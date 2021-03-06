#!/usr/bin/env python

import sys, optparse
import numpy as np
import math as m
import threading
import copy

import openravepy as op

import roslib
roslib.load_manifest('hrl_base_selection')
roslib.load_manifest('hrl_haptic_mpc')
import rospy, rospkg
import tf
from std_msgs.msg import String
from geometry_msgs.msg import PoseStamped
from sensor_msgs.msg import JointState
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
from visualization_msgs.msg import Marker

import hrl_haptic_manipulation_in_clutter_msgs.msg as haptic_msgs
import hrl_lib.transforms as tr
from hrl_base_selection.srv import *
from helper_functions import createBMatrix

class ArmReacher:
    head = np.matrix([[m.cos(0.),-m.sin(0.),0.,0],
                      [m.sin(0.),m.cos(0.),0.,0.],
                      [0.,0.,1.,0.],[0.,0.,0.,1.]])

    robot_start = np.matrix([[m.cos(0.),-m.sin(0.),0.,0],
                             [m.sin(0.),m.cos(0.),0.,0.],
                             [0.,0.,1.,0.],[0.,0.,0.,1.]])
    sol = traj =None
    joint_angles = np.zeros(39)
    joint_names = []
    state_lock = threading.RLock()
    

    def __init__(self):
        rospy.init_node('arm_reacher')
        self.listener = tf.TransformListener()
        self.vis_pub = rospy.Publisher("~_wc_model", Marker, latch=True)
        self.goal_pose_pub = rospy.Publisher("/haptic_mpc/goal_pose", PoseStamped) 
        self.feedback_pub = rospy.Publisher("wt_log_out", String)
        
        self.env = op.Environment()
        self.env.SetViewer('qtcoin')
        self.env.Load('robots/pr2-beta-static.zae')
        self.robot = self.env.GetRobots()[0]
        print self.robot
        v = self.robot.GetActiveDOFValues()
        for name in self.joint_names:
            v[self.robot.GetJoint(name).GetDOFIndex()] = self.joint_angles[self.joint_names.index(name)]
        self.robot.SetActiveDOFValues(v)
        #v[self.robot.GetJoint('l_shoulder_pan_joint').GetDOFIndex()]= np.pi/2.
        #v[self.robot.GetJoint('r_shoulder_pan_joint').GetDOFIndex()] = -np.pi/2.
        #v[self.robot.GetJoint('l_gripper_l_finger_joint').GetDOFIndex()] = .54
        #v[self.robot.GetJoint('torso_lift_joint').GetDOFIndex()] = .15
        #self.robot.SetActiveDOFValues(v)
        self.robot_start = np.matrix([[m.cos(0.), -m.sin(0.),  0.,  0.],
                                      [m.sin(0.),  m.cos(0.),  0.,  0.],
                                      [       0.,         0.,  1.,  0.],
                                      [       0.,         0.,  0.,  1.]])
        #self.robot_start = np.matrix([[ -0,    1,    0.0,    2.6],
        #                             [ -1.,   -0,    0.00,    1.0],
        #                             [  0.,    0.,    1.00,    0.0],
        #                             [  0.,    0.,    0.0,    1.00]])

        self.robot.SetTransform(np.array(self.robot_start))

        self.moving = False

        rospack = rospkg.RosPack()
        pkg_path = rospack.get_path('hrl_base_selection')
        self.env.Load(''.join([pkg_path, '/models/ADA_Wheelchair.dae']))

        self.manip = self.robot.SetActiveManipulator('leftarm')
        self.ikmodel = op.databases.inversekinematics.InverseKinematicsModel(self.robot,iktype=op.IkParameterization.Type.Transform6D)
        self.manipprob = op.interfaces.BaseManipulation(self.robot) # create the interface for basic manipulation programs

        if not self.ikmodel.load():
            self.ikmodel.autogenerate()

        self.wheelchair = self.env.GetBodies()[1]
        self.wc_angle =  m.pi

        self.pr2_B_wc = np.matrix([[m.cos(0.),-m.sin(0.),0.,2],
                                 [m.sin(0.),m.cos(0.),0.,0.],
                                 [0.,0.,1.,0.],[0.,0.,0.,1.]])

        #self.pr2_B_wc =   np.matrix([[ self.head[0,0], self.head[0,1],   0.,  self.head[0,3]],
        #                             [ self.head[1,0], self.head[1,1],   0.,  self.head[1,3]],
        #                             [             0.,             0.,   1.,              0.],
        #                             [             0.,             0.,   0.,              1.]])

        self.corner_B_head = np.matrix([[m.cos(0.),-m.sin(0.), 0., 0.45],
                                        [m.sin(0.),m.cos(0.),  0., 0.44],#0.34
                                        [       0.,       0.,  1.,   0.],
                                        [       0.,       0.,  0.,   1.]])
        self.wheelchair_location = self.pr2_B_wc * self.corner_B_head.I
        self.wheelchair.SetTransform(np.array(self.wheelchair_location))

        rospy.Subscriber('/joint_states', JointState, self.update_robot_state)
        #rospy.Subscriber('~goal_pose', PoseStamped, self.new_goal)
        #rospy.Subscriber('/haptic_mpc/head_pose', PoseStamped, self.new_head)
        rospy.Subscriber('/select_base_server/pr2_B_wc',PoseStamped,self.update_wc)
        self.goal_traj_pub = rospy.Publisher("/haptic_mpc/joint_trajectory", JointTrajectory, latch=True)
        #self.mpc_weights_pub = rospy.Publisher("/haptic_mpc/weights", haptic_msgs.HapticMpcWeights)
        rospy.loginfo("[%s] Arm reaching node has been created." %rospy.get_name())

    def pub_feedback(self, msg):
        rospy.loginfo("[%s] %s" % (rospy.get_name(), msg))
        self.feedback_pub.publish(msg)

    def update_wc(self,msg):
        v = self.robot.GetActiveDOFValues()
        for name in self.joint_names:
            v[self.robot.GetJoint(name).GetDOFIndex()] = self.joint_angles[self.joint_names.index(name)]
        self.robot.SetActiveDOFValues(v)
        rospy.loginfo("I have got a wc location!")
        pos_temp = [msg.pose.position.x,
                    msg.pose.position.y,
                    msg.pose.position.z]
        ori_temp = [msg.pose.orientation.x,
                    msg.pose.orientation.y,
                    msg.pose.orientation.z,
                    msg.pose.orientation.w]
        self.pr2_B_wc = createBMatrix(pos_temp, ori_temp)
        psm = PoseStamped()
        psm.header.stamp = rospy.Time.now()
        #self.goal_pose_pub.publish(psm)
        self.pub_feedback("Reaching toward goal location")

        wheelchair_location = self.pr2_B_wc * self.corner_B_head.I
        self.wheelchair.SetTransform(np.array(wheelchair_location))

        pos_goal = wheelchair_location[:3,3]
        ori_goal = tr.matrix_to_quaternion(wheelchair_location[0:3,0:3])

        marker = Marker()
        marker.header.frame_id = "base_link"
        marker.header.stamp = rospy.Time()
        marker.ns = "arm_reacher_wc_model"
        marker.id = 0
        marker.type = Marker.MESH_RESOURCE;
        marker.action = Marker.ADD
        marker.pose.position.x = pos_goal[0]
        marker.pose.position.y = pos_goal[1]
        marker.pose.position.z = pos_goal[2]
        marker.pose.orientation.x = ori_goal[0]
        marker.pose.orientation.y = ori_goal[1]
        marker.pose.orientation.z = ori_goal[2]
        marker.pose.orientation.w = ori_goal[3]
        marker.scale.x = 0.0254
        marker.scale.y = 0.0254
        marker.scale.z = 0.0254
        marker.color.a = 1.0
        marker.color.r = 1.0
        marker.color.g = 0.0
        marker.color.b = 0.0
        #only if using a MESH_RESOURCE marker type:
        marker.mesh_resource = "package://hrl_base_selection/models/ADA_Wheelchair.dae"
        self.vis_pub.publish( marker )

        v = self.robot.GetActiveDOFValues()
        for name in self.joint_names:
            v[self.robot.GetJoint(name).GetDOFIndex()] = self.joint_angles[self.joint_names.index(name)]
        self.robot.SetActiveDOFValues(v)
        goal_angle = 0#m.pi/2
        self.goal  =  np.matrix([[    m.cos(goal_angle),     -m.sin(goal_angle),                0.,              .5],
                                  [    m.sin(goal_angle),      m.cos(goal_angle),                0.,              0],
                                  [                   0.,                     0.,                1.,             1.2],
                                  [                   0.,                     0.,                0.,              1.]])
        #self.goal = copy.copy(self.pr2_B_wc)
        #self.goal[0,3]=self.goal[0,3]-.2
        #self.goal[1,3]=self.goal[1,3]-.3
        #self.goal[2,3]= 1.3
        print 'goal is: \n', self.goal

        self.goal_B_gripper =  np.matrix([[   0.,  0.,   1., 0.1],
                                          [   0.,  1.,   0.,  0.],
                                          [  -1.,  0.,   0.,  0.],
                                          [   0.,  0.,   0.,  1.]])
        self.pr2_B_goal = self.goal*self.goal_B_gripper

        self.sol = self.manip.FindIKSolution(np.array(self.pr2_B_goal), op.IkFilterOptions.CheckEnvCollisions)
        if self.sol is None:
            self.pub_feedback("Failed to find a good arm configuration for reaching.")
            return None
        rospy.loginfo("[%s] Got an IK solution: %s" % (rospy.get_name(), self.sol))
        self.pub_feedback("Found a good arm configuration for reaching.")

        self.pub_feedback("Looking for path for arm to goal.")
        traj = None
        try:
            #self.res = self.manipprob.MoveToHandPosition(matrices=[np.array(self.pr2_B_goal)],seedik=10) # call motion planner with goal joint angles
            self.traj=self.manipprob.MoveManipulator(goal=self.sol,outputtrajobj=True)
            self.pub_feedback("Found a path to reach to the goal.")
        except:
            self.traj = None
            self.pub_feedback("Could not find a path to reach to the goal")
            return None

        tmp_traj = tmp_vel = tmp_acc = [] #np.zeros([self.traj.GetNumWaypoints(),7])
        trajectory = JointTrajectory()
        for i in xrange(self.traj.GetNumWaypoints()):
            
            point = JointTrajectoryPoint()
            temp = []
            for j in xrange(7):
                temp.append(float(self.traj.GetWaypoint(i)[j]))
            point.positions = temp
            #point.positions.append(temp)
            #point.accelerations.append([0.,0.,0.,0.,0.,0.,0.])
            #point.velocities.append([0.,0.,0.,0.,0.,0.,0.])
            trajectory.points.append(point)
            #tmp_traj.append(temp)
            #tmp_traj.append(list(self.traj.GetWaypoint(i)))

            #tmp_vel.append([0.,0.,0.,0.,0.,0.,0.])
            #tmp_acc.append([0.,0.,0.,0.,0.,0.,0.])
            #print 'tmp_traj is: \n', tmp_traj
            #for j in xrange(7):
                #tmp_traj[i,j] = float(self.traj.GetWaypoint(i)[j])
        #trajectory = JointTrajectory()
        #point = JointTrajectoryPoint()
        #point.positions.append(tmp_traj)
        #point.velocities.append(tmp_vel)
        #point.accelerations.append(tmp_acc)
        #point.velocities=[[0.,0.,0.,0.,0.,0.,0.]]
        #point.accelerations=[[0.,0.,0.,0.,0.,0.,0.]]
        trajectory.joint_names = ['l_upper_arm_roll_joint',
                                  'l_shoulder_pan_joint',
                                  'l_shoulder_lift_joint',
                                  'l_forearm_roll_joint',
                                  'l_elbow_flex_joint',
                                  'l_wrist_flex_joint',
                                  'l_wrist_roll_joint']
        #trajectory.points.append(point)
        #self.mpc_weights_pub.publish(self.weights)
        self.moving=True
        self.goal_traj_pub.publish(trajectory)
        self.pub_feedback("Reaching to location")


    def new_goal(self, psm):
        rospy.loginfo("[%s] I just got a goal location. I will now start reaching!" %rospy.get_name())
        psm.header.stamp = rospy.Time.now()
        #self.goal_pose_pub.publish(psm)
        self.pub_feedback("Reaching toward goal location")
        #return
        # This is to use tf to get head location.
        # Otherwise, there is a subscriber to get a head location.
        #Comment out if there is no tf to use.
        #now = rospy.Time.now() + rospy.Duration(0.5)
        #self.listener.waitForTransform('/base_link', '/head_frame', now, rospy.Duration(10))
        #pos_temp, ori_temp = self.listener.lookupTransform('/base_link', '/head_frame', now)
        #self.head = createBMatrix(pos_temp,ori_temp)

        #self.pr2_B_wc =   np.matrix([[ self.head[0,0], self.head[0,1],   0., self.head[0,3]],
        #                             [ self.head[1,0], self.head[1,1],   0., self.head[1,3]],
        #                             [             0.,             0.,   1.,             0.],
        #                             [             0.,             0.,   0.,              1]])

        #self.pr2_B_wc = 

        wheelchair_location = self.pr2_B_wc * self.corner_B_head.I
        self.wheelchair.SetTransform(np.array(wheelchair_location))

        pos_goal = wheelchair_location[:3,3]
        ori_goal = tr.matrix_to_quaternion(wheelchair_location[0:3,0:3])

        marker = Marker()
        marker.header.frame_id = "base_link"
        marker.header.stamp = rospy.Time()
        marker.ns = "arm_reacher_wc_model"
        marker.id = 0
        marker.type = Marker.MESH_RESOURCE;
        marker.action = Marker.ADD
        marker.pose.position.x = pos_goal[0]
        marker.pose.position.y = pos_goal[1]
        marker.pose.position.z = pos_goal[2]
        marker.pose.orientation.x = ori_goal[0]
        marker.pose.orientation.y = ori_goal[1]
        marker.pose.orientation.z = ori_goal[2]
        marker.pose.orientation.w = ori_goal[3]
        marker.scale.x = 0.0254
        marker.scale.y = 0.0254
        marker.scale.z = 0.0254
        marker.color.a = 1.0
        marker.color.r = 1.0
        marker.color.g = 0.0
        marker.color.b = 0.0
        #only if using a MESH_RESOURCE marker type:
        marker.mesh_resource = "package://hrl_base_selection/models/ADA_Wheelchair.dae"
        self.vis_pub.publish( marker )

        v = self.robot.GetActiveDOFValues()
        for name in self.joint_names:
            v[self.robot.GetJoint(name).GetDOFIndex()] = self.joint_angles[self.joint_names.index(name)]
        self.robot.SetActiveDOFValues(v)

        pos_temp = [psm.pose.position.x,
                    psm.pose.position.y,
                    psm.pose.position.z]
        ori_temp = [psm.pose.orientation.x,
                    psm.pose.orientation.y,
                    psm.pose.orientation.z,
                    psm.pose.orientation.w]
        self.goal = createBMatrix(pos_temp,ori_temp)

        self.goal_B_gripper =  np.matrix([[   0.,  0.,   1., 0.1],
                                          [   0.,  1.,   0.,  0.],
                                          [  -1.,  0.,   0.,  0.],
                                          [   0.,  0.,   0.,  1.]])
        self.pr2_B_goal = self.goal*self.goal_B_gripper

        self.sol = self.manip.FindIKSolution(np.array(self.pr2_B_goal), op.IkFilterOptions.CheckEnvCollisions)
        if self.sol is None:
            self.pub_feedback("Failed to find a good arm configuration for reaching.")
            return None
        rospy.loginfo("[%s] Got an IK solution: %s" % (rospy.get_name(), self.sol))
        self.pub_feedback("Found a good arm configuration for reaching.")

        self.pub_feedback("Looking for path for arm to goal.")
        traj = None
        try:
            #self.res = self.manipprob.MoveToHandPosition(matrices=[np.array(self.pr2_B_goal)],seedik=10) # call motion planner with goal joint angles
            self.traj=self.manipprob.MoveManipulator(goal=self.sol,outputtrajobj=True)
            self.pub_feedback("Found a path to reach to the goal.")
        except:
            self.traj = None
            self.pub_feedback("Could not find a path to reach to the goal")
            return None

        tmp_traj = tmp_vel = tmp_acc = [] #np.zeros([self.traj.GetNumWaypoints(),7])
        trajectory = JointTrajectory()
        for i in xrange(self.traj.GetNumWaypoints()):
            point = JointTrajectoryPoint()
            temp = []
            for j in xrange(7):
                temp.append(float(self.traj.GetWaypoint(i)[j]))
            point.positions = temp
            #point.positions.append(temp)
            #point.accelerations.append([0.,0.,0.,0.,0.,0.,0.])
            #point.velocities.append([0.,0.,0.,0.,0.,0.,0.])
            trajectory.points.append(point)
            #tmp_traj.append(temp)
            #tmp_traj.append(list(self.traj.GetWaypoint(i)))

            #tmp_vel.append([0.,0.,0.,0.,0.,0.,0.])
            #tmp_acc.append([0.,0.,0.,0.,0.,0.,0.])
            #print 'tmp_traj is: \n', tmp_traj
            #for j in xrange(7):
                #tmp_traj[i,j] = float(self.traj.GetWaypoint(i)[j])
        #trajectory = JointTrajectory()
        #point = JointTrajectoryPoint()
        #point.positions.append(tmp_traj)
        #point.velocities.append(tmp_vel)
        #point.accelerations.append(tmp_acc)
        #point.velocities=[[0.,0.,0.,0.,0.,0.,0.]]
        #point.accelerations=[[0.,0.,0.,0.,0.,0.,0.]]
        trajectory.joint_names = ['l_upper_arm_roll_joint',
                                  'l_shoulder_pan_joint',
                                  'l_shoulder_lift_joint',
                                  'l_forearm_roll_joint',
                                  'l_elbow_flex_joint',
                                  'l_wrist_flex_joint',
                                  'l_wrist_roll_joint']
        #trajectory.points.append(point)
        #self.mpc_weights_pub.publish(self.weights)
        self.goal_traj_pub.publish(trajectory)
        self.pub_feedback("Reaching to location")

    def update_robot_state(self, msg):
        #print 'started updating joint angles \n'
        with self.state_lock:
            #self.last_msg_time = rospy.Time.now() # timeout for the controller
            #self.msg = msg
            if not self.moving:
                self.joint_names = msg.name
                self.joint_angles = msg.position
                v = self.robot.GetActiveDOFValues()
                for name in self.joint_names:
                    v[self.robot.GetJoint(name).GetDOFIndex()] = self.joint_angles[self.joint_names.index(name)]
                self.robot.SetActiveDOFValues(v)
            #print 'finished updating joint angles \n'

    # This is to use a subscriber to get head location. Otherwise, there is a tf listener to get a head location.
    def new_head(self, msg):
        rospy.loginfo("I have got a head location!")
        pos_temp = [msg.pose.position.x,
                    msg.pose.position.y,
                    msg.pose.position.z]
        ori_temp = [msg.pose.orientation.x,
                    msg.pose.orientation.y,
                    msg.pose.orientation.z,
                    msg.pose.orientation.w]
        self.head = createBMatrix(pos_temp, ori_temp)

if __name__ == "__main__":
    reach = ArmReacher()
    rospy.spin()
