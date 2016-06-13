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

#  \author Daehyung Park and Zackory Erickson (Healthcare Robotics Lab, Georgia Tech.)

# system library
import time
import random
import numpy as np
import multiprocessing

# ROS library
import rospy, roslib
from roslib import message
import PyKDL

# HRL library
from hrl_srvs.srv import String_String, String_StringRequest

from tf import TransformListener
from sensor_msgs.msg import PointCloud2, CameraInfo
from visualization_msgs.msg import Marker
from geometry_msgs.msg import Point, PoseStamped, TransformStamped, PointStamped
import image_geometry
from tf2_sensor_msgs.tf2_sensor_msgs import do_transform_cloud

try :
    import sensor_msgs.point_cloud2 as pc2
except:
    import point_cloud2 as pc2

class ArmReacherClient:
    def __init__(self, isScooping=True, verbose=True):
        rospy.init_node('feed_client')
        self.tf = TransformListener()

        self.isScooping = isScooping
        self.verbose = verbose
        self.points3D = None
        self.highestBowlPoint = None
        self.initialized = False
        self.bowlRawPos = None
        self.bowlCenter = None
        self.pinholeCamera = None
        self.cameraWidth = None
        self.cameraHeight = None
        # self.torso_frame = rospy.get_param('haptic_mpc/pr2/torso_frame')

        # ROS publisher for data points
        self.publisher = rospy.Publisher('visualization_marker', Marker, queue_size=100)

        # Connect to point cloud from Kinect
        self.cloudSub = rospy.Subscriber('/head_mount_kinect/sd/points', PointCloud2, self.cloudCallback)
        if self.verbose: print 'Connected to Kinect depth'
        self.cameraSub = rospy.Subscriber('/head_mount_kinect/sd/camera_info', CameraInfo, self.cameraRGBInfoCallback)
        if self.verbose: print 'Connected to Kinect camera info'

        # Connect to bowl center location
        self.bowlSub = rospy.Subscriber('/hrl_manipulation_task/bowl_cen_pose', PoseStamped, self.bowlCallback)
        if self.verbose: print 'Connected to bowl center location'

        # Connect to both PR2 arms
        if isScooping:
            if self.verbose: print 'waiting for /arm_reach_enable'
            rospy.wait_for_service("/arm_reach_enable")
            self.armReachActionLeft  = rospy.ServiceProxy('/arm_reach_enable', String_String)
            if self.verbose: print 'waiting for /right/arm_reach_enable'
            self.armReachActionRight = rospy.ServiceProxy('/right/arm_reach_enable', String_String)
            if self.verbose: print 'Connected to both services'

    def cancel(self):
        self.cloudSub.unregister()
        self.cameraSub.unregister()
        self.bowlSub.unregister()

    def initScooping(self):
        if self.verbose: print 'Initializing arm joints for scooping'
        leftProc = multiprocessing.Process(target=self.armReachLeft, args=('initScooping1',))
        rightProc = multiprocessing.Process(target=self.armReachRight, args=('initScooping1',))
        if self.verbose:
            print 'Beginning - left arm init #1'
            t = time.time()
        leftProc.start()
        if self.verbose:
            print 'Beginning - right arm init #1'
            t2 = time.time()
        rightProc.start()
        leftProc.join()
        if self.verbose: print 'Completed - left arm init #1, time:', time.time() - t
        rightProc.join()
        if self.verbose: print 'Completed - right arm init #1, time:', time.time() - t2

        if self.verbose:
            print 'Beginning - right arm (bowl holding arm) init #2'
            t = time.time()
        self.armReachActionRight('initScooping2')
        if self.verbose:
            print 'Completed - right arm (bowl holding arm) init #2, time:', time.time() - t
            print 'Beginning - getBowPos'
            t = time.time()
        self.armReachActionLeft('getBowlPos')
        if self.verbose:
            print 'Completed - getBowPos, time:', time.time() - t
            print 'Beginning - lookAtBowl'
            t = time.time()
        self.armReachActionLeft('lookAtBowl')
        if self.verbose: print 'Completed - lookAtBowl, time:', time.time() - t

        self.initialized = True

    def run(self):
        # Don't run unless highest point in bowl has been obtained, use: "while not run(): pass"
        if self.highestBowlPoint is None:
            return False

        time.sleep(5)

        if self.verbose: print 'Beginning to scoop!'
        self.armReachActionLeft('initScooping2')
        self.armReachActionLeft('runScooping')

        return True

    def armReachLeft(self, action):
        self.armReachActionLeft(action)

    def armReachRight(self, action):
        self.armReachActionRight(action)

    def getHeadPos(self):
        self.armReachActionLeft('lookAtMouth')
        self.armReachActionLeft('getHeadPos')

    def bowlCallback(self, data):
        bowlPosePos = data.pose.position
        # Account for the fact  that the bowl center position is not directly in the center
        self.bowlRawPos = [bowlPosePos.x + 0.02, bowlPosePos.y + 0.02, bowlPosePos.z]

    def cameraRGBInfoCallback(self, data):
        if self.pinholeCamera is None:
            self.cameraWidth = data.width
            self.cameraHeight = data.height
            self.pinholeCamera = image_geometry.PinholeCameraModel()
            self.pinholeCamera.fromCameraInfo(data)

    def cloudCallback(self, data):
        # print 'Time between cloud calls:', time.time() - self.cloudTime
        # startTime = time.time()

        # Wait to obtain cloud data until after arms have been initialized
        if self.isScooping and not self.initialized:
            return

        pointCloud = data

        # Transform the raw bowl center to the Kinect frame
        if self.bowlCenter is None:
            if self.bowlRawPos is not None:
                if self.verbose: print 'Using self.bowlPosePos'
                point = PointStamped()
                point.header.frame_id = 'torso_lift_link'
                point.point.x = self.bowlRawPos[0]
                point.point.y = self.bowlRawPos[1]
                point.point.z = self.bowlRawPos[2]
                # self.publishPoints('bowlCenterPre', [], g=1.0, frame='torso_lift_link')
                point = self.tf.transformPoint('head_mount_kinect_ir_optical_frame', point)
                self.bowlCenter = np.array([point.point.x, point.point.y, point.point.z])
            else:
                if self.verbose: print 'Using self.getBowlFrame()'
                # bowlPos = self.armReachActionLeft('returnBowlPos')
                bowlPos = self.getBowlFrame()
                self.bowlCenter = np.array([bowlPos.p.x(), bowlPos.p.y(), bowlPos.p.z()])
            self.publishPoints('bowlCenterPost', [self.bowlCenter], r=1.0)

        # Project bowl position to 2D pixel location to narrow search for bowl points (use point projected to kinect frame)
        bowlProjX, bowlProjY = [int(x) for x in self.pinholeCamera.project3dToPixel(self.bowlCenter)]
        print '3D bowl point:', self.bowlCenter, 'Projected X, Y:', bowlProjX, bowlProjY, 'Camera width, height:', self.cameraWidth, self.cameraHeight
        points2D = [[x, y] for y in xrange(bowlProjY-50, bowlProjY+50) for x in xrange(bowlProjX-50, bowlProjX+50)]
        print 'points2D'
        print np.shape(points2D)
        try:
            points3D = pc2.read_points(pointCloud, field_names=('x', 'y', 'z'), skip_nans=True, uvs=points2D)
        except:
            print 'Unable to unpack from PointCloud2!'
            return

        # print 'points3D'
        # print np.shape([x for x in points3D])
        t = time.time()

        # X, Y Positions must be within a radius of 5 cm from the bowl center, and Z positions must be within 4 cm of center
        # TODO: This could be sped up by restricting to a 2D window in the point cloud (uvs=points2D)
        self.points3D = np.array([point for point in points3D if np.linalg.norm(self.bowlCenter[:2] - np.array(point[:2])) < 0.04 and abs(self.bowlCenter[2] - point[2]) < 0.04])
        # self.points3D = np.array([point for point in points3D])

        print 'Time to determine points near bowl center:', time.time() - t

        # Find the highest point (based on Z axis value) that is within the bowl. Positive Z is facing towards the floor, so find the min Z value
        if self.verbose: print 'points3D:', np.shape(self.points3D)
        maxIndex = self.points3D[:, 2].argmin()
        self.highestBowlPoint = self.points3D[maxIndex]

        # Publish highest bowl point and all 3D points in bowl
        self.publishPoints('highestPoint', [self.highestBowlPoint], size=0.004, r=.5, b=.5)
        self.publishPoints('allPoints', self.points3D, g=0.6, b=1.0)

    def getBowlFrame(self):
        # Get frame info from right arm and upate bowl_pos

        # 1. right arm ('r_gripper_tool_frame') from tf
        self.tf.waitForTransform(self.torso_frame, 'r_gripper_tool_frame', rospy.Time(0), rospy.Duration(5.0))
        [pos, quat] = self.tf.lookupTransform(self.torso_frame, 'r_gripper_tool_frame', rospy.Time(0))
        p = PyKDL.Vector(pos[0], pos[1], pos[2])
        M = PyKDL.Rotation.Quaternion(quat[0], quat[1], quat[2], quat[3])

        # 2. add offset to called TF value. Make sure Orientation is up right.
        ## Off set : 11 cm x direction, - 5 cm z direction.
        pos_offset = rospy.get_param('hrl_manipulation_task/sub_ee_pos_offset')
        orient_offset = rospy.get_param('hrl_manipulation_task/sub_ee_orient_offset')

        p = p + M * PyKDL.Vector(pos_offset['x'], pos_offset['y'], pos_offset['z'])
        M.DoRotX(orient_offset['rx'])
        M.DoRotY(orient_offset['ry'])
        M.DoRotZ(orient_offset['rz'])

        if self.verbose: print 'Bowl frame:', p

        return PyKDL.Frame(M, p)

    def publishPoints(self, name, points, size=0.002, r=0.0, g=0.0, b=0.0, a=1.0, frame='head_mount_kinect_ir_optical_frame'):
        marker = Marker()
        marker.header.frame_id = frame
        marker.ns = name
        marker.type = marker.POINTS
        marker.action = marker.ADD
        marker.scale.x = size
        marker.scale.y = size
        marker.color.a = a
        marker.color.r = r
        marker.color.g = g
        marker.color.b = b
        for point in points:
            p = Point()
            p.x, p.y, p.z = point
            marker.points.append(p)
        self.publisher.publish(marker)


