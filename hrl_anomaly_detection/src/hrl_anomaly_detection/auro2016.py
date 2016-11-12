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

# system & utils
import os, sys, copy, random
import numpy as np
import scipy
from joblib import Parallel, delayed
import hrl_lib.util as ut

# Private utils
from hrl_anomaly_detection.util import *
from hrl_anomaly_detection.util_viz import *
from hrl_anomaly_detection import data_manager as dm
from hrl_anomaly_detection.AURO2016_params import *
## from hrl_anomaly_detection.optimizeParam import *
from hrl_anomaly_detection import util as util

# Private learners
from hrl_anomaly_detection.hmm import learning_hmm as hmm
import hrl_anomaly_detection.classifiers.classifier as cf
import hrl_anomaly_detection.data_viz as dv

# visualization
import matplotlib
#matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from matplotlib import gridspec
import itertools
colors = itertools.cycle(['g', 'm', 'c', 'k', 'y','r', 'b', ])
shapes = itertools.cycle(['x','v', 'o', '+'])

matplotlib.rcParams['pdf.fonttype'] = 42
matplotlib.rcParams['ps.fonttype'] = 42 
random.seed(3334)
np.random.seed(3334)



def evaluation_all(subject_names, task_name, raw_data_path, processed_data_path, param_dict,\
                   data_renew=False, save_pdf=False, verbose=False, debug=False,\
                   no_plot=False, delay_plot=True, find_param=False, data_gen=False):

    ## Parameters
    # data
    data_dict  = param_dict['data_param']
    data_renew = data_dict['renew']
    # HMM
    HMM_dict   = param_dict['HMM']
    nState     = HMM_dict['nState']
    cov        = HMM_dict['cov']
    add_logp_d = HMM_dict.get('add_logp_d', False)
    # SVM
    SVM_dict   = param_dict['SVM']

    # ROC
    ROC_dict = param_dict['ROC']

    # parameters
    startIdx    = 4
    method_list = ROC_dict['methods'] 
    nPoints     = ROC_dict['nPoints']
    
    #------------------------------------------

   
    if os.path.isdir(processed_data_path) is False:
        os.system('mkdir -p '+processed_data_path)

    crossVal_pkl = os.path.join(processed_data_path, 'cv_'+task_name+'.pkl')
    
    if os.path.isfile(crossVal_pkl) and data_renew is False and data_gen is False:
        print "CV data exists and no renew"
        d = ut.load_pickle(crossVal_pkl)
        kFold_list = d['kFoldList'] 
        successData = d['successData']
        failureData = d['failureData']        
    else:
        '''
        Use augmented data? if nAugment is 0, then aug_successData = successData
        '''        
        d = dm.getDataLOPO(subject_names, task_name, raw_data_path, \
                           processed_data_path, data_dict['rf_center'], data_dict['local_range'],\
                           downSampleSize=data_dict['downSampleSize'], scale=1.0,\
                           handFeatures=data_dict['handFeatures'], \
                           cut_data=data_dict['cut_data'], \
                           data_renew=data_renew, max_time=data_dict['max_time'])
        successData, failureData, success_files, failure_files, kFold_list \
          = dm.LOPO_data_index(d['successDataList'], d['failureDataList'],\
                               d['successFileList'], d['failureFileList'])

        d['successData']   = successData
        d['failureData']   = failureData
        d['kFoldList']     = kFold_list
        ut.save_pickle(d, crossVal_pkl)
        if data_gen: sys.exit()

    #-----------------------------------------------------------------------------------------
    param_dict2 = d['param_dict']
    if 'timeList' in param_dict2.keys():
        timeList    = param_dict2['timeList'][startIdx:]
    else: timeList = None

    if 'progress_diag' in method_list: diag = True
    else: diag = False

    #-----------------------------------------------------------------------------------------    
    # Training HMM, and getting classifier training and testing data
    dm.saveHMMinducedFeatures(kFold_list, successData, failureData,\
                              task_name, processed_data_path,\
                              HMM_dict, data_renew, startIdx, nState, cov, scale, \
                              noise_mag=0.03, diag=diag, \
                              add_logp_d=add_logp_d, verbose=verbose)

    #-----------------------------------------------------------------------------------------
    roc_pkl = os.path.join(processed_data_path, 'roc_'+task_name+'.pkl')

    if os.path.isfile(roc_pkl) is False or HMM_dict['renew'] or SVM_dict['renew']: ROC_data = {}
    else: ROC_data = ut.load_pickle(roc_pkl)
    ROC_data = util.reset_roc_data(ROC_data, method_list, ROC_dict['update_list'], nPoints)

    osvm_data = None ; bpsvm_data = None
    if 'osvm' in method_list  and ROC_data['osvm']['complete'] is False:
        osvm_data = dm.getPCAData(len(kFold_list), crossVal_pkl, \
                                  window=SVM_dict['raw_window_size'],
                                  use_test=True, use_pca=False )

    # parallelization
    if debug: n_jobs=1
    else: n_jobs=-1
    l_data = Parallel(n_jobs=n_jobs, verbose=10)(delayed(cf.run_classifiers)( idx, processed_data_path, \
                                                                         task_name, \
                                                                         method, ROC_data, \
                                                                         ROC_dict, \
                                                                         SVM_dict, HMM_dict, \
                                                                         raw_data=(osvm_data,bpsvm_data),\
                                                                         startIdx=startIdx, nState=nState) \
                                                                         for idx in xrange(len(kFold_list)) \
                                                                         for method in method_list )


    print "finished to run run_classifiers"
    ROC_data = util.update_roc_data(ROC_data, l_data, nPoints, method_list)
    ut.save_pickle(ROC_data, roc_pkl)

    #-----------------------------------------------------------------------------------------
    ## best_param_idx = getBestParamIdx(method_list, ROC_data, nPoints, verbose=False)
    ## scores, delays = cost_info(best_param_idx, method_list, ROC_data, nPoints, \
    ##                            timeList=timeList, verbose=False)

    
    # ---------------- ROC Visualization ----------------------
    roc_info(method_list, ROC_data, nPoints, no_plot=True)


