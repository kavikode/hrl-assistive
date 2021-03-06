#!/usr/bin/env python

from copy import deepcopy
import numpy as np

import rospy
import actionlib
from geometry_msgs.msg import PoseStamped, Quaternion
import tf


class HapticMpcArmWrapper(object):
    def __init__(self, side):
        self.side = side
        self.pose_state = None
        self.in_deadzone = None
        self.tfl = tf.TransformListener()
        self.state_sub = rospy.Subscriber('/'+side+'_arm/haptic_mpc/gripper_pose', PoseStamped, self.state_cb)
        self.goal_pub = rospy.Publisher('/'+side+'_arm/haptic_mpc/goal_pose', PoseStamped, queue_size=3)
        self.deadzone_dist = rospy.get_param('/'+side+'_arm/haptic_mpc/deadzone_distance', 0.01)
        self.deadzone_angle = np.radians(rospy.get_param('/'+side+'_arm/haptic_mpc/deadzone_angle', 3))

    def state_cb(self, msg):
        new_frame = '/base_link'
        if msg.header.frame_id == new_frame:
            self.pose_state = msg
        msg.header.stamp = rospy.Time(0)
        try:
            self.tfl.waitForTransform(msg.header.frame_id, new_frame, msg.header.stamp, rospy.Duration(10.0))
        except (tf.ConnectivityException, tf.LookupException, tf.ExtrapolationException) as e:
            rospy.logerr('[%s]: TF Exception: %s', rospy.get_name(), e)
        self.pose_state = self.tfl.transformPose(new_frame, msg)

    def get_error(self, ps_goal):
        ps_now = deepcopy(self.pose_state)
        # Calculate cartesian error distance
        pos_now = np.array([ps_now.pose.position.x, ps_now.pose.position.y, ps_now.pose.position.z])
        pos_goal = np.array([ps_goal.pose.position.x, ps_goal.pose.position.y, ps_goal.pose.position.z])
        cart_err = np.linalg.norm(pos_goal - pos_now)
        # Calculate orientation error angle
        q_now = [ps_now.pose.orientation.x, ps_now.pose.orientation.y, ps_now.pose.orientation.z, ps_now.pose.orientation.w]
        q_goal = [ps_goal.pose.orientation.x, ps_goal.pose.orientation.y, ps_goal.pose.orientation.z, ps_goal.pose.orientation.w]
        ang = np.arccos(np.dot(q_now, q_goal))
        ang_err = ang if ang <= np.pi/2 else np.pi - ang  # handle equivalent quaternions
        return (cart_err, ang_err)

    def move_arm(self, ps_goal, wait=False, progress_error_ratio=0.98, progress_check_time=1, cart_threshold=None, ort_threshold=None):
        ps_goal.header.stamp = rospy.Time.now()
        self.goal_pub.publish(ps_goal)
        if not wait:
            return True
        rospy.sleep(0.7)  # make sure the msg has time to arrive...
        check_delay = rospy.Duration(progress_check_time)
        last_cart_err, last_ort_err = self.get_error(ps_goal)
        next_check_time = rospy.Time.now() + check_delay
        while not rospy.is_shutdown():
            cart_err, ort_err = self.get_error(ps_goal)
            if cart_err < self.deadzone_dist and ort_err < self.deadzone_angle:
                return True
            if rospy.Time.now() > next_check_time:
                if cart_threshold is not None and cart_err < cart_threshold:
                    if ort_threshold is None:
                        return True
                    elif ort_err < ort_threshold:
                        return True
                if cart_err <= progress_error_ratio*last_cart_err or ort_err <= progress_error_ratio*last_ort_err:
                    last_cart_err, last_ort_err = cart_err, ort_err
                    next_check_time = rospy.Time.now() + rospy.Duration(3)  # Progressing, set next check time
                else:
                    return False  # Not progressing
            rospy.sleep(0.1)
        return False  # node killed...


from pr2_controllers_msgs.msg import Pr2GripperCommandAction, Pr2GripperCommandGoal, Pr2GripperCommand
from pr2_gripper_sensor_msgs.msg import (PR2GripperGrabAction, PR2GripperGrabGoal, PR2GripperGrabCommand,
                                         PR2GripperReleaseAction, PR2GripperReleaseGoal, PR2GripperReleaseCommand)


