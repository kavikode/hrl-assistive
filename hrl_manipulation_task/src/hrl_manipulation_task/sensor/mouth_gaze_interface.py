#! /usr/bin/env python

# Will take in "kinect" or "wrist" as command line argument to specify camera.
# No argument will default to wrist.
#
# Text box will be different colors depending on condition.
#   Orange: Conditions not met
#   Green: Conditions met
#
# Detection of whether mouth is open considers both the distance between lips and
# the area of the mouth relative to the face area.
#
# Gaze detection splits the right eye into 3 areas and
# compares the darkness of the three areas.
# Only performed when head is not rotated.
# Right eye is checked first, and if result is 'unknown', left eye is checked.
#
# Head rotation is detected by comparing the position of the
# corners of mouth with the edge of the cheek.


import sys
import dlib
import numpy as np

import rospy
from std_msgs.msg import String, Bool
from sensor_msgs.msg import Image
from hrl_msgs.msg import StringArray

import cv2
from cv_bridge import CvBridge, CvBridgeError

import time
import math

import argparse

from sound_play.libsoundplay import SoundClient

# dlib colors
yellow = dlib.rgb_pixel(255, 255, 0)
red = dlib.rgb_pixel(255, 0, 0)
green = dlib.rgb_pixel(0, 255, 0)
blue = dlib.rgb_pixel(0, 0, 255)
orange = dlib.rgb_pixel(255, 157, 20)

# cv2 colors (rgb)
cv2_white = (255, 255, 255)
cv2_black = (0, 0, 0)
cv2_yellow = (255, 255, 0)
cv2_blue = (0, 0, 255)
cv2_green = (0, 255, 0)
cv2_orange = (255, 157, 20)

QUEUE_SIZE = 10

