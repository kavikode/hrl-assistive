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

#  \author Daehyung Park (Healthcare Robotics Lab, Georgia Tech.)

# system
import rospy, os, sys, threading, datetime
import random, numpy as np

import hrl_lib.quaternion as qt
from sklearn import preprocessing

# Utility
import hrl_lib.util as ut
from hrl_execution_monitor import anomaly_isolator_util as aiu
from hrl_execution_monitor import util as autil

#msg
from hrl_anomaly_detection.msg import MultiModality
from std_msgs.msg import String, Float64
from hrl_srvs.srv import Bool_None, Bool_NoneResponse, StringArray_None
from hrl_msgs.msg import FloatArray, StringArray

QUEUE_SIZE = 10

class anomaly_isolator:
    def __init__(self, subject_names, task_name, method, raw_data_path, save_data_path,\
                 param_dict, verbose=False):
        rospy.loginfo('Initializing anomaly detector')

        self.subject_names   = subject_names
        self.task_name       = task_name.lower()
        self.method          = method
        self.raw_data_path   = raw_data_path
        self.save_data_path  = save_data_path        
        self.verbose = verbose

        # Important containers
        self.enable_isolator = False
        self.dataList        = []
        
        # Params
        self.param_dict      = param_dict        

        # HMM, Classifier
        self.ml           = None
        self.classifier   = None

        # Comms
        self.lock = threading.Lock()        
        self.initParams()
        self.initComms()
        self.initDetector()

        if self.verbose:
            rospy.loginfo( "==========================================================")
            rospy.loginfo( "Isolator initialized!! : %s", self.task_name)
            rospy.loginfo( "==========================================================")


    def initParams(self):
        return


    def initComms(self):
        return




if __name__ == '__main__':

    ## rospy.init_node('isolator')


    print sys.argv

    ai = anomaly_isolator()
    ai.run()


    