class GripperGraspControllerWrapper(object):
    def __init__(self, side):
        self.side = side
        self.gripper_client = actionlib.SimpleActionClient('/'+side[0]+'_gripper_sensor_controller/gripper_action', Pr2GripperCommandAction)
        self.grab_client = actionlib.SimpleActionClient('/'+side[0]+'_gripper_sensor_controller/grab', PR2GripperGrabAction)
        self.contact_release_client = actionlib.SimpleActionClient('/'+side[0]+'_gripper_sensor_controller/release', PR2GripperReleaseAction)
        self.gripper_client.wait_for_server()
        self.grab_client.wait_for_server()

    def open_gripper(self, wait=False):
        cmd = Pr2GripperCommand(0.09, -1.0)
        goal = Pr2GripperCommandGoal(cmd)
        self.gripper_client.send_goal(goal)
        if wait:
            self.contact_release_client.wait_for_result()

    def grasp(self, wait=False):
        cmd = PR2GripperGrabCommand(0.03)
        goal = PR2GripperGrabGoal(cmd)
        self.grab_client.send_goal(goal)
        if wait:
            self.grab_client.wait_for_result()

    def release_on_contact(self, wait=False):
        cmd = PR2GripperReleaseCommand()
        cmd.event.trigger_conditions = 2  # Slip, impact, or acceleration
        cmd.event.acceleration_trigger_magnitude = 2.0
        cmd.event.slip_trigger_magnitude = 0.005
        goal = PR2GripperReleaseGoal(cmd)
        self.contact_release_client.send_goal(goal)
        if wait:
            self.contact_release_client.wait_for_result()


from assistive_teleop.msg import OverheadGraspAction, OverheadGraspResult, OverheadGraspFeedback


class OverheadGrasp(object):
    def __init__(self, side, overhead_offset=0.12):
        self.overhead_offset = overhead_offset
        self.side = side
        self.arm = HapticMpcArmWrapper(side)
        self.gripper = GripperGraspControllerWrapper(side)
        self.action_server = actionlib.SimpleActionServer('/%s_arm/overhead_grasp' % self.side, OverheadGraspAction, self.execute, False)
        self.action_server.start()
        rospy.loginfo("[%s] %s Overhead Grasp Action Started", rospy.get_name(), self.side.capitalize())

    def execute(self, goal):
        self.action_server.publish_feedback(OverheadGraspFeedback("Processing Goal Pose"))
        (setup_pose, overhead_pose, goal_pose) = self.process_path(goal.goal_pose)
        print "Moving arm to setup"
        self.action_server.publish_feedback(OverheadGraspFeedback("Moving to Setup Position"))
        reached = self.arm.move_arm(setup_pose, wait=True, cart_threshold=0.05)
        if not reached:
            self.action_server.set_aborted(OverheadGraspResult('Reaching to Setup'))
            print "Failed to reach setup"
            return
        print "Moving arm to overhead"
        self.action_server.publish_feedback(OverheadGraspFeedback("Moving to Overhead Position"))
        reached = self.arm.move_arm(overhead_pose, wait=True, cart_threshold=0.04, ort_threshold=np.radians(10))
        if not reached:
            self.action_server.set_aborted(OverheadGraspResult('Reaching to Overhead'))
            print "Failed to reach overhead"
            return
        print "Opening gripper"
        self.action_server.publish_feedback(OverheadGraspFeedback("Opening Gripper"))
        self.gripper.open_gripper()
        rospy.sleep(2.0)
        print "Moving arm to goal"
        self.action_server.publish_feedback(OverheadGraspFeedback("Moving to goal"))
        reached = self.arm.move_arm(goal_pose, wait=True)
        if not reached:
            self.action_server.set_aborted(OverheadGraspResult('Reaching to Goal'))
            print "Failed to reach goal"
            return
        print "Closing Gripper"
        self.action_server.publish_feedback(OverheadGraspFeedback("Closing Gripper"))
        self.gripper.grasp(wait=True)
        self.action_server.publish_feedback(OverheadGraspFeedback("finished"))
        self.action_server.set_succeeded(OverheadGraspResult('finished'))
        print "Finished"

    def process_path(self, goal_pose):
        while self.arm.pose_state is None and not rospy.is_shutdown():
            rospy.sleep(0.1)
            rospy.loginfo("[%s] Waiting for %s arm state", rospy.get_name(), self.side)
        current_pose = deepcopy(self.arm.pose_state)
        goal_pose.pose.orientation = Quaternion(0.7071067, 0, -0.7071067, 0)
        overhead_height = max(goal_pose.pose.position.z + self.overhead_offset, current_pose.pose.position.z)
        setup_pose = deepcopy(current_pose)
        setup_pose.header.frame_id = '/base_link'
        setup_pose.pose.position.z = overhead_height
        overhead_pose = deepcopy(goal_pose)
        overhead_pose.pose.position.z = overhead_height
        goal_pose.pose.position.z += -0.01
        return (setup_pose, overhead_pose, goal_pose)