if __name__ == '__main__':
    scooping = False
    client = ArmReacherClient(scooping, verbose=True)

    if scooping:
        client.initScooping()
        print 'Beginning - left arm init #2'
        t1 = time.time()
        client.armReachActionLeft('initScooping2')
        print 'Completed - left arm init #2, time:', time.time() - t1
        print 'Beginning - scooping'
        t1 = time.time()
        client.armReachActionLeft('runScoopingCenter')
        # client.armReachActionLeft('runScoopingRight')
        print 'Completed - scooping, time:', time.time() - t1

    time.sleep(60)

    # while not client.run():
    #     pass
    client.cancel()

    # if True:
    #     print 'Detecting AR tag on head'
    #     print armReachActionLeft('lookAtMouth')
    #     print armReachActionLeft("getHeadPos")
    #     sys.exit()
    #
    #
    # ## Scooping -----------------------------------
    # if True:
    #     # print armReachActionLeft("initScooping1")
    #     # print armReachActionRight("initScooping1")
    #
    #     pass
    #     # sys.exit()
    #
    # ## Feeding -----------------------------------
    # if True:
    #     leftProc = multiprocessing.Process(target=armReachLeft, args=('initFeeding',))
    #     rightProc = multiprocessing.Process(target=armReachRight, args=('initFeeding',))
    #     # headProc = multiprocessing.Process(target=getHeadPos) # TODO: Make a new service this!
    #     leftProc.start()
    #     rightProc.start()
    #     # headProc.start()
    #     leftProc.join()
    #     rightProc.join()
    #     # headProc.join()
    #
    #     # print 'Initializing both arms for feeding and detecting the user\'s head'
    #     # print armReachActionLeft("initFeeding")
    #     # print armReachActionRight("initFeeding")
    #
    #     # print "Detect ar tag on the head"
    #     print armReachActionLeft('lookAtMouth')
    #     print armReachActionLeft("getHeadPos")
    #     # ut.get_keystroke('Hit a key to proceed next')
    #
    #     print "Running feeding!"
    #     print armReachActionLeft("runFeeding1")
    #     print armReachActionLeft("runFeeding2")
    #
    # cloudSub.unregister()