def evaluation_unexp(subject_names, task_name, raw_data_path, processed_data_path, param_dict,\
                     data_renew=False, save_pdf=False, verbose=False, debug=False,\
                     no_plot=False, delay_plot=True, find_param=False, data_gen=False):
    """Get a list of failures that executin monitoring systems cannot detect."""

    ## Parameters
    # data
    data_dict  = param_dict['data_param']
    data_renew = data_dict['renew']
    # HMM
    HMM_dict   = param_dict['HMM']
    nState     = HMM_dict['nState']
    scale      = HMM_dict['scale']
    cov        = HMM_dict['cov']
    add_logp_d = HMM_dict.get('add_logp_d', False)
    # SVM
    SVM_dict   = param_dict['SVM']

    # ROC
    ROC_dict = param_dict['ROC']

    # parameters
    startIdx    = 4
    method_list = ROC_dict['methods'] 
    nPoints     = ROC_dict['nPoints']
    
    #------------------------------------------

   
    if os.path.isdir(processed_data_path) is False:
        os.system('mkdir -p '+processed_data_path)

    crossVal_pkl = os.path.join(processed_data_path, 'cv_'+task_name+'.pkl')
    
    if os.path.isfile(crossVal_pkl) and data_renew is False and data_gen is False:
        print "CV data exists and no renew"
        d = ut.load_pickle(crossVal_pkl)
        print d.keys()
        kFold_list  = d['kFoldList']
        successData = d['successData']
        failureData = d['failureData']
        success_files = d['success_files']
        failure_files = d['failure_files']
    else:
        '''
        Use augmented data? if nAugment is 0, then aug_successData = successData
        '''
        # Get a data set with a leave-one-person-out
        print "Extract data using getDataLOPO"
        d = dm.getDataLOPO(subject_names, task_name, raw_data_path, \
                           processed_data_path, data_dict['rf_center'], data_dict['local_range'],\
                           downSampleSize=data_dict['downSampleSize'], scale=1.0,\
                           handFeatures=data_dict['handFeatures'], \
                           cut_data=data_dict['cut_data'], \
                           data_renew=data_renew, max_time=data_dict['max_time'])
        successData, failureData, success_files, failure_files, kFold_list \
          = dm.LOPO_data_index(d['successDataList'], d['failureDataList'],\
                               d['successFileList'], d['failureFileList'])

        d['successData']   = successData
        d['failureData']   = failureData
        d['success_files'] = success_files
        d['failure_files'] = failure_files
        d['kFoldList']     = kFold_list
        ut.save_pickle(d, crossVal_pkl)
        if data_gen: sys.exit()


    param_dict2  = d['param_dict']
    if 'timeList' in param_dict2.keys():
        timeList    = param_dict2['timeList'][startIdx:]
    else: timeList = None

    #-----------------------------------------------------------------------------------------
    # HMM-induced vector with LOPO
    dm.saveHMMinducedFeatures(kFold_list, successData, failureData,\
                              task_name, processed_data_path,\
                              HMM_dict, data_renew, startIdx, nState, cov, scale, \
                              success_files=success_files, failure_files=failure_files,\
                              add_logp_d=add_logp_d, verbose=verbose)
                              
    #-----------------------------------------------------------------------------------------
    roc_pkl = os.path.join(processed_data_path, 'roc_'+task_name+'.pkl')
    if os.path.isfile(roc_pkl) is False or HMM_dict['renew'] or SVM_dict['renew']: ROC_data = {}
    else: ROC_data = ut.load_pickle(roc_pkl)
    ROC_data = util.reset_roc_data(ROC_data, method_list, ROC_dict['update_list'], nPoints)

    osvm_data = None ; bpsvm_data = None
    if 'osvm' in method_list  and ROC_data['osvm']['complete'] is False:
        osvm_data = dm.getPCAData(len(kFold_list), crossVal_pkl, \
                                  window=SVM_dict['raw_window_size'],
                                  use_test=True, use_pca=False)

    # parallelization
    if debug: n_jobs=1
    else: n_jobs=-1
    l_data = Parallel(n_jobs=n_jobs, verbose=10)(delayed(cf.run_classifiers)( idx, processed_data_path, \
                                                                         task_name, \
                                                                         method, ROC_data, \
                                                                         ROC_dict, \
                                                                         SVM_dict, HMM_dict, \
                                                                         raw_data=(osvm_data,bpsvm_data),\
                                                                         startIdx=startIdx, nState=nState) \
                                                                         for idx in xrange(len(kFold_list)) \
                                                                         for method in method_list )


    print "finished to run run_classifiers"
    ROC_data = util.update_roc_data(ROC_data, l_data, nPoints, method_list)
    ut.save_pickle(ROC_data, roc_pkl)


    #----------------- List up anomaly cases ------------------
    ## for method in method_list:
    ##     max_idx = np.argmax(acc_rates[method])

    ##     print "-----------------------------------"
    ##     print "Method: ", method
    ##     print acc_rates[method][max_idx]
    ## if nPoints > 1:
    ##     print "Wrong number of points"
    ##     sys.exit()
    
    detection_info(method_list, ROC_data, nPoints, kFold_list, zero_fp_flag=True)
    