from assistive_teleop.msg import OverheadPlaceAction, OverheadPlaceResult, OverheadPlaceFeedback


class OverheadPlace(object):
    def __init__(self, side, overhead_offset=0.1):
        self.overhead_offset = overhead_offset
        self.side = side
        self.arm = HapticMpcArmWrapper(side)
        self.gripper = GripperGraspControllerWrapper(side)
        self.action_server = actionlib.SimpleActionServer('/%s_arm/overhead_place' % self.side, OverheadPlaceAction, self.execute, False)
        self.action_server.start()
        rospy.loginfo("[%s] %s Overhead Place Action Started", rospy.get_name(), self.side.capitalize())

    def execute(self, goal):
        self.action_server.publish_feedback(OverheadGraspFeedback("Processing Goal Pose"))
        (setup_pose, overhead_pose, goal_pose) = self.process_path(goal.goal_pose)
        print "Moving arm to setup"
        self.action_server.publish_feedback(OverheadPlaceFeedback("Moving to Setup Position"))
        reached = self.arm.move_arm(setup_pose, wait=True, cart_threshold=0.05, ort_threshold=30)
        if not reached:
            self.action_server.set_aborted(OverheadGraspResult('Reaching to Setup'))
            print "Failed to reach setup"
            return
        self.action_server.publish_feedback(OverheadPlaceFeedback("Moving to Overhead Position"))
        print "Moving arm to overhead"
        reached = self.arm.move_arm(overhead_pose, wait=True, cart_threshold=0.03)
        if not reached:
            self.action_server.set_aborted(OverheadGraspResult('Reaching to Overhead'))
            print "Failed to reach overhead"
            return
        self.gripper.release_on_contact()
        print "moving arm to goal"
        self.action_server.publish_feedback(OverheadPlaceFeedback("Moving to goal"))
        reached = self.arm.move_arm(goal_pose, wait=True)
        if not reached:
            self.action_server.set_aborted(OverheadGraspResult('Reaching to Goal'))
            print "Failed to reach goal"
            return
        print "opening gripper"
        self.action_server.publish_feedback(OverheadPlaceFeedback("Opening Gripper"))
        self.gripper.open_gripper()
        self.action_server.publish_feedback(OverheadPlaceFeedback("finished"))
        self.action_server.set_succeeded(OverheadPlaceResult('finished'))

    def process_path(self, goal_pose):
        while self.arm.pose_state is None and not rospy.is_shutdown():
            rospy.sleep(0.1)
            rospy.loginfo("[%s] Waiting for %s arm state", rospy.get_name(), self.side)
        current_pose = deepcopy(self.arm.pose_state)
        goal_pose.pose.orientation = Quaternion(0.7071067, 0, -0.7071067, 0)
        overhead_height = max(goal_pose.pose.position.z + self.overhead_offset, current_pose.pose.position.z)
        setup_pose = deepcopy(current_pose)
        setup_pose.header.frame_id = '/base_link'
        setup_pose.pose.position.z = overhead_height
        overhead_pose = deepcopy(goal_pose)
        overhead_pose.pose.position.z = overhead_height
        goal_pose.pose.position.z += -0.01
        return (setup_pose, overhead_pose, goal_pose)


def main():
    rospy.init_node('overhead_grasp')
    r_overhead_grasp = OverheadGrasp('right')
    l_overhead_grasp = OverheadGrasp('left')
    r_overhead_place = OverheadPlace('right')
    l_overhead_place = OverheadPlace('left')
    rospy.spin()