class DlibFaceLandmarkDetector:

    def __init__(self, img_topic='/SR300/rgb/image_raw'):
        # Make window.
        self.win = dlib.image_window()

        # Subscribe to image topic.
        self.img_topic = img_topic
        self.image_sub = rospy.Subscriber(self.img_topic, Image, self.callback)

        # Bridge
        self.bridge = CvBridge()
        
        # Load detector.
        self.detector = dlib.get_frontal_face_detector()
        self.predictor = dlib.shape_predictor('./detector_tools/shape_predictor_68_face_landmarks.dat')

        # Use when detecting faces every 4 frames.
        self.count = 0
        self.dets = None
        if self.img_topic == '/SR300/rgb/image_raw':
            self.frame_num = 2
        else:
            self.frame_num = 4

        # Use to print number of detected faces only when number detected changes.
        self.prev = 0

        # True when both mouth and eye conditions are met.
        self.conditions_met = False
        self.outliers = 0

        # Timer
        self.timer_started = False
        self.start_time = None

        # Scoop/stop tools
        self.stop_condition = False
        self.stop_timer = None
        self.stop_outliers = 0
        self.scoop_condition = False
        self.scoop_timer = None
        self.scoop_outliers = 0

        # Publisher/subscriber
        self.imagePub = rospy.Publisher("/hrl_manipulation_task/mouth_gaze_detector", Image, queue_size=10)
        self.statusPub = rospy.Publisher("/manipulation_task/status", String, queue_size=1)
        self.guiStatusPub = rospy.Publisher("/manipulation_task/gui_status", String, queue_size=1, latch=True)
        self.availablePub = rospy.Publisher("/manipulation_task/available", String, queue_size=QUEUE_SIZE)
        self.emergencyPub = rospy.Publisher("/manipulation_task/emergency", String, queue_size=QUEUE_SIZE)
        self.userInputPub = rospy.Publisher("/manipulation_task/user_input", String, queue_size=QUEUE_SIZE)
        self.feed_message_published = False
        self.gui_status = ''
        rospy.Subscriber("/manipulation_task/gui_status", String, self.guiCallback, queue_size=1)

        # Sound
        self.sound_handle = SoundClient()

        # TODO: testing when head becomes inavailable
        # self.head_motion -> shows how the head is moving?
        # still, to straight, to left, to right
        self.head_motion = ''
        self.prev_head_status = ''
        self.prev_head_ratio = 0.0


    def guiCallback(self, msg):
        self.gui_status = msg.data



    def callback(self, data):
        nodded = False
        shaken = False
        # TODO
        corrected = False
        # Convert sensor_msgs/Image to rgb.
        img = self.bridge.imgmsg_to_cv2(data, 'rgb8')

        # Flip image
        if self.img_topic == '/SR300/rgb/image_raw':
            img = cv2.flip(img, 0)
            img = cv2.flip(img, 1)

        # Make image half the size of original (speedup).
        h, w, c = img.shape
        big_img = img
        img = cv2.resize(img, (w/2, h/2))  # 320x240 for Kinect
        
        # TODO
        #if self.img_topic == '/SR300/rgb/image_raw':
        #    img = img[0:400, 0:640]
        
        # Grayscale (speedup)
        gray_img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

        # Display image.
        #self.win.set_image(img)

        # Text string describing status.
        status = ''
        console_status = ''

        # Detect face every 4 frames (speedup).
        if (self.count%self.frame_num) == 0:
            self.dets = self.detector(gray_img, 1)
            if len(self.dets)>=1:
                if len(self.dets) != self.prev:
                    print '---------------DETECTED ' + str(len(self.dets)) + ' FACE(S)---------------'
                    self.prev = len(self.dets)
            else:
                # TODO: added two lines below for testing cases when head is not detected but still in frame
                head_status = self.prev_head_status
                ratio = self.prev_head_ratio
                if len(self.dets) != self.prev:
                    print '----------------NO FACE DETECTED----------------'
                    self.prev = len(self.dets)
                    self.win.clear_overlay()
            self.count += 1
        else:
            self.count += 1
        head_status = self.prev_head_status
        ratio = self.prev_head_ratio

        # Stop condition check
        #if ratio > 2.5 and mouth_open:
        if ratio > 2.5:
            self.stop_outliers = 0
            if self.stop_condition:
                elapsed = time.time() - self.stop_timer
                if elapsed > 3.0:
                    if (self.gui_status == 'in motion') or (self.gui_status == 'wait start'):
                        self.emergencyPub.publish('STOP')
                        print 'stopping command published'
                        self.sound_handle.say('Stop ing')
                        print 'said stopping'
            else:
                print 'stop timer started'
                self.stop_timer = time.time()
                self.stop_condition = True
        elif self.stop_outliers <= 5:
            self.stop_outliers += 1
        else:
            self.stop_condition = False

        

        if self.dets == None:
            self.win.set_image(img)
            self.imagePub.publish(self.bridge.cv2_to_imgmsg(img, "rgb8"))

        # Detect landmarks.
        if not self.dets == None:
            # Find largest face.
            largest_area = 0
            largest_box = None
            for k, d in enumerate(self.dets):
                if d.area() > largest_area:
                    largest_area = d.area()
                    largest_box = d