def evaluation_modality(subject_names, task_name, raw_data_path, processed_data_path, param_dict,\
                        detection_rate=False,\
                        data_renew=False, save_pdf=False, verbose=False, debug=False,\
                        no_plot=False, delay_plot=True, find_param=False, data_gen=False):

    ## Parameters
    # data
    data_dict  = param_dict['data_param']
    data_renew = data_dict['renew']
    # HMM
    HMM_dict   = param_dict['HMM']
    nState     = HMM_dict['nState']
    cov        = HMM_dict['cov']
    # SVM
    SVM_dict   = param_dict['SVM']

    # ROC
    ROC_dict = param_dict['ROC']

    # parameters
    startIdx    = 4
    method_list = ROC_dict['methods'] 
    nPoints     = ROC_dict['nPoints']
    
    #------------------------------------------

    if os.path.isdir(processed_data_path) is False:
        os.system('mkdir -p '+processed_data_path)

    crossVal_pkl = os.path.join(processed_data_path, 'cv_'+task_name+'.pkl')
    
    if os.path.isfile(crossVal_pkl) and data_renew is False and data_gen is False:
        print "CV data exists and no renew"
        d = ut.load_pickle(crossVal_pkl)
        kFold_list = d['kFoldList'] 
        successData = d['successData']
        failureData = d['failureData']
        success_files = d['success_files']
        failure_files = d['failure_files']
    else:
        '''
        Use augmented data? if nAugment is 0, then aug_successData = successData
        '''        
        d = dm.getDataLOPO(subject_names, task_name, raw_data_path, \
                           processed_data_path, data_dict['rf_center'], data_dict['local_range'],\
                           downSampleSize=data_dict['downSampleSize'], scale=1.0,\
                           handFeatures=data_dict['handFeatures'], \
                           cut_data=data_dict['cut_data'], \
                           data_renew=data_renew, max_time=data_dict['max_time'])
        successData, failureData, success_files, failure_files, kFold_list \
          = dm.LOPO_data_index(d['successDataList'], d['failureDataList'],\
                               d['successFileList'], d['failureFileList'])

        d['successData']   = successData
        d['failureData']   = failureData
        d['success_files'] = success_files
        d['failure_files'] = failure_files
        d['kFoldList']     = kFold_list
        ut.save_pickle(d, crossVal_pkl)
        if data_gen: sys.exit()

    #-----------------------------------------------------------------------------------------
    param_dict2 = d['param_dict']
    if 'timeList' in param_dict2.keys():
        timeList    = param_dict2['timeList'][startIdx:]
    else: timeList = None

    print d['param_dict']['feature_names']

    org_processed_data_path = copy.copy(processed_data_path)
    modality_list = ['f', 's', 'k', 'fs', 'fk', 'sk'] #, 'fsk']
    for modality in modality_list:
        print "-------------------- Modality: ", modality ," ------------------------"
        if modality == 'f':            
            successData = d['successData'][1:3]
            failureData = d['failureData'][1:3]
        elif modality == 's':            
            successData = d['successData'][0:1]
            failureData = d['failureData'][0:1]
        elif modality == 'k':            
            successData = d['successData'][3:]
            failureData = d['failureData'][3:]
        elif modality == 'fs':            
            successData = d['successData'][[0,1,2]]
            failureData = d['failureData'][[0,1,2]]
        elif modality == 'fk':            
            successData = d['successData'][1:]
            failureData = d['failureData'][1:]
        elif modality == 'sk':            
            successData = d['successData'][[0,3]]
            failureData = d['failureData'][[0,3]]

        processed_data_path = os.path.join(org_processed_data_path, modality)
        if os.path.isdir(processed_data_path) is False:
            os.system('mkdir -p '+processed_data_path)
            
        #-----------------------------------------------------------------------------------------    
        # Training HMM, and getting classifier training and testing data
        dm.saveHMMinducedFeatures(kFold_list, successData, failureData,\
                                  task_name, processed_data_path,\
                                  HMM_dict, data_renew, startIdx, nState, cov, scale, \
                                  success_files=success_files, failure_files=failure_files,\
                                  noise_mag=0.03, verbose=verbose)

        #-----------------------------------------------------------------------------------------
        roc_pkl = os.path.join(processed_data_path, 'roc_'+task_name+'.pkl')

        if os.path.isfile(roc_pkl) is False or HMM_dict['renew'] or SVM_dict['renew']: ROC_data = {}
        else: ROC_data = ut.load_pickle(roc_pkl)
        ROC_data = util.reset_roc_data(ROC_data, method_list, ROC_dict['update_list'], nPoints)

        osvm_data = None ; bpsvm_data = None
        if 'osvm' in method_list  and ROC_data['osvm']['complete'] is False:
            osvm_data = dm.getPCAData(len(kFold_list), crossVal_pkl, \
                                      window=SVM_dict['raw_window_size'],
                                      use_test=True, use_pca=False )

        # parallelization
        if debug: n_jobs=1
        else: n_jobs=-1
        l_data = Parallel(n_jobs=n_jobs, verbose=10)(delayed(cf.run_classifiers)( idx, processed_data_path, \
                                                                             task_name, \
                                                                             method, ROC_data, \
                                                                             ROC_dict, \
                                                                             SVM_dict, HMM_dict, \
                                                                             raw_data=(osvm_data,bpsvm_data),\
                                                                             startIdx=startIdx, nState=nState) \
                                                                             for idx in xrange(len(kFold_list)) \
                                                                             for method in method_list )


        print "finished to run run_classifiers"
        ROC_data = util.update_roc_data(ROC_data, l_data, nPoints, method_list)
        ut.save_pickle(ROC_data, roc_pkl)

        if detection_rate: detection_info(method_list, ROC_data, nPoints, kFold_list,zero_fp_flag=True)
        

    # ---------------- ROC Visualization ----------------------
    if detection_rate: sys.exit()
    for modality in modality_list:
        processed_data_path = os.path.join(org_processed_data_path, modality)
        roc_pkl = os.path.join(processed_data_path, 'roc_'+task_name+'.pkl')
        ROC_data = ut.load_pickle(roc_pkl)        
        roc_info(method_list, ROC_data, nPoints, no_plot=True)


