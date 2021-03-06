#!/usr/bin/env python
#
# Copyright (c) 2014, Georgia Tech Research Corporation
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of the Georgia Tech Research Corporation nor the
#       names of its contributors may be used to endorse or promote products
#       derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY GEORGIA TECH RESEARCH CORPORATION ''AS IS'' AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL GEORGIA TECH BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA,
# OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
# OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
# ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

#  \author Daehyung Park (Healthcare Robotics Lab, Georgia Tech.)

# System
import sys, time, copy
import numpy as np

# ROS
import rospy, roslib
import tf
import PyKDL
from geometry_msgs.msg import Pose, PoseStamped, Point, Quaternion
from std_msgs.msg import String

# HRL library
import hrl_haptic_mpc.haptic_mpc_util as haptic_mpc_util
import hrl_lib.quaternion as quatMath 
from hrl_srvs.srv import None_Bool, String_String

# Personal library
from sandbox_dpark_darpa_m3.lib.hrl_mpc_base import mpcBaseAction
from sandbox_dpark_darpa_m3.lib import hrl_dh_lib as dh

class armReachAction(mpcBaseAction):
    def __init__(self, d_robot, controller, arm, tool_id=0, verbose=False):
        mpcBaseAction.__init__(self, d_robot, controller, arm, tool_id)
        self.listener = tf.TransformListener()

        #Variables...! #
        self.stop_motion = False
        self.verbose = verbose

        self.default_frame      = PyKDL.Frame()
        self.knee_left = None

        self.initCommsForArmReach()                            
        self.initParamsForArmReach()

        rate = rospy.Rate(100) # 25Hz, nominally.
        while not rospy.is_shutdown():
            if self.getJointAngles() != []:
                if verbose:
                    print "--------------------------------"
                    print "Current "+self.arm_name+" arm joint angles"
                    print self.getJointAngles()
                    print "Current "+self.arm_name+" arm pose"
                    print self.getEndeffectorPose(tool=tool_id)
                    print "Current "+self.arm_name+" arm orientation (w/ euler rpy)"
                    print self.getEndeffectorRPY(tool=tool_id) #*180.0/np.pi
                    print "--------------------------------"
                break
            rate.sleep()
            
        rospy.loginfo("Arm Reach Action is initialized.")
        print "Current "+self.arm_name+" arm joint angles"
        print self.getJointAngles()
        print "Current "+self.arm_name+" arm pose"
        print self.getEndeffectorPose(tool=tool_id)
                            
    def initCommsForArmReach(self):

        # publishers and subscribers
        rospy.Subscriber('InterruptAction', String, self.stopCallback)        
        # service
        self.reach_service = rospy.Service('arm_reach_enable', String_String, self.serverCallback)
        
        if self.verbose: rospy.loginfo("ROS-based communications are set up .")
                                    
    def initParamsForArmReach(self):
        '''
        Industrial movment commands generally follows following format, 
        
               Movement type, joint or pose(pos+euler or pos+quat), timeout, relative_frame(not implemented)

        In this code, we allow to use following movement types,

        MOVEP: point-to-point motion without orientation control (ex. MOVEP pos-euler timeout relative_frame)
        MOVES: point-to-point motion with orientation control (ex. MOVES pos-euler timeout relative_frame)
        MOVEL: straight (linear) motion with orientation control (ex. MOVEL pos-quat timeout relative_frame)
        MOVET: MOVES with respect to the current tool frame (ex. MOVET pos-euler timeout) (experimental!!)
        MOVEJ: joint motion (ex. MOVEJ joint timeout)
        PAUSE: Add pause time between motions (ex. PAUSE duration)

        #TOOL: Set a tool frame for MOVET. Defualt is 0 which is end-effector frame.

        joint or pose: we use radian and meter unit. The order of euler angle follows original z-y-x order (RPY).
        timeout or duration: we use second
        relative_frame: You can put your custome PyKDL frame variable or you can use 'self.default_frame'
        '''
        
        self.motions = {}

        ## test motions --------------------------------------------------------
        # It uses the l_gripper_push_frame
        self.motions['initTest'] = {}
        self.motions['initTest']['left'] = \
          [['MOVEJ', '[0.4447, 0.1256, 0.721, -2.12, 1.574, -0.7956, 0.8291]', 10.0],
           ['PAUSE', 1.0],
           #['MOVES', '[0.7, -0.15, -0.1, -3.1415, 0.0, 1.57]', 2.],
           ['MOVES', '[0.3, 0.45, 0.2, -3.1415, 0.0, 1.57]', 2.],
           #['MOVET', '[-0.2, 0.0, -0.1, 0.0, 0.0, 0.0, 1.0]', 5.0],
           #['MOVET', '[-0.05, 0.0, -0.1, 0.0, 0.0, 0.0, 1.0]', 2.5],
           #['MOVET', '[-0.2, 0.0, -0.1, 0.0, 0.0, 0.0, 1.0]', 3.0],
          ]
        self.motions['initTest']['right'] = []

        self.motions['scratching_knee_left'] = {}
