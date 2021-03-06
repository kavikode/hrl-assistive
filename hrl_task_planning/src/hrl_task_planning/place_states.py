import rospy
import actionlib
from geometry_msgs.msg import PoseStamped
import tf

# pylint: disable=W0102
from task_smacher import PDDLSmachState
from hrl_task_planning.msg import PDDLState

SPA = ["succeeded", "preempted", "aborted"]


def get_action_state(domain, problem, action, args, init_state, goal_state):
    if action == 'FORGET-LOCATION':
        param = "/pddl_tasks/%s/%s/%s" % (domain, 'KNOWN', args[0])
        return DeleteParamState(param, domain=domain, problem=problem,
                                action=action, action_args=args,
                                init_state=init_state, goal_state=goal_state,
                                outcomes=SPA)
    elif action == 'AUTO-PLACE':
        return OverheadPlaceState(hand=args[0], item=args[1], location=args[2], domain=domain, problem=problem,
                                  action=action, action_args=args, init_state=init_state,
                                  goal_state=goal_state, outcomes=SPA)
    elif action in ['ID-LOCATION', 'MANUAL-PLACE']:
        return PDDLSmachState(domain, problem, action, args, init_state, goal_state, outcomes=SPA)


class DeleteParamState(PDDLSmachState):
    def __init__(self, param, *args, **kwargs):
        super(DeleteParamState, self).__init__(*args, **kwargs)
        self.param = param

    def on_execute(self, ud):
        if self.preempt_requested():
            self.service_preempt()
            return 'preempted'
        try:
            rospy.delete_param(self.param)
        except KeyError:
            pass
        except rospy.ROSException:
            rospy.warn("[%s] Error trying to delete param %s", rospy.get_name(), self.param)
            return 'aborted'


from assistive_teleop.msg import OverheadPlaceAction, OverheadPlaceGoal


class OverheadPlaceState(PDDLSmachState):
    def __init__(self, hand, item, location, domain, *args, **kwargs):
        super(OverheadPlaceState, self).__init__(domain=domain, *args, **kwargs)
        self.location = location
        self.domain = domain
        self.item = item
        self.tfl = tf.TransformListener()
        if hand == 'RIGHT_HAND':
            self.overhead_place_client = actionlib.SimpleActionClient('/right_arm/overhead_place', OverheadPlaceAction)
        elif hand == 'LEFT_HAND':
            self.overhead_place_client = actionlib.SimpleActionClient('/left_arm/overhead_place', OverheadPlaceAction)
        self.state_update_pub = rospy.Publisher('/pddl_tasks/state_updates', PDDLState, queue_size=1)

    def on_execute(self, ud):
        try:
            goal_pose_dict = rospy.get_param('/pddl_tasks/%s/KNOWN/%s' % (self.domain, self.location))
            goal_pose = _dict_to_pose_stamped(goal_pose_dict)
        except KeyError:
            rospy.loginfo("[%s] Move Arm Cannot find location %s on parameter server", rospy.get_name(), self.location)
            return 'aborted'
        goal_msg = OverheadPlaceGoal()
        goal_msg.goal_pose = goal_pose
        self.overhead_place_client.send_goal(goal_msg)
        self.overhead_place_client.wait_for_result()
        state_update = PDDLState()
        state_update.domain = self.domain
        state_update.problem = self.problem
        state_update.predicates = ['(AUTO-PLACE-DONE)']
        self.state_update_pub.publish(state_update)


def _pose_stamped_to_dict(ps_msg):
    return {'header':
            {'seq': ps_msg.header.seq,
             'stamp': {'secs': ps_msg.header.stamp.secs,
                       'nsecs': ps_msg.header.stamp.nsecs},
             'frame_id': ps_msg.header.frame_id},
            'pose':
            {'position': {'x': ps_msg.pose.position.x,
                          'y': ps_msg.pose.position.y,
                          'z': ps_msg.pose.position.z},
             'orientation': {'x': ps_msg.pose.orientation.x,
                             'y': ps_msg.pose.orientation.y,
                             'z': ps_msg.pose.orientation.z,
                             'w': ps_msg.pose.orientation.w}}}


def _dict_to_pose_stamped(ps_dict):
    ps = PoseStamped()
    ps.header.seq = ps_dict['header']['seq']
    ps.header.stamp.secs = ps_dict['header']['stamp']['secs']
    ps.header.stamp.nsecs = ps_dict['header']['stamp']['nsecs']
    ps.header.frame_id = ps_dict['header']['frame_id']
    ps.pose.position.x = ps_dict['pose']['position']['x']
    ps.pose.position.y = ps_dict['pose']['position']['y']
    ps.pose.position.z = ps_dict['pose']['position']['z']
    ps.pose.orientation.x = ps_dict['pose']['orientation']['x']
    ps.pose.orientation.y = ps_dict['pose']['orientation']['y']
    ps.pose.orientation.z = ps_dict['pose']['orientation']['z']
    ps.pose.orientation.w = ps_dict['pose']['orientation']['w']
    return ps