def detection_info(method_list, ROC_data, nPoints, kFold_list, zero_fp_flag=False):

    for method in method_list:
        print "---------- ", method, " -----------"

        tp_l = []
        tn_l = []
        fn_l = []
        fp_l = []
        for i in xrange(nPoints):
            tp_l.append( float(np.sum(ROC_data[method]['tp_l'][i])) )
            tn_l.append( float(np.sum(ROC_data[method]['tn_l'][i])) )
            fn_l.append( float(np.sum(ROC_data[method]['fn_l'][i])) )
            fp_l.append( float(np.sum(ROC_data[method]['fp_l'][i])) )
        tp_l = np.array(tp_l)
        fp_l = np.array(fp_l)
        tn_l = np.array(tn_l)
        fn_l = np.array(fn_l)
            
        fscore_l = 2.0*tp_l/(2.0*tp_l+fp_l+fn_l)
        fscore_l = fscore05_l =(1.0+0.25)*tp_l / ((1.0+0.25)*tp_l + 0.25*fn_l + fp_l )
        ## fscore_l = fscore2_l =(1.0+4.0)*tp_l / ((1.0+4.0)*tp_l + 4.0*fn_l + fp_l )
        acc_l = (tp_l+tn_l)/( tp_l+tn_l+fp_l+fn_l )
        fpr_l = fp_l/(fp_l+tn_l)
        tpr_l = tp_l/(tp_l+fn_l)
        print "FPR: ", fpr_l

        if zero_fp_flag:

            i = (np.abs(fpr_l-0.08)).argmin()
            
            ## if fpr_l[0] > fpr_l[-1]:
            ##     for i in xrange(len(fpr_l)):
            ##         if fpr_l[i] < 0.1+0.02: break
            ## else:
            ##     for i in xrange(len(fpr_l)):
            ##         if fpr_l[i] > 0.1-0.02 and fpr_l[i+1] > 0.1+0.02: break
            best_idx = i
        else:
            ##################################3
            ## best_idx = np.argmin(fp_l)
            ## best_idx = np.argmax(acc_l)
            best_idx = np.argmax(fscore_l)
            ##################################3
        
        print 'fp_l:', fp_l
        print 'fscore: ', fscore_l
        print "F1-score: ", fscore_l[best_idx], " fp: ", fp_l[best_idx], " acc: ", acc_l[best_idx], "tpr: ", tpr_l[best_idx], "fpr: ", fpr_l[best_idx]
        print "best idx: ", best_idx

        ## print fn_l+tp_l
        ## print fp_l+tn_l
        ## sys.exit()

        # fscore
        ## tp = float(np.sum(ROC_data[method]['tp_l'][0]))
        ## fn = float(np.sum(ROC_data[method]['fn_l'][0]))
        ## fp = float(np.sum(ROC_data[method]['fp_l'][0]))
        ## fscore_1 = 2.0*tp/(2.0*tp+fn+fp)
        
        # false negatives
        labels = ROC_data[method]['fn_labels'][best_idx]            
        anomalies = [label.split('/')[-1].split('_')[0] for label in labels] # extract class
            
        d = {x: anomalies.count(x) for x in anomalies}
        l_idx = np.array(d.values()).argsort() #[-10:]

        d_list = []
        t_sum = []
        print "Max count is ", len(kFold_list)*2
        for idx in l_idx:
            print "Class: ", np.array(d.keys())[idx], "Count: ", np.array(d.values())[idx], \
              " Detection rate: ", float( len(kFold_list)*2 - np.array(d.values())[idx])/float( len(kFold_list)*2)
            t_sum.append( float( len(kFold_list)*2 - np.array(d.values())[idx])/float( len(kFold_list)*2) )
            d_list.append([float(np.array(d.keys())[idx]), float( len(kFold_list)*2 - np.array(d.values())[idx])/float( len(kFold_list)*2)])

        if len(t_sum)<12: t_sum.append(1.0)
        print "Avg.: ", np.mean(t_sum)

    d_list = np.array(d_list)
    d_list = d_list[np.argsort(d_list[:,0])]
    print d_list[:,0]
    print d_list[:,1]

    return d_list
        