#-----do stuff to face from here-------------------------------------------------------------------------
            try:
                # Landmarks for only largest face.
                nodded = False
                shape = self.predictor(gray_img, largest_box)
                # Correction for when face is "squished"
                if d.bottom() > shape.part(8).y-5:
                    largest_box = dlib.rectangle(largest_box.left(), largest_box.top()+10, largest_box.right(), largest_box.bottom()+10)
                    shape = self.predictor(gray_img, largest_box)
                    corrected = True

                # Mouth open check.
                mouth_open = self.lips_open(shape, largest_area)
                if mouth_open:
                    status += 'OPEN'
                    console_status += 'Mouth open'
                else:
                    console_status += 'Mouth closed'

                # Head rotated check.
                head_rotated, head_status, ratio = self.is_head_rotated(shape)

                # TODO:
                if len(self.dets) < 1:
                    head_status = self.prev_head_status
                    ratio = self.prev_head_ratio

                

                # Scoop condition check
                if ratio < 0.4 and mouth_open:
                    self.scoop_outliers = 0
                    if self.scoop_condition:
                        elapsed = time.time() - self.scoop_timer
                        if elapsed > 3.0:
                            if (self.gui_status == 'select task') or (self.gui_status == 'stopped'):
                                self.statusPub.publish('Scooping')
                                self.availablePub.publish('true')
                                self.userInputPub.publish('Start')
                                print 'scooping command published'
                                self.sound_handle.say('Scoop ing')
                                print 'said scooping'
                            elif self.gui_status == 'wait start':
                                self.userInputPub.publish('Start')
                    else:
                        print 'scoop timer started'
                        self.scoop_timer = time.time()
                        self.scoop_condition = True
                elif self.scoop_outliers <= 5:
                    self.scoop_outliers += 1
                else:
                    self.scoop_condition = False


                # Gaze detection only if head is not rotated.
                '''
                if head_rotated:
                    eyes_straight = False
                    console_status += ', head {}'.format(head_status)
                    eye_string = ''
                    #print 'head rotated'
                else:
                    console_status += ', head {}'.format(head_status)
                    try:
                        eyes_straight, eye_string = self.detect_gaze(shape, gray_img)
                        if eyes_straight and mouth_open:
                            console_status += (', gaze: ' + eye_string)
                            status += ', STRAIGHT'
                        elif eyes_straight:
                            console_status += (', gaze: ' + eye_string)
                            status += 'STRAIGHT'
                        elif not eyes_straight:
                            console_status += (', gaze: ' + eye_string)
                    # Will throw ZeroDivisionErrors and occasional AttributeError (no attribute part???).
                    except:
                        eyes_straight = False
                        eye_string = 'failed'
                        console_status += ', gaze detection failed'
                '''

                # If head straight, gaze straight.
                if head_rotated:
                    eyes_straight = False
                    console_status += ', eyes not straight'
                else:
                    eyes_straight = True
                    console_status += ', eyes straight'
                
                # -----------------------------------------------------------------
                # Update conditions_met bool.
                # Allow 4 consecutive outliers for gaze detection.
                if mouth_open and eyes_straight:
                    self.conditions_met = True
                    self.outliers = 0
                elif self.conditions_met and mouth_open and (self.outliers < 5):
                    self.outliers += 1
                    status = 'OPEN, STRAIGHT'
                else:
                    self.conditions_met = False
                    self.outliers = 0
   
                # Text box coordinates
                left = largest_box.left()
                top = largest_box.top()
                right = largest_box.right()
                bottom = largest_box.bottom()

                # Check if three seconds have passed while conditions were continuously met.
                color = None
                if (self.conditions_met) and (not self.timer_started):  # conditions_met: False -> True.
                    print 'feeding timer started'
                    self.start_time = time.time()
                    self.timer_started = True
                    cv2.rectangle(img, (left, top-15), (left+135, top), cv2_green, -1)
                    cv2.putText(img, status, (left+2, top-2), cv2.FONT_HERSHEY_PLAIN, 1, cv2_black)
                    color = green
                elif (self.conditions_met) and (self.timer_started):  # conditions_met: True -> True, >= 3 secs
                    if (time.time() - self.start_time) >= 3.0:
                        cv2.rectangle(img, (left, top-15), (left+135, top), cv2_green, -1)
                        cv2.putText(img, status, (left+2, top-2), cv2.FONT_HERSHEY_PLAIN, 1, cv2_black)
                        cv2.putText(img, '3 seconds passed!', (2, 230), cv2.FONT_HERSHEY_PLAIN, 2, cv2_green, 2)
                        color = green
                        if (self.gui_status == 'select task') or (self.gui_status == 'stopped'):
                            self.statusPub.publish('Feeding')
                            self.availablePub.publish('true')
                            self.userInputPub.publish('Start')
                            print 'Feeding command published'
                            self.sound_handle.say('feed ing')
                            print 'said feeding'
                        elif self.gui_status == 'wait start':
                            self.userInputPub.publish('Start')
                    else:  # conditions_met: True -> True, < 3 secs
                        cv2.rectangle(img, (left, top-15), (left+135, top), cv2_green, -1)
                        cv2.putText(img, status, (left+2, top-2), cv2.FONT_HERSHEY_PLAIN, 1, cv2_black)
                        color = green
                else:  # conditions_met: False
                    cv2.rectangle(img, (left, top-15), (left+135, top), cv2_orange, -1)
                    cv2.putText(img, status, (left+2, top-2), cv2.FONT_HERSHEY_PLAIN, 1, cv2_black)
                    color = orange
                    self.timer_started = False
                self.win.set_image(img)
                self.win.clear_overlay()
                self.imagePub.publish(self.bridge.cv2_to_imgmsg(img, "rgb8"))

                self.prev_head_status = head_status
                self.prev_head_ratio = ratio
                

                # Uncomment to print head+mouth status to command line.
                #print '{}'.format(console_status)
                #print ''
                #print head_status

                #self.eyes_prev = eye_string
   
            except TypeError:
                self.win.set_image(img)
                self.imagePub.publish(self.bridge.cv2_to_imgmsg(img, "rgb8"))
                print head_status
                #print 'landmarks not detected'
                pass
            # Uncomment to add rectangle around face.
            #self.win.add_overlay(self.dets)

        #else:
        #    self.win.set_image(img)


    def lips_open(self, shape, face_area):
        """Determine whether mouth is open."""
        # r_diff is the height of opening of right side of mouth
        r_diff = shape.part(67).y - shape.part(61).y
        c_diff = shape.part(66).y - shape.part(62).y
        l_diff = shape.part(65).y - shape.part(63).y
        mouth_height = ((c_diff >= 5) and (r_diff >= 3) and (l_diff >= 3))
        mouth_area = self.mouth_area_ratio(shape, face_area) > 1.3
        # Consider both distance between inner lips and area of mouth.
        # This helps detect open mouth when the face is small
        if mouth_height or mouth_area:
            return True
        else:
            return False


    def mouth_shape_ratio(self, shape):
        """Return percentage of height of mouth w.r.t. width of mouth."""
        height = np.absolute(float(shape.part(66).y)-float(shape.part(62).y))
        width = np.absolute(float(shape.part(64).x)-float(shape.part(60).x))
        # Prevent div by 0 errors.
        if width > 0.0:
            return (height/width)*100
        else:
            return 0


    def mouth_area_ratio(self, shape, face_area):
        """Return percentage of mouth area w.r.t face area."""
        mouth = self.mouth_area(shape)
        if face_area > 0:
            return (mouth/face_area)*100
        else:
            return 0

    def mouth_area(self, shape):
        """Calculate area of the mouth between inner lips."""
        # Make two vectors for each triangle.
        v1 = [shape.part(61).x-shape.part(60).x, shape.part(62).y-shape.part(60).y]
        v2 = [shape.part(67).x-shape.part(60).x, shape.part(67).y-shape.part(60).y]

        v3 = [shape.part(63).x-shape.part(61).x, shape.part(63).y-shape.part(61).y]
        v4 = [shape.part(67).x-shape.part(61).x, shape.part(67).y-shape.part(61).y]

        v5 = [shape.part(63).x-shape.part(65).x, shape.part(63).y-shape.part(65).y]
        v6 = [shape.part(67).x-shape.part(65).x, shape.part(67).y-shape.part(65).y]

        v7 = [shape.part(63).x-shape.part(64).x, shape.part(63).y-shape.part(64).y]
        v8 = [shape.part(65).x-shape.part(64).x, shape.part(65).y-shape.part(64).y]

        # Calculate area using cross product.
        tri1 = np.absolute(np.cross(v1, v2))*0.5
        tri2 = np.absolute(np.cross(v3, v4))*0.5
        tri3 = np.absolute(np.cross(v5, v6))*0.5
        tri4 = np.absolute(np.cross(v7, v8))*0.5

        return tri1+tri2+tri3+tri4


    def get_dist(self, pt1, pt2):
        """Return distance between two 'point's."""
        return math.sqrt((pt1.x - pt2.x)**2 + (pt1.y - pt2.y)**2)


    def is_head_rotated(self, shape):
        """Determine whether head is rotated."""
        # Compares distance between corner of mouth and edge of cheek.
        dist1 = self.get_dist(shape.part(48), shape.part(4))
        dist2 = self.get_dist(shape.part(54), shape.part(12))
        if dist2 > 0.0:
            ratio = dist1/dist2
        else: ratio = 0
        if ratio > 1.6:
            return True, 'right', ratio
        elif ratio < 0.625:
            return True, 'left', ratio
        else:
            return False, 'straight', ratio


    def detect_gaze(self, shape, gray_img, h=1, side='right'):
        """Return True if person if looking straight."""

        # Set landmark points for eye.
        pt1 = 36
        pt2 = 41
        pt3 = 40
        pt4 = 39
        if side == 'left':
            pt1 = 42
            pt2 = 47
            pt3 = 46
            pt4 = 45
        
        # x1, y1 are top left coordinates, x2, y2 are bottom right coordinates.
        x1 = shape.part(pt1).x
        y1 = shape.part(pt1).y
        x2 = shape.part(pt4).x
        y2 = max(shape.part(pt2).y, shape.part(pt3).y)
        
        # Locate bottom half of eye.
        temp = gray_img[y1:y2, x1:x2]

        # Uncomment to increase contrast.
        #temp = self.contrast(temp)

        # Resize so that height for half eye will be 60 px.
        k = 60.0/temp.shape[0]
        new_h = int(round(temp.shape[0]*k))
        new_w = int(round(temp.shape[1]*k))
        sample = cv2.resize(temp, (new_w, new_h))

        # Width for each of the three sections (right, center, left).
        a = int(round((shape.part(pt2).x - shape.part(pt1).x) * k))
        b = int(round((shape.part(pt3).x - shape.part(pt2).x) * k))
        c = int(round((shape.part(pt4).x - shape.part(pt3).x) * k))
 
        tot_a = 0.0
        tot_b = 0.0
        tot_c = 0.0

        # Find average pixel value for each region.
        for y in range(0, h):    
            for x in range(0, a):
                tot_a = tot_a + sample[y, x]
            for x in range(a, a+b):
                tot_b = tot_b + sample[y, x]
            for x in range(a+b, a+b+c):
                tot_c = tot_c + sample[y, x]

        avg_a = tot_a/(10*a)
        avg_b = tot_b/(10*b)
        avg_c = tot_c/(10*c)

        # Determine if eye is looking straight.
        # If unknown and eye was right eye, check left eye.
        # If left eye is also unknown, return unknown. 
        if (avg_a > avg_b) and (avg_c > avg_b):
            #print 'straight'
            return True, 'straight'
        elif (avg_a < avg_b) and (avg_a < avg_c):
            #print '<-'
            return False, '<-'
        elif (avg_c < avg_a) and (avg_a < avg_b):
            #print '->'
            return False, '->'
        elif side=='right':
            return self.detect_gaze(self, shape, gray_img, side='left')
        else:
            #print 'unknown'
            return False, 'unknown'


    def contrast(self, img, alpha=2.2, beta=0):
        h, w = img.shape
        new_img = np.zeros((h, w), dtype=np.uint8)
        for x in range(0, w):
            for y in range(0, h):
                    pix = (alpha * img[y, x]) + beta
                    #pix = (self.alpha * gray[y, x])
                    pix = int(pix)
                    if pix > 255:
                        pix = 255
                    new_img[y, x] = pix
        return new_img


    def is_smiling(self, shape):
        horizontal = abs(shape.part(54).x - shape.part(48).x)
        vertical = abs(shape.part(57).y - shape.part(51).y)
        if vertical > 0.0:
            ratio = float(horizontal) / float(vertical)
        else:
            ratio = 0.0
        return (ratio > 4.0), ratio        


def main(args):
    # Can specify to use kinect camera or wrist mounted (SR300) camera.
    if len(sys.argv) == 2:
        if sys.argv[1] == 'kinect':
            thing = DlibFaceLandmarkDetector(img_topic='/camera/rgb/image_raw')
        elif sys.argv[1] == 'wrist':
            thing = DlibFaceLandmarkDetector()
        else:
            print 'Invalid arugment. Please specify "kinect" or "wrist". Default is wrist.'
            sys.exit()       
    elif len(sys.argv) == 1:
        thing = DlibFaceLandmarkDetector()
    else:
        print 'Invalid argument. Please specify "kinect" or "wrist". Default is wrist.'
        sys.exit()

    rospy.init_node('mouth_gaze_interface', anonymous=True)
    try:
        rospy.spin()
        thing.debug_file.close()
    except:
        pass

if __name__ == '__main__':
    main(sys.argv)