#        self.motions['leftKnee']['left'] = \
 #         [['MOVES', '[-0.04310556,  0.07347758,  0.00485197, -2.7837531887646243, 1.5256272978351686, 1.2025216534291792]', 10., 'self.knee_left']]
        self.motions['scratching_knee_left']['left'] = \
          [['MOVES', '[-0.04310556,  0.07347758+0.05,  0.00485197, 0.48790861, -0.50380292,  0.51703901, -0.4907122]', 10., 'self.knee_left']]
        self.motions['scratching_knee_left']['right'] = []

        self.motions['reach_initialization'] = {}
        self.motions['reach_initialization']['left'] = \
          [['MOVEJ', '[0.7629304700932569, -0.3365186041095207, 0.5240000202473829, -2.003310310963515, 0.9459734129025158, -1.7128778450423763, 0.6123854412633384]', 10.0],
           ['PAUSE', 1.0],
           #['MOVES', '[0.7, -0.15, -0.1, -3.1415, 0.0, 1.57]', 2.],
           #['MOVES', '[0.3, 0.45, 0.2, -3.1415, 0.0, 1.57]', 2.],
           #['MOVET', '[-0.2, 0.0, -0.1, 0.0, 0.0, 0.0, 1.0]', 5.0],
           #['MOVET', '[-0.05, 0.0, -0.1, 0.0, 0.0, 0.0, 1.0]', 2.5],
           #['MOVET', '[-0.2, 0.0, -0.1, 0.0, 0.0, 0.0, 1.0]', 3.0],
          ]
        self.motions['reach_initialization']['right'] = []
                                                           
        rospy.loginfo("Parameters are loaded.")
        
    def serverCallback(self, req):
        task = req.data
        self.stop_motion = False
        
        if 'knee' in task.split('_') and 'left' in task.split('_'):
         
            print 'Will now interpret left knee'
          
            now = rospy.Time.now()
            rospy.sleep(1)
            self.listener.waitForTransform('/torso_lift_link', '/autobed/calf_left_link', now, rospy.Duration(5))
            print 'here!'
            now = rospy.Time.now()
            rospy.sleep(1)
            (trans, rot) = self.listener.lookupTransform('/torso_lift_link', '/autobed/calf_left_link', now)
            print trans, '\n', rot
            p = PyKDL.Vector(trans[0], trans[1], trans[2])
            M = PyKDL.Rotation.Quaternion(rot[0], rot[1], rot[2], rot[3])
            self.knee_left = PyKDL.Frame(M, p)
            # reference_B_goal = (array([-0.04310556,  0.17347758,  0.00485197]), array([ 0.48790861, -0.50380292,  0.51703901, -0.4907122 ]))
            # import tf.transformations as tft
            # tft.euler_from_quaternion([ 0.48790861, -0.50380292,  0.51703901, -0.4907122], 'szyx')
           
        self.parsingMovements(self.motions[task][self.arm_name])
        return "Completed to execute "+task

    
    def stopCallback(self, msg):
        print '\n\nAction Interrupted! Event Stop\n\n'
        print 'Interrupt Data:', msg.data
        self.stop_motion = True

        print "Stopping Motion..."
        self.setStop() #Stops Current Motion
        try:
            self.setStopRight() #Sends message to service node
        except:
            rospy.loginfo("Couldn't stop "+self.arm_name+" arm! ")



if __name__ == '__main__':

    import optparse
    p = optparse.OptionParser()
    haptic_mpc_util.initialiseOptParser(p)
    opt = haptic_mpc_util.getValidInput(p)

    # Initial variables
    d_robot    = 'pr2'
    controller = 'static'
    ## controller = 'actionlib'
    arm        = opt.arm
    tool_id    = 0
    if opt.arm == 'l': verbose = False
    else: verbose = True
        
    rospy.init_node('arm_reacher_pushing')
    ara = armReachAction(d_robot, controller, arm, tool_id, verbose)
    rospy.spin()