def plotModalityVSAnomaly(save_pdf=False):

    ## from sklearn.metrics import confusion_matrix

    f   = np.array([[0., 0., 0., 0.75, 0., 0.9375,  0., 0., 0., 0., 0.5, 0.125]]).T #0.0875
    s   = np.array([[0.25, 0.875, 0.0625, 0.4375, 0.125, 0.125, 0.9375, 0., 0.0625, 0.0625, 0.1875, 0.0625]]).T # 0.06875
    k   = np.array([[1.0, 0., 0.375, 0.4375, 1.0, 0.6875, 0.25, 0.9375, 0.1875, 0.5, 0.6875, 0.]]).T #0.08125
    fs  = np.array([[0.0625, 0.5625, 0.0625, 0.625, 0.0625, 0.8125, 0.8125, 0., 0., 0., 0.3125, 0.0625]]).T #0.0875
    fk  = np.array([[1.0, 0., 0.1875, 0.875, 1.0, 0.875, 0.1875, 0.25, 0.0625, 0.4375, 0.5625, 0.]]).T #0.08125
    sk  = np.array([[1., 0.625, 0.5, 0.4375, 1.0, 0.375, 0.8125, 0.375, 0.0625, 0.5, 0.6875, 0.0625]]).T # 0.08125
    fsk = np.array([[1.0, 0.5, 0.375, 0.4375, 1.0, 0.9375, 0.8125, 0.4375, 0.1875, 0.1875, 0.625, 0.125]]).T # 0.08125

    cm = np.hstack([f,s,k,fs,fk,sk,fsk])
    np.set_printoptions(precision=3)
    normalize=False
    title='Confusion matrix'
    cmap=plt.cm.Blues
    ## x_classes = [1,2,3,4,5,6,7,8,9,10,11,12]
    x_classes = ['Object collision', 'Noisy environment', 'Spoon miss by a user', 'Spoon collision by a user', 'Robot-body collision by a user', 'Aggressive eating', 'Anomalous sound from a user', 'Unreachable mouth pose', 'Face occlusion by a user', 'Spoon miss by system fault', 'Spoon collision by system fault', 'Freeze by system fault']
    y_classes = ['force','sound','kinematics','force-sound','force-\n kinematics','sound-\n kinematics','force-sound-\n kinematics']
    
    fig = plt.figure(figsize=(9,7))
    ## plt.rc('text', usetex=True)    
    plt.imshow(cm, interpolation='nearest', cmap=cmap, aspect='auto')
    ## plt.imshow(cm, interpolation='nearest', cmap=cmap, extent=[0,7,0,12], aspect='auto')
    ## plt.title(title)
    ## plt.colorbar(orientation='horizontal')
    plt.colorbar()
    tick_marks = np.arange(len(y_classes))
    plt.xticks(tick_marks, y_classes, rotation=30)
    tick_marks = np.arange(len(x_classes))
    plt.yticks(tick_marks, x_classes)
    ## ax = plt.gca()
    ## ax.xaxis.tick_top()

    if normalize:
        cm = cm.astype('float') / cm.sum(axis=1)[:, np.newaxis]
        print("Normalized confusion matrix")
    else:
        print('Confusion matrix, without normalization')

    print(cm)

    ## thresh = cm.max() / 2.
    ## for i, j in itertools.product(range(cm.shape[0]), range(cm.shape[1])):
    ##     plt.text(j, i, cm[i, j],
    ##              horizontalalignment="center",
    ##              color="white" if cm[i, j] > thresh else "black")

    plt.tight_layout()
    plt.ylabel('Anomaly class', fontsize=22)
    plt.xlabel('Modalities', fontsize=22)
    plt.tight_layout()

    if save_pdf == True:
        fig.savefig('test.pdf')
        fig.savefig('test.png')
        os.system('cp test.p* ~/Dropbox/HRL/')
    else:
        plt.show()        


    f = [50.58 , 70.24 , 46.86 , 81.23 , 49.14, 68.39 , 73.53 , 54.96 , 51.68 , 63.92, 77.03 , 81.99 , 61.93 , 82.12 , 76.09]
    fs = [66.72 , 82.88 , 55.37 , 71.78 , 58.98,  86.65 , 92.18 , 67.43 , 95.68, 73.30,  89.22 , 97.59 , 65.24 , 79.99 , 79.24]
    fsk = [91.13, 99.38, 76.54, 86.08, 81.21]

    print np.mean(f)
    print np.mean(fs)
    print np.mean(fsk)


