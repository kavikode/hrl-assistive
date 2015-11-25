#!/usr/bin/env python

# system library
import time
import datetime

# ROS library
import rospy
import roslib
roslib.load_manifest('hrl_multimodal_anomaly_detection')

# HRL library
## from hrl_srvs.srv import None_Bool, None_BoolResponse
from hrl_multimodal_anomaly_detection.srv import String_String
import hrl_lib.util as ut


if __name__ == '__main__':

    rospy.init_node('feed_client')

    rospy.wait_for_service("/arm_reach_enable")
    armReachAction = rospy.ServiceProxy("/arm_reach_enable", String_String)
    #armMovements = rospy.ServiceProxy("/arm_reach_enable", None_Bool)

    ## ret = armReachAction()
    ## #ret = armMovements()
    ## print ret

    ## Scooping -----------------------------------    
    print "Initializing left arm for scooping"
    print armReachAction("leftArmInitScooping")

    print armReachAction("chooseManualBowlPos")
    ut.get_keystroke('Hit a key to proceed next')        

    print 'Initializing scooping'
    print armReachAction('initArmScooping')

    print "Running scooping!"
    print armReachAction("runScooping")
    time.sleep(2.0)    


    ## Feeding -----------------------------------
    print "Initializing left arm for feeding"
    print armReachAction("leftArmInitFeeding")

    print armReachAction("chooseManualHeadPos")

    print 'Initializing feeding'
    print armReachAction('initArmFeeding')
    time.sleep(2.0)    
    ## ut.get_keystroke('Hit a key to proceed next')        

    print "Running feeding!"
    print armReachAction("runFeeding")
    







    ## t1 = datetime.datetime.now()
    ## t2 = datetime.datetime.now()
    ## t  = t2-t1
    ## print "time delay: ", t.seconds
    