if __name__ == '__main__':

    import optparse
    p = optparse.OptionParser()
    util.initialiseOptParser(p)
    opt, args = p.parse_args()
    

    #---------------------------------------------------------------------------           
    # Run evaluation
    #---------------------------------------------------------------------------           
    rf_center     = 'kinEEPos'        
    scale         = 1.0
    local_range   = 10.0
    nPoints = 40 #None

    raw_data_path, save_data_path, param_dict = getParams(opt.task, opt.bDataRenew, \
                                                          opt.bHMMRenew, opt.bClassifierRenew, opt.dim,\
                                                          rf_center, local_range, nPoints=nPoints)
    if opt.bNoUpdate: param_dict['ROC']['update_list'] = []
    # Mikako - bad camera
    # s1 - kaci - before camera calibration
    subjects = ['s2', 's3','s4','s5', 's6','s7','s8', 's9']

    if opt.bEvaluationUnexpected:
        save_data_path = os.path.expanduser('~')+\
          '/hrl_file_server/dpark_data/anomaly/AURO2016/'+opt.task+'_data_unexp/'+\
          str(param_dict['data_param']['downSampleSize'])+'_'+str(opt.dim)

    
    #---------------------------------------------------------------------------           
    if opt.bRawDataPlot or opt.bInterpDataPlot:
        '''
        Before localization: Raw data plot
        After localization: Raw or interpolated data plot
        '''
        successData = True
        failureData = False
        modality_list   = ['kinematics', 'kinematics_des', 'audioWrist', 'ft', 'vision_landmark'] # raw plot

        dv.data_plot(subjects, opt.task, raw_data_path, save_data_path,\
                  downSampleSize=param_dict['data_param']['downSampleSize'], \
                  local_range=local_range, rf_center=rf_center, global_data=True, \
                  raw_viz=opt.bRawDataPlot, interp_viz=opt.bInterpDataPlot, save_pdf=opt.bSavePdf,\
                  successData=successData, failureData=failureData,\
                  continuousPlot=True, \
                  modality_list=modality_list, data_renew=opt.bDataRenew, verbose=opt.bVerbose)

    elif opt.bFeaturePlot:
        success_viz = True
        failure_viz = False
        ## param_dict['data_param']['handFeatures'] = ['crossmodal_targetEEDist', \
        ##                                             'crossmodal_targetEEAng']
        
        dm.getDataLOPO(subjects, opt.task, raw_data_path, save_data_path,
                       param_dict['data_param']['rf_center'], param_dict['data_param']['local_range'],\
                       downSampleSize=param_dict['data_param']['downSampleSize'], scale=scale, \
                       success_viz=success_viz, failure_viz=failure_viz,\
                       ae_data=False,\
                       cut_data=param_dict['data_param']['cut_data'],\
                       save_pdf=opt.bSavePdf, solid_color=True,\
                       handFeatures=param_dict['data_param']['handFeatures'], data_renew=opt.bDataRenew, \
                       max_time=param_dict['data_param']['max_time'])

    elif opt.bLikelihoodPlot:
        ## param_dict['HMM']['nState'] = 25
        ## param_dict['HMM']['scale'] = 9.0
        ## param_dict['SVM']['nugget'] = 10.0

        import hrl_anomaly_detection.data_viz as dv        
        dv.vizLikelihoods(subjects, opt.task, raw_data_path, save_data_path, param_dict,\
                          decision_boundary_viz=False, method='hmmgp', \
                          useTrain=True, useNormalTest=False, useAbnormalTest=True,\
                          useTrain_color=False, useNormalTest_color=False, useAbnormalTest_color=False,\
                          hmm_renew=opt.bHMMRenew, data_renew=opt.bDataRenew, save_pdf=opt.bSavePdf,\
                          verbose=opt.bVerbose, lopo=True)

    elif opt.HMM_param_search:
        from hrl_anomaly_detection.hmm import run_hmm_cpu as hmm_opt
        parameters = {'nState': [25], 'scale': np.linspace(1.0,18.0,10), \
                      'cov': np.linspace(0.1, 3.0, 2) }
        max_check_fold = 1 #len(subjects) #5 #None
        no_cov = False
        method = 'hmmgp'
        
        hmm_opt.tune_hmm(parameters, opt.task, param_dict, save_data_path, verbose=False, n_jobs=opt.n_jobs, \
                         bSave=opt.bSave, method=method, max_check_fold=max_check_fold, no_cov=no_cov)

    elif opt.CLF_param_search:
        from hrl_anomaly_detection.classifiers import opt_classifier as clf_opt
        method = 'hmmgp'
        clf_opt.tune_classifier(save_data_path, opt.task, method, param_dict, file_idx=2,\
                                n_jobs=opt.n_jobs, n_iter_search=100, save=opt.bSave)

    elif opt.bEvaluationUnexpected and opt.bEvaluationModality is False:
        param_dict['ROC']['methods'] = ['progress', 'hmmgp'] #'osvm',
        ## param_dict['ROC']['update_list'] = ['hmmgp']
        if opt.bNoUpdate: param_dict['ROC']['update_list'] = []        
        
        param_dict['ROC']['progress_param_range'] = -np.logspace(0.4, 0.8, nPoints)
        param_dict['ROC']['hmmgp_param_range']    = -np.logspace(0.8, 1.4, nPoints)
        ## param_dict['SVM']['nugget'] = 119.43
        ## param_dict['SVM']['theta0'] = 1.423

        evaluation_unexp(subjects, opt.task, raw_data_path, save_data_path, \
                         param_dict, save_pdf=opt.bSavePdf, \
                         verbose=opt.bVerbose, debug=opt.bDebug, no_plot=opt.bNoPlot, \
                         find_param=False, data_gen=opt.bDataGen)

    elif opt.bEvaluationAll or opt.bDataGen:
        if opt.bNoUpdate: param_dict['ROC']['update_list'] = []        
        evaluation_all(subjects, opt.task, raw_data_path, save_data_path, param_dict, save_pdf=opt.bSavePdf, \
                       verbose=opt.bVerbose, debug=opt.bDebug, no_plot=opt.bNoPlot, \
                       find_param=False, data_gen=opt.bDataGen)

    elif opt.bEvaluationAccParam or opt.bEvaluationWithNoise:
        param_dict['ROC']['methods'] = ['osvm', 'fixed', 'change', 'hmmosvm', 'progress', 'hmmgp']
        param_dict['ROC']['update_list'] = [ 'osvm']
        if opt.bNoUpdate: param_dict['ROC']['update_list'] = []        
        param_dict['ROC']['nPoints'] = nPoints = 40

        save_data_path = os.path.expanduser('~')+\
          '/hrl_file_server/dpark_data/anomaly/AURO2016/'+opt.task+'_data/'+\
          str(param_dict['data_param']['downSampleSize'])+'_'+str(opt.dim)+'_acc_param'

        if opt.task == 'feeding':
            param_dict['ROC']['hmmgp_param_range']  = -np.logspace(0.0, 2.5, nPoints)+2.0
            param_dict['ROC']['progress_param_range'] = -np.logspace(0.2, 2.0, nPoints)+2.0            
            param_dict['ROC']['osvm_param_range']     = np.logspace(-4.5, 0.0, nPoints)
            param_dict['ROC']['hmmosvm_param_range']  = np.logspace(-4.5, 0.0, nPoints)
            param_dict['ROC']['fixed_param_range']  = np.linspace(-4.0, 1.0, nPoints)
            param_dict['ROC']['change_param_range'] = np.linspace(-30.0, 10.0, nPoints)
        else:
            sys.exit()

        if 0:
            step_mag =0.01*param_dict['HMM']['scale'] # need to varying it
            pkl_prefix = 'step_0.01'
        elif 0:
            step_mag =0.02*param_dict['HMM']['scale'] # need to varying it
            pkl_prefix = 'step_0.02'
        elif 0:
            step_mag =0.03*param_dict['HMM']['scale'] # need to varying it
            pkl_prefix = 'step_0.03'
        elif 0:
            step_mag =0.025*param_dict['HMM']['scale'] # need to varying it
            pkl_prefix = 'step_0.025'
        elif 1:
            step_mag =0.05*param_dict['HMM']['scale'] # need to varying it
            pkl_prefix = 'step_0.05'
        elif 0:
            step_mag = 0.1*param_dict['HMM']['scale'] # need to varying it
            pkl_prefix = 'step_0.1'
        ## elif 0:
        ##     step_mag = 0.15*param_dict['HMM']['scale'] # need to varying it
        ##     pkl_prefix = 'step_0.15'
        elif 0:
            step_mag = 0.2*param_dict['HMM']['scale'] # need to varying it
            pkl_prefix = 'step_0.2'
        elif 0:
            step_mag = 0.25*param_dict['HMM']['scale'] # need to varying it
            pkl_prefix = 'step_0.25'
        elif True:
            step_mag = 0.5*param_dict['HMM']['scale'] # need to varying it
            pkl_prefix = 'step_0.5'
        elif True:
            step_mag =1.0*param_dict['HMM']['scale'] # need to varying it
            pkl_prefix = 'step_1.0'
        else:
            step_mag = 10000000*param_dict['HMM']['scale'] # need to varying it
            pkl_prefix = 'step_10000000'

        import hrl_anomaly_detection.evaluation as ev 
        if opt.bEvaluationAccParam:
            ev.evaluation_acc_param(subjects, opt.task, raw_data_path, save_data_path, param_dict,\
                                    step_mag, pkl_prefix,\
                                    save_pdf=opt.bSavePdf, verbose=opt.bVerbose, debug=opt.bDebug, \
                                    no_plot=opt.bNoPlot, delay_plot=True)
        else:        
            ev.evaluation_step_noise(subjects, opt.task, raw_data_path, save_data_path, param_dict,\
                                     step_mag, pkl_prefix,\
                                     save_pdf=opt.bSavePdf, verbose=opt.bVerbose, debug=opt.bDebug, \
                                     no_plot=opt.bNoPlot, delay_plot=True)

    elif opt.param_search:
        
        from scipy.stats import uniform, expon
        param_dist = {'scale': uniform(2.0,15.0),\
                      'cov': [1.0],\
                      'ths_mult': uniform(-35.0,35.0),\
                      'nugget': uniform(1.0,100.0),\
                      'theta0': [1.0] }
        method = 'hmmgp'
        
        from hrl_anomaly_detection import optimizeParam as op
        op.tune_detector(param_dist, opt.task, param_dict, save_data_path, verbose=False, n_jobs=opt.n_jobs, \
                         save=opt.bSave, method=method, n_iter_search=100)

    elif opt.bEvaluationModality:
        param_dict['ROC']['methods'] = ['hmmgp']
        if opt.bNoUpdate: param_dict['ROC']['update_list'] = []
        save_data_path = os.path.expanduser('~')+\
          '/hrl_file_server/dpark_data/anomaly/AURO2016/'+opt.task+'_data_modality/'+\
          str(param_dict['data_param']['downSampleSize'])
        nPoints = param_dict['ROC']['nPoints'] = 100

        param_dict['ROC']['hmmgp_param_range'] = np.logspace(-0.5, 2.6, nPoints)*-1.0
        
        evaluation_modality(subjects, opt.task, raw_data_path, save_data_path, param_dict, \
                            detection_rate=opt.bEvaluationUnexpected,\
                            save_pdf=opt.bSavePdf, \
                            verbose=opt.bVerbose, debug=opt.bDebug, no_plot=opt.bNoPlot, \
                            data_gen=opt.bDataGen)

    else:
        plotModalityVSAnomaly(opt.bSavePdf)
