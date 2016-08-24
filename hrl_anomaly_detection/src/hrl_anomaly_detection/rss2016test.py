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

# system
## import rospy, roslib
import os, sys, copy
import random
import socket

# visualization
import matplotlib
#matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from matplotlib import gridspec
# util
import numpy as np
import scipy
import hrl_lib.util as ut
from hrl_anomaly_detection.util import *
from hrl_anomaly_detection.util_viz import *
from hrl_anomaly_detection import data_manager as dm
## from hrl_anomaly_detection.scooping_feeding import util as sutil
## import PyKDL
## import sandbox_dpark_darpa_m3.lib.hrl_check_util as hcu
## import sandbox_dpark_darpa_m3.lib.hrl_dh_lib as hdl
## import hrl_lib.circular_buffer as cb
from hrl_anomaly_detection.params import *
from hrl_anomaly_detection.optimizeParam import *

# learning
## from hrl_anomaly_detection.hmm import learning_hmm_multi_n as hmm
from hrl_anomaly_detection.hmm import learning_hmm as hmm
from mvpa2.datasets.base import Dataset
## from sklearn import svm
from joblib import Parallel, delayed
from sklearn import metrics

# private learner
import hrl_anomaly_detection.classifiers.classifier as cf

import itertools
colors = itertools.cycle(['g', 'm', 'c', 'k', 'y','r', 'b', ])
shapes = itertools.cycle(['x','v', 'o', '+'])

matplotlib.rcParams['pdf.fonttype'] = 42
matplotlib.rcParams['ps.fonttype'] = 42 
   


    
def aeDataExtraction(subject_names, task_name, raw_data_path, \
                    processed_data_path, param_dict,\
                    handFeature_viz=False, success_viz=False, failure_viz=False,\
                    verbose=False):

    ## Parameters
    # data
    data_dict  = param_dict['data_param']
    data_renew = data_dict['renew']
    handFeatures = data_dict['handFeatures']
    # AE
    AE_dict     = param_dict['AE']
    rawFeatures = AE_dict['rawFeatures']
    #------------------------------------------
    assert AE_dict['switch'] == True
                   
    crossVal_pkl = os.path.join(processed_data_path, 'cv_'+task_name+'.pkl')
    if os.path.isfile(crossVal_pkl) and data_renew is False: 
        print "Loading cv data"
        d = ut.load_pickle(crossVal_pkl)
        if 'aeSuccessData' not in d.keys():
            print "Reload data!!"
            sys.exit()
    else:
        d = dm.getDataSet(subject_names, task_name, raw_data_path, processed_data_path, \
                           data_dict['rf_center'], data_dict['local_range'],\
                           downSampleSize=data_dict['downSampleSize'], scale=1.0,\
                           ae_data=AE_dict['switch'], \
                           handFeatures=handFeatures, rawFeatures=rawFeatures,\
                           cut_data=data_dict['cut_data'],
                           data_renew=data_renew)

        if os.path.isfile(crossVal_pkl):
            dd = ut.load_pickle(crossVal_pkl)
            d['kFoldList'] = dd['kFoldList'] 
        else:
            kFold_list = dm.kFold_data_index2(len(d['aeSuccessData'][0]),\
                                              len(d['aeFailureData'][0]),\
                                              data_dict['nNormalFold'], data_dict['nAbnormalFold'] )

            d['kFoldList']       = kFold_list                                             
        ut.save_pickle(d, crossVal_pkl)

    # Training HMM, and getting classifier training and testing data
    for idx, (normalTrainIdx, abnormalTrainIdx, normalTestIdx, abnormalTestIdx) \
      in enumerate( d['kFoldList'] ):

        if verbose: print "Start "+str(idx)+"/"+str(len( d['kFoldList'] ))+"th iteration"

        if AE_dict['method'] == 'ae':
            AE_proc_data = os.path.join(processed_data_path, 'ae_processed_data_'+str(idx)+'.pkl')
        else:
            AE_proc_data = os.path.join(processed_data_path, 'pca_processed_data_'+str(idx)+'.pkl')
            
        # From dim x sample x length
        # To reduced_dim x sample
        dd = dm.getAEdataSet(idx, d['aeSuccessData'], d['aeFailureData'], \
                             d['successData'], d['failureData'], d['param_dict'], \
                             normalTrainIdx, abnormalTrainIdx, normalTestIdx, abnormalTestIdx,
                             AE_dict['time_window'], AE_dict['nAugment'], \
                             AE_proc_data, \
                             # data param
                             processed_data_path, \
                             # AE param
                             layer_sizes=AE_dict['layer_sizes'], learning_rate=AE_dict['learning_rate'], \
                             learning_rate_decay=AE_dict['learning_rate_decay'], \
                             momentum=AE_dict['momentum'], dampening=AE_dict['dampening'], \
                             lambda_reg=AE_dict['lambda_reg'], \
                             max_iteration=AE_dict['max_iteration'], min_loss=AE_dict['min_loss'], \
                             cuda=AE_dict['cuda'], \
                             filtering=AE_dict['filter'], filteringDim=AE_dict['filterDim'],\
                             method=AE_dict['method'],\
                             # PCA param
                             pca_gamma=AE_dict['pca_gamma'],\
                             verbose=verbose, renew=AE_dict['renew'], \
                             preTrainModel=AE_dict['preTrainModel'])

        if AE_dict['filter']:
            # NOTE: pooling dimension should vary on each auto encoder.
            # Filtering using variances
            normalTrainData   = dd['normTrainDataFiltered']
            abnormalTrainData = dd['abnormTrainDataFiltered']
            normalTestData    = dd['normTestDataFiltered']
            abnormalTestData  = dd['abnormTestDataFiltered']
        else:
            normalTrainData   = dd['normTrainData']
            abnormalTrainData = dd['abnormTrainData']
            normalTestData    = dd['normTestData']
            abnormalTestData  = dd['abnormTestData']            

            
        if success_viz or failure_viz and False:
            import data_viz as dv
            print dd.keys()
            dv.viz(dd['normTrainData'], normTest=dd['normTestData'], \
                   abnormTest=dd['abnormTestData'],skip=True)
            if AE_dict['filter']:
                dv.viz(dd['normTrainDataFiltered'], abnormTest=dd['abnormTrainDataFiltered'])
            else: dv.viz(dd['normTrainData'], dd['abnormTrainData'])

        if handFeature_viz:
            print AE_dict['add_option'], dd['handFeatureNames']
            handNormalTrainData = combineData( normalTrainData, dd['handNormTrainData'],\
                                               AE_dict['add_option'], dd['handFeatureNames'])
            handAbnormalTrainData = combineData( abnormalTrainData, dd['handAbnormTrainData'],\
                                                 AE_dict['add_option'], dd['handFeatureNames'])

            
            import data_viz as dv
            dv.viz(handNormalTrainData, abnormTest=handAbnormalTrainData)

            ## normalTrainData   = stackSample(normalTrainData, handNormalTrainData)
            ## abnormalTrainData = stackSample(abnormalTrainData, handAbnormalTrainData)



# ------------------------------------------------------------------------------------
# ------------------------------------------------------------------------------------
# ------------------------------------------------------------------------------------
# ------------------------------------------------------------------------------------

def evaluation_all(subject_names, task_name, raw_data_path, processed_data_path, param_dict,\
                   data_renew=False, save_pdf=False, verbose=False, debug=False,\
                   no_plot=False, delay_plot=True, find_param=False, data_gen=False):

    ## Parameters
    # data
    data_dict  = param_dict['data_param']
    data_renew = data_dict['renew']
    # AE
    AE_dict     = param_dict['AE']
    # HMM
    HMM_dict   = param_dict['HMM']
    nState     = HMM_dict['nState']
    cov        = HMM_dict['cov']
    add_logp_d = HMM_dict.get('add_logp_d', False)
    # SVM
    SVM_dict   = param_dict['SVM']

    # ROC
    ROC_dict = param_dict['ROC']
    
    #------------------------------------------
    if os.path.isdir(processed_data_path) is False:
        os.system('mkdir -p '+processed_data_path)

    crossVal_pkl = os.path.join(processed_data_path, 'cv_'+task_name+'.pkl')
    
    if os.path.isfile(crossVal_pkl) and data_renew is False and data_gen is False:
        d = ut.load_pickle(crossVal_pkl)
        kFold_list  = d['kFoldList']
    else:
        '''
        Use augmented data? if nAugment is 0, then aug_successData = successData
        '''        
        d = dm.getDataSet(subject_names, task_name, raw_data_path, \
                           processed_data_path, data_dict['rf_center'], data_dict['local_range'],\
                           downSampleSize=data_dict['downSampleSize'], scale=1.0,\
                           ae_data=AE_dict['switch'],\
                           handFeatures=data_dict['handFeatures'], \
                           rawFeatures=AE_dict['rawFeatures'],\
                           cut_data=data_dict['cut_data'], \
                           data_renew=data_renew, max_time=data_dict['max_time'])
                           
        # Task-oriented hand-crafted features        
        kFold_list = dm.kFold_data_index2(len(d['successData'][0]), len(d['failureData'][0]), \
                                          data_dict['nNormalFold'], data_dict['nAbnormalFold'] )
        d['kFoldList']   = kFold_list
        ut.save_pickle(d, crossVal_pkl)
        if data_gen: sys.exit()

    #-----------------------------------------------------------------------------------------
    # parameters
    startIdx    = 4
    method_list = ROC_dict['methods'] 
    nPoints     = ROC_dict['nPoints']

    successData = d['successData']
    failureData = d['failureData']
    param_dict2 = d['param_dict']
    if 'timeList' in param_dict2.keys():
        timeList    = param_dict2['timeList'][startIdx:]
    else: timeList = None

    #-----------------------------------------------------------------------------------------
    # Training HMM, and getting classifier training and testing data
    for idx, (normalTrainIdx, abnormalTrainIdx, normalTestIdx, abnormalTestIdx) \
      in enumerate(kFold_list):

        if verbose: print idx, " : training hmm and getting classifier training and testing data"
            
        modeling_pkl = os.path.join(processed_data_path, 'hmm_'+task_name+'_'+str(idx)+'.pkl')
        if not (os.path.isfile(modeling_pkl) is False or HMM_dict['renew'] or data_renew): continue

        # scaling with size dim x sample x length
        normalTrainData   = successData[:, normalTrainIdx, :] * HMM_dict['scale']
        abnormalTrainData = failureData[:, abnormalTrainIdx, :] * HMM_dict['scale'] 
        normalTestData    = successData[:, normalTestIdx, :] * HMM_dict['scale'] 
        abnormalTestData  = failureData[:, abnormalTestIdx, :] * HMM_dict['scale'] 

        # training hmm
        if verbose: print "start to fit hmm"
        nEmissionDim = len(normalTrainData)
        cov_mult     = [cov]*(nEmissionDim**2)
        nLength      = len(normalTrainData[0][0]) - startIdx

        #-----------------------------------------------------------------------------------------
        # Full co-variance
        #-----------------------------------------------------------------------------------------
        ml  = hmm.learning_hmm(nState, nEmissionDim, verbose=verbose) 
        if data_dict['handFeatures_noise']:
            ret = ml.fit(normalTrainData+\
                         np.random.normal(0.0, 0.03, np.shape(normalTrainData) )*HMM_dict['scale'], \
                         cov_mult=cov_mult, use_pkl=False)
        else:
            ret = ml.fit(normalTrainData, cov_mult=cov_mult, use_pkl=False)

        if ret == 'Failure': sys.exit()

        # Classifier training data
        ll_classifier_train_X, ll_classifier_train_Y, ll_classifier_train_idx =\
          hmm.getHMMinducedFeaturesFromRawFeatures(ml, normalTrainData, abnormalTrainData, startIdx, add_logp_d)

        # Classifier test data
        ll_classifier_test_X, ll_classifier_test_Y, ll_classifier_test_idx =\
          hmm.getHMMinducedFeaturesFromRawFeatures(ml, normalTestData, abnormalTestData, startIdx, add_logp_d)


        #-----------------------------------------------------------------------------------------
        # New three element feature vector
        #-----------------------------------------------------------------------------------------
        ll_classifier_ep_train_X, ll_classifier_ep_train_Y, ll_classifier_ep_train_idx =\
          hmm.getEntropyFeaturesFromHMMInducedFeatures(ll_classifier_train_X, \
                                                       ll_classifier_train_Y, \
                                                       ll_classifier_train_idx, nState)
        ll_classifier_ep_test_X, ll_classifier_ep_test_Y, ll_classifier_ep_test_idx =\
          hmm.getEntropyFeaturesFromHMMInducedFeatures(ll_classifier_test_X, \
                                                       ll_classifier_test_Y, \
                                                       ll_classifier_test_idx, nState)

        ## ll_classifier_ep_train_X = np.array(ll_classifier_ep_train_X)
        ## fig = plt.figure()
        ## ax1 = fig.add_subplot(211)        
        ## for i in xrange(len(ll_classifier_ep_train_X)):
        ##     if ll_classifier_ep_train_Y[i][0] < 0:
        ##         plt.plot( ll_classifier_ep_train_X[i,:,2], 'bo-' )
        ##         ## plt.plot( ll_classifier_ep_train_X[i,:,1], ll_classifier_ep_train_X[i,:,2], 'bo' )
        ##     if ll_classifier_ep_train_Y[i][0] > 0:
        ##         plt.plot( ll_classifier_ep_train_X[i,:,2], 'r+-' )
        ##         ## plt.plot( ll_classifier_ep_train_X[i,:,1], ll_classifier_ep_train_X[i,:,2], 'r+' )
        ## ax1 = fig.add_subplot(212)        
        ## for i in xrange(len(ll_classifier_ep_train_X)):
        ##     if ll_classifier_ep_train_Y[i][0] < 0:
        ##         plt.plot(ll_classifier_ep_train_X[i,:,1], 'bo-')
        ##     if ll_classifier_ep_train_Y[i][0] > 0:
        ##         plt.plot( ll_classifier_ep_train_X[i,:,1], 'r+-' )
        ## plt.show()
        ## sys.exit()
        
        #-----------------------------------------------------------------------------------------
        # Diagonal co-variance
        #-----------------------------------------------------------------------------------------
        ml  = hmm.learning_hmm(nState, nEmissionDim, verbose=verbose) 
        if data_dict['handFeatures_noise']:
            ret = ml.fit(normalTrainData+\
                         np.random.normal(0.0, 0.03, np.shape(normalTrainData) )*HMM_dict['scale'], \
                         cov_mult=cov_mult, use_pkl=False, cov_type='diag')
        else:
            ret = ml.fit(normalTrainData, cov_mult=cov_mult, use_pkl=False, cov_type='diag')
        ## for i in xrange(nState):
        ##     for j in xrange(nEmissionDim):
        ##         for k in xrange(nEmissionDim):
        ##             if j != k:
        ##                 ml.B[i][1][j*nEmissionDim+k] = 0.0
        if ret == 'Failure' or np.isnan(ret): sys.exit()

        # Classifier training data
        ll_classifier_diag_train_X, ll_classifier_diag_train_Y, ll_classifier_diag_train_idx =\
          hmm.getHMMinducedFeaturesFromRawFeatures(ml, normalTrainData, abnormalTrainData, startIdx, add_logp_d,\
                                                   cov_type='diag')

        # Classifier test data
        ll_classifier_diag_test_X, ll_classifier_diag_test_Y, ll_classifier_diag_test_idx =\
          hmm.getHMMinducedFeaturesFromRawFeatures(ml, normalTestData, abnormalTestData, startIdx, add_logp_d,\
                                                   cov_type='diag')

        #-----------------------------------------------------------------------------------------
        d = {}
        d['nEmissionDim'] = ml.nEmissionDim
        d['A']            = ml.A 
        d['B']            = ml.B 
        d['pi']           = ml.pi
        d['F']            = ml.F
        d['nState']       = nState
        d['startIdx']     = startIdx
        d['nLength']      = nLength
        d['ll_classifier_train_X']       = ll_classifier_train_X
        d['ll_classifier_train_Y']       = ll_classifier_train_Y            
        d['ll_classifier_train_idx']     = ll_classifier_train_idx
        d['ll_classifier_test_X']        = ll_classifier_test_X
        d['ll_classifier_test_Y']        = ll_classifier_test_Y            
        d['ll_classifier_test_idx']      = ll_classifier_test_idx
        d['ll_classifier_diag_train_X']  = ll_classifier_diag_train_X
        d['ll_classifier_diag_train_Y']  = ll_classifier_diag_train_Y            
        d['ll_classifier_diag_train_idx']= ll_classifier_diag_train_idx
        d['ll_classifier_diag_test_X']   = ll_classifier_diag_test_X
        d['ll_classifier_diag_test_Y']   = ll_classifier_diag_test_Y            
        d['ll_classifier_diag_test_idx'] = ll_classifier_diag_test_idx
        d['ll_classifier_ep_train_X']    = ll_classifier_ep_train_X
        d['ll_classifier_ep_train_Y']    = ll_classifier_ep_train_Y            
        d['ll_classifier_ep_train_idx']  = ll_classifier_ep_train_idx
        d['ll_classifier_ep_test_X']     = ll_classifier_ep_test_X
        d['ll_classifier_ep_test_Y']     = ll_classifier_ep_test_Y            
        d['ll_classifier_ep_test_idx']   = ll_classifier_ep_test_idx        
        ut.save_pickle(d, modeling_pkl)

        
    #-----------------------------------------------------------------------------------------
    roc_pkl = os.path.join(processed_data_path, 'roc_'+task_name+'.pkl')
        
    if os.path.isfile(roc_pkl) is False or HMM_dict['renew']:        
        ROC_data = {}
    else:
        ROC_data = ut.load_pickle(roc_pkl)
        
    for i, method in enumerate(method_list):
        if method not in ROC_data.keys() or method in ROC_dict['update_list']: 
            ROC_data[method] = {}
            ROC_data[method]['complete'] = False 
            ROC_data[method]['tp_l'] = [ [] for j in xrange(nPoints) ]
            ROC_data[method]['fp_l'] = [ [] for j in xrange(nPoints) ]
            ROC_data[method]['tn_l'] = [ [] for j in xrange(nPoints) ]
            ROC_data[method]['fn_l'] = [ [] for j in xrange(nPoints) ]
            ROC_data[method]['delay_l'] = [ [] for j in xrange(nPoints) ]
            ROC_data[method]['tp_delay_l'] = [ [] for j in xrange(nPoints) ]
            ROC_data[method]['tp_idx_l'] = [ [] for j in xrange(nPoints) ]

    osvm_data = None ; bpsvm_data = None
    if 'osvm' in method_list  and ROC_data['osvm']['complete'] is False:
        osvm_data = dm.getPCAData(len(kFold_list), crossVal_pkl, \
                                  window=SVM_dict['raw_window_size'],
                                  use_test=True, use_pca=False)
    if 'bpsvm' in method_list and ROC_data['bpsvm']['complete'] is False:

        # get ll_cut_idx only for pos data
        pos_dict = []
        for idx in xrange(len(kFold_list)):
            modeling_pkl = os.path.join(processed_data_path, 'hmm_'+task_name+'_'+str(idx)+'.pkl')
            d            = ut.load_pickle(modeling_pkl)
            ll_classifier_train_X   = d['ll_classifier_train_X']
            ll_classifier_train_Y   = d['ll_classifier_train_Y']         
            ll_classifier_train_idx = d['ll_classifier_train_idx']
            l_cut_idx = dm.getHMMCuttingIdx(ll_classifier_train_X, \
                                         ll_classifier_train_Y, \
                                         ll_classifier_train_idx)
            idx_dict={'abnormal_train_cut_idx': l_cut_idx}
            pos_dict.append(idx_dict)
                    
        bpsvm_data = dm.getPCAData(len(kFold_list), crossVal_pkl, \
                                   window=SVM_dict['raw_window_size'], \
                                   pos_dict=pos_dict, use_test=True, use_pca=False)

    if find_param:
        #find the best parameters
        for method in method_list:
            if method == 'osvm' or method == 'bpsvm' or 'osvm' in method: continue
            find_ROC_param_range(method, task_name, processed_data_path, param_dict, \
                                 add_print="eval_all")            
        sys.exit()
                                   
    # parallelization
    if debug: n_jobs=1
    else: n_jobs=-1
    r = Parallel(n_jobs=n_jobs, verbose=50)(delayed(cf.run_classifiers)( idx, processed_data_path, task_name, \
                                                                         method, ROC_data, \
                                                                         ROC_dict, AE_dict, \
                                                                         SVM_dict, HMM_dict, \
                                                                         raw_data=(osvm_data,bpsvm_data),\
                                                                         startIdx=startIdx, nState=nState) \
                                                                         for idx in xrange(len(kFold_list)) \
                                                                         for method in method_list )
                                                                  
    l_data = r
    print "finished to run run_classifiers"

    for i in xrange(len(l_data)):
        for j in xrange(nPoints):
            try:
                method = l_data[i].keys()[0]
            except:
                print l_data[i]
                sys.exit()
            if ROC_data[method]['complete'] == True: continue
            ROC_data[method]['tp_l'][j] += l_data[i][method]['tp_l'][j]
            ROC_data[method]['fp_l'][j] += l_data[i][method]['fp_l'][j]
            ROC_data[method]['tn_l'][j] += l_data[i][method]['tn_l'][j]
            ROC_data[method]['fn_l'][j] += l_data[i][method]['fn_l'][j]
            ROC_data[method]['delay_l'][j] += l_data[i][method]['delay_l'][j]
            ROC_data[method]['tp_delay_l'][j].append( l_data[i][method]['delay_l'][j] )
            ROC_data[method]['tp_idx_l'][j].append( l_data[i][method]['tp_idx_l'][j] )

    for i, method in enumerate(method_list):
        ROC_data[method]['complete'] = True

    ut.save_pickle(ROC_data, roc_pkl)
        
    #-----------------------------------------------------------------------------------------
    # ---------------- ROC Visualization ----------------------
    roc_info(method_list, ROC_data, nPoints, delay_plot=delay_plot, no_plot=no_plot, save_pdf=save_pdf, \
             timeList=timeList)


def evaluation_step_noise(subject_names, task_name, raw_data_path, processed_data_path, param_dict,\
                          data_renew=False, save_pdf=False, verbose=False, debug=False,\
                          no_plot=False, delay_plot=False, find_param=False):

    ## Parameters
    # data
    data_dict  = param_dict['data_param']
    data_renew = data_dict['renew']
    dim        = len(data_dict['handFeatures'])
    # AE
    AE_dict    = param_dict['AE']
    # HMM
    HMM_dict   = param_dict['HMM']
    nState     = HMM_dict['nState']
    cov        = HMM_dict['cov']
    add_logp_d = HMM_dict.get('add_logp_d', False)
    # SVM
    SVM_dict   = param_dict['SVM']
    # ROC
    ROC_dict = param_dict['ROC']

    # reference data #TODO
    ref_data_path = os.path.join(processed_data_path, '../'+str(data_dict['downSampleSize'])+\
                                 '_'+str(dim))
    modeling_pkl_prefix = 'hmm_step_'+task_name

    #------------------------------------------
    # Get features
    if os.path.isdir(processed_data_path) is False:
        os.system('mkdir -p '+processed_data_path)

    crossVal_pkl = os.path.join(ref_data_path, 'cv_'+task_name+'.pkl')
    
    if os.path.isfile(crossVal_pkl) and data_renew is False:
        d = ut.load_pickle(crossVal_pkl)
        kFold_list  = d['kFoldList']
    else: sys.exit()

    #-----------------------------------------------------------------------------------------
    # parameters
    startIdx    = 4
    method_list = ROC_dict['methods'] 
    nPoints     = ROC_dict['nPoints']

    successData = d['successData']
    failureData = d['failureData']
    param_dict2  = d['param_dict']
    if 'timeList' in param_dict2.keys():
        timeList = param_dict2['timeList'][startIdx:]
    else: timeList = None

    #-----------------------------------------------------------------------------------------
    # Training HMM, and getting classifier training and testing data
    for idx, (normalTrainIdx, abnormalTrainIdx, normalTestIdx, abnormalTestIdx) \
      in enumerate(kFold_list):

        if verbose: print idx, " : training hmm and getting classifier training and testing data"
            
        ref_modeling_pkl = os.path.join(ref_data_path, 'hmm_'+task_name+'_'+str(idx)+'.pkl')
        if os.path.isfile(ref_modeling_pkl) is False:
            print "No reference modeling file exists"
            sys.exit()
        
        modeling_pkl = os.path.join(processed_data_path, modeling_pkl_prefix+'_'+str(idx)+'.pkl')
        if not (os.path.isfile(modeling_pkl) is False or HMM_dict['renew'] or data_renew): continue

        # dim x sample x length
        normalTestData    = successData[:, normalTestIdx, :] * HMM_dict['scale']

        # training hmm
        if verbose: print "start to fit hmm"
        dd = ut.load_pickle(ref_modeling_pkl)
        nEmissionDim = dd['nEmissionDim']
        nLength      = len(normalTestData[0][0]) - startIdx

        # Classifier test data
        # random step noise
        abnormalTestData = copy.copy(normalTestData)
        samples = []
        step_idx_l = []
        ## step_mag = 10000000*HMM_dict['scale'] # need to varying it
        step_mag = 0.1*HMM_dict['scale'] # need to varying it
        for i in xrange(len(normalTestData[0])):
            step_idx_l.append(None)
        for i in xrange(len(abnormalTestData[0])):
            start_idx = np.random.randint(0, nLength/2, 1)[0]
            
            if start_idx < startIdx: start_idx=startIdx
            abnormalTestData[:,i,start_idx:] += step_mag
            step_idx_l.append(start_idx)

        ml = hmm.learning_hmm(nState, nEmissionDim, verbose=False)
        ml.set_hmm_object(dd['A'], dd['B'], dd['pi'])            

        # Classifier test data
        ll_classifier_test_X, ll_classifier_test_Y, ll_classifier_test_idx =\
          hmm.getHMMinducedFeaturesFromRawFeatures(ml, normalTestData, abnormalTestData, startIdx, add_logp_d)

        #-----------------------------------------------------------------------------------------
        d = {}
        d['nEmissionDim'] = nEmissionDim
        d['A']            = dd['A'] 
        d['B']            = dd['B'] 
        d['pi']           = dd['pi']
        d['F']            = dd['F']
        d['nState']       = nState
        d['startIdx']     = startIdx
        d['ll_classifier_train_X']   = dd['ll_classifier_train_X']
        d['ll_classifier_train_Y']   = dd['ll_classifier_train_Y']
        d['ll_classifier_train_idx'] = dd['ll_classifier_train_idx']
        d['ll_classifier_test_X']    = ll_classifier_test_X
        d['ll_classifier_test_Y']    = ll_classifier_test_Y            
        d['ll_classifier_test_idx']  = ll_classifier_test_idx
        d['nLength']      = nLength
        d['step_idx_l']   = step_idx_l
        ut.save_pickle(d, modeling_pkl)

    ## fig = plt.figure()
    ## ## modeling_pkl = os.path.join(processed_data_path, modeling_pkl_prefix+'_'+str(0)+'.pkl')
    ## ## modeling_pkl = os.path.join(ref_data_path, 'hmm_'+task_name+'_'+str(0)+'.pkl')
    ## d = ut.load_pickle(modeling_pkl)
    ## ll_classifier_test_X = d['ll_classifier_test_X']
    ## ll_classifier_test_Y = d['ll_classifier_test_Y']
    ## print np.shape(ll_classifier_test_Y)
    ## for i in xrange(len(ll_classifier_test_X)):        
    ##     if ll_classifier_test_Y[i][0] > 0: continue
    ##     print "test normal: ", np.shape(ll_classifier_test_X[i])        
    ##     x = ll_classifier_test_X[i]
    ##     plt.plot(np.argmax(np.array(x)[:,2:],axis=1), np.array(x)[:,0], 'b-')
    ## plt.show()

    ## sys.exit()

    #-----------------------------------------------------------------------------------------
    roc_pkl = os.path.join(processed_data_path, 'roc_noise_'+task_name+'.pkl')
    if os.path.isfile(roc_pkl) is False or HMM_dict['renew'] or SVM_dict['renew']:        
        ROC_data = {}
    else:
        ROC_data = ut.load_pickle(roc_pkl)
        
    for i, method in enumerate(method_list):
        if method not in ROC_data.keys() or method in ROC_dict['update_list'] or SVM_dict['renew']:            
            ROC_data[method] = {}
            ROC_data[method]['complete'] = False 
            ROC_data[method]['tp_l'] = [ [] for j in xrange(nPoints) ]
            ROC_data[method]['fp_l'] = [ [] for j in xrange(nPoints) ]
            ROC_data[method]['tn_l'] = [ [] for j in xrange(nPoints) ]
            ROC_data[method]['fn_l'] = [ [] for j in xrange(nPoints) ]
            ROC_data[method]['delay_l'] = [ [] for j in xrange(nPoints) ]


    osvm_data = None ; bpsvm_data = None
    if 'bpsvm' in method_list and ROC_data['bpsvm']['complete'] is False:

        # get ll_cut_idx only for pos data
        pos_dict  = []
        drop_dict = []
        for idx in xrange(len(kFold_list)):
            modeling_pkl = os.path.join(processed_data_path, 'hmm_drop_'+task_name+'_'+str(idx)+'.pkl')
            d            = ut.load_pickle(modeling_pkl)
            ll_classifier_train_X   = d['ll_classifier_train_X']
            ll_classifier_train_Y   = d['ll_classifier_train_Y']         
            ll_classifier_train_idx = d['ll_classifier_train_idx']
            l_cut_idx = dm.getHMMCuttingIdx(ll_classifier_train_X, \
                                         ll_classifier_train_Y, \
                                         ll_classifier_train_idx)
            idx_dict={'abnormal_train_cut_idx': l_cut_idx}
            pos_dict.append(idx_dict)
            drop_dict.append([d['drop_idx_l'], d['drop_length']])
                    
        bpsvm_data = dm.getPCAData(len(kFold_list), crossVal_pkl, \
                                   window=SVM_dict['raw_window_size'], \
                                   pos_dict=pos_dict, use_test=True, use_pca=False,
                                   test_drop_elements=drop_dict)

    # parallelization
    if debug: n_jobs=1
    else: n_jobs=-1
    r = Parallel(n_jobs=n_jobs, verbose=50)(delayed(cf.run_classifiers)( idx, processed_data_path, task_name, \
                                                                 method, ROC_data, \
                                                                 ROC_dict, AE_dict, \
                                                                 SVM_dict, HMM_dict, \
                                                                 raw_data=(osvm_data,bpsvm_data),\
                                                                 startIdx=startIdx, nState=nState,\
                                                                 modeling_pkl_prefix=modeling_pkl_prefix,\
                                                                 delay_estimation=True) \
                                                                 for idx in xrange(len(kFold_list)) \
                                                                 for method in method_list )
    l_data = r
    print "finished to run run_classifiers"

    for i in xrange(len(l_data)):
        for j in xrange(nPoints):
            try:
                method = l_data[i].keys()[0]
            except:
                print l_data[i]
                sys.exit()
            if ROC_data[method]['complete'] == True: continue
            ROC_data[method]['tp_l'][j] += l_data[i][method]['tp_l'][j]
            ROC_data[method]['fp_l'][j] += l_data[i][method]['fp_l'][j]
            ROC_data[method]['tn_l'][j] += l_data[i][method]['tn_l'][j]
            ROC_data[method]['fn_l'][j] += l_data[i][method]['fn_l'][j]
            ROC_data[method]['delay_l'][j] += l_data[i][method]['delay_l'][j]

    for i, method in enumerate(method_list):
        ROC_data[method]['complete'] = True

    ut.save_pickle(ROC_data, roc_pkl)
        
    #-----------------------------------------------------------------------------------------
    # ---------------- ROC Visualization ----------------------
    ## roc_info(method_list, ROC_data, nPoints, delay_plot=delay_plot, no_plot=no_plot, save_pdf=save_pdf)
    delay_info(method_list, ROC_data, nPoints, no_plot=no_plot, save_pdf=save_pdf, timeList=timeList)
             

def evaluation_noise(subject_names, task_name, raw_data_path, processed_data_path, param_dict,\
                     data_renew=False, save_pdf=False, verbose=False, debug=False,\
                     no_plot=False):

    ## Parameters
    # data
    data_dict  = param_dict['data_param']
    data_renew = data_dict['renew']
    # AE
    AE_dict     = param_dict['AE']
    # HMM
    HMM_dict   = param_dict['HMM']
    nState     = HMM_dict['nState']
    cov        = HMM_dict['cov']
    add_logp_d = HMM_dict.get('add_logp_d', False)
    # SVM
    SVM_dict   = param_dict['SVM']

    # ROC
    ROC_dict = param_dict['ROC']
    
    #------------------------------------------

    crossVal_pkl = os.path.join(processed_data_path, 'cv_'+task_name+'.pkl')    
    if os.path.isfile(crossVal_pkl) and data_renew is False:
        d = ut.load_pickle(crossVal_pkl)
        kFold_list  = d['kFoldList']
    else:
        '''
        Use augmented data? if nAugment is 0, then aug_successData = successData
        '''        
        sys.exit()
        
    #-----------------------------------------------------------------------------------------
    # parameters
    startIdx    = 4
    method_list = ROC_dict['methods'] 
    nPoints     = ROC_dict['nPoints']

    # temp
    ## kFold_list = kFold_list[0:1]

    #-----------------------------------------------------------------------------------------
    # add noise
    modeling_pkl_prefix = 'hmm_'+task_name+'_noise'
    for idx in xrange(len(kFold_list)):
        modeling_noise_pkl = os.path.join(processed_data_path, modeling_pkl_prefix+'_'+str(idx)+'.pkl')
        if os.path.isfile(modeling_noise_pkl) and HMM_dict['renew'] is False: continue
        
        modeling_pkl = os.path.join(processed_data_path, 'hmm_'+task_name+'_'+str(idx)+'.pkl')

        d = ut.load_pickle(modeling_pkl)
        ll_classifier_train_X   = d['ll_classifier_train_X']
        ll_classifier_train_Y   = d['ll_classifier_train_Y']         
        ll_classifier_train_idx = d['ll_classifier_train_idx']
        ll_classifier_test_X    = d['ll_classifier_test_X']  
        ll_classifier_test_Y    = d['ll_classifier_test_Y']
        ll_classifier_test_idx  = d['ll_classifier_test_idx']

        ll_classifier_test_X    = ll_classifier_train_X
        ll_classifier_test_Y    = ll_classifier_train_Y
        ll_classifier_test_idx  = ll_classifier_train_idx
        
        # exclude only normal data
        l_normal_test_X = []
        l_normal_test_Y = []
        l_normal_test_idx = []
        for i in xrange(len(ll_classifier_test_Y)):
            if ll_classifier_test_Y[i][0] > 0.0:
                continue
            l_normal_test_X.append( ll_classifier_test_X[i] )
            l_normal_test_Y.append( ll_classifier_test_Y[i] )
            l_normal_test_idx.append( ll_classifier_test_idx[i] )

        # get abnormal minimum likelihood
        logp_min = np.amin(np.array(ll_classifier_test_X)[:,:,0])
        if logp_min > 0:
            print "min loglikelihood is positive!!!!!!!!!!!!!!!!!!!!"
            sys.exit()

        #temp
        logp_min = -1000
        
        # add random extreme noise
        # maybe sample x length x features
        offset = 30
        l_abnormal_test_X = []
        l_abnormal_test_Y = (np.array(l_normal_test_Y)*-1.0).tolist()
        
        l_abnormal_test_idx = copy.deepcopy(l_normal_test_idx)
        for i in xrange(len(l_normal_test_X)):
            length  = len(l_normal_test_X[i])
            rnd_idx = random.randint(0+offset,length-1-offset)

            l_x = copy.deepcopy(l_normal_test_X[i])
            l_x = np.array(l_x)
            l_x[rnd_idx:rnd_idx+1,0] += logp_min
            ## l_x[rnd_idx][0]   += random.uniform(10.0*logp_min, 20.0*logp_min)
            ## print l_x[rnd_idx][0], np.shape(l_x)
            
            ## if add_logp_d:
            ##     l_x[rnd_idx][1] /= l_normal_test_X[i][rnd_idx][0] - l_normal_test_X[i][rnd_idx-1][0]
            ##     l_x[rnd_idx][1] *= l_x[rnd_idx][0]-l_x[rnd_idx-1][0] 

            ##     l_x[rnd_idx+1][1] /= l_normal_test_X[i][rnd_idx+1][0] - l_normal_test_X[i][rnd_idx][0]
            ##     l_x[rnd_idx+1][1] *= l_x[rnd_idx+1][0]-l_x[rnd_idx][0]
            ##     print "added random noise!!!"

            l_abnormal_test_X.append(l_x)
            
        new_test_X   = l_normal_test_X + l_abnormal_test_X 
        new_test_Y   = l_normal_test_Y + l_abnormal_test_Y 
        new_test_idx = l_normal_test_idx + l_abnormal_test_idx 

        d['ll_classifier_test_X']  = new_test_X
        d['ll_classifier_test_Y']  = new_test_Y
        d['ll_classifier_test_idx']= new_test_idx        
        ut.save_pickle(d, modeling_noise_pkl)
                 
    #-----------------------------------------------------------------------------------------
    roc_pkl = os.path.join(processed_data_path, 'roc_noise_'+task_name+'.pkl')
        
    if os.path.isfile(roc_pkl) is False or HMM_dict['renew']:        
        ROC_data = {}
    else:
        ROC_data = ut.load_pickle(roc_pkl)

    for ii, method in enumerate(method_list):
        if method not in ROC_data.keys() or method in ROC_dict['update_list']: 
            ROC_data[method] = {}
            ROC_data[method]['complete'] = False 
            ROC_data[method]['tp_l'] = [ [] for j in xrange(nPoints) ]
            ROC_data[method]['fp_l'] = [ [] for j in xrange(nPoints) ]
            ROC_data[method]['tn_l'] = [ [] for j in xrange(nPoints) ]
            ROC_data[method]['fn_l'] = [ [] for j in xrange(nPoints) ]
            ROC_data[method]['delay_l'] = [ [] for j in xrange(nPoints) ]

            # parallelization
            if debug: n_jobs=1
            else: n_jobs=-1
            r = Parallel(n_jobs=n_jobs, verbose=50)(delayed(cf.run_classifiers)( idx, processed_data_path, \
                                                                              task_name, \
                                                                              method, ROC_data, \
                                                                              ROC_dict, AE_dict, \
                                                                              SVM_dict, HMM_dict,\
                                                                              startIdx=startIdx, nState=nState,\
                                                                              modeling_pkl_prefix=modeling_pkl_prefix) \
                                                                              for idx in xrange(len(kFold_list)) \
                                                                              for method in method_list )
            l_data = r
            print "finished to run run_classifiers"

            for i in xrange(len(l_data)):
                for j in xrange(nPoints):
                    try:
                        method = l_data[i].keys()[0]
                    except:
                        print l_data[i]
                        sys.exit()
                    if ROC_data[method]['complete'] == True: continue
                    ROC_data[method]['tp_l'][j] += l_data[i][method]['tp_l'][j]
                    ROC_data[method]['fp_l'][j] += l_data[i][method]['fp_l'][j]
                    ROC_data[method]['tn_l'][j] += l_data[i][method]['tn_l'][j]
                    ROC_data[method]['fn_l'][j] += l_data[i][method]['fn_l'][j]
                    ROC_data[method]['delay_l'][j] += l_data[i][method]['delay_l'][j]

    for i, method in enumerate(method_list):
        ROC_data[method]['complete'] = True

    ut.save_pickle(ROC_data, roc_pkl)
        
    #-----------------------------------------------------------------------------------------
    # ---------------- ROC Result ----------------------
    ## modeling_noise_pkl = os.path.join(processed_data_path, modeling_pkl_prefix+'_'+str(0)+'.pkl')
    ## d = ut.load_pickle(modeling_noise_pkl)
    ## ll_classifier_test_Y    = d['ll_classifier_test_Y']
    roc_info(method_list, ROC_data, nPoints, delay_plot=delay_plot, no_plot=no_plot, save_pdf=save_pdf)


def evaluation_drop(subject_names, task_name, raw_data_path, processed_data_path, param_dict,\
                    data_renew=False, save_pdf=False, verbose=False, debug=False,\
                    no_plot=False, delay_plot=False, find_param=False):

    ## Parameters
    # data
    data_dict  = param_dict['data_param']
    data_renew = data_dict['renew']
    dim        = len(data_dict['handFeatures'])
    # AE
    AE_dict    = param_dict['AE']
    # HMM
    HMM_dict   = param_dict['HMM']
    nState     = HMM_dict['nState']
    cov        = HMM_dict['cov']
    add_logp_d = HMM_dict.get('add_logp_d', False)
    # SVM
    SVM_dict   = param_dict['SVM']

    # ROC
    ROC_dict = param_dict['ROC']

    # reference data #TODO
    ref_data_path = os.path.join(processed_data_path, '../'+str(data_dict['downSampleSize'])+\
                                 '_'+str(dim))
    modeling_pkl_prefix = 'hmm_drop_'+task_name


    #------------------------------------------
    # Get features
    if os.path.isdir(processed_data_path) is False:
        os.system('mkdir -p '+processed_data_path)

    crossVal_pkl = os.path.join(ref_data_path, 'cv_'+task_name+'.pkl')
    
    if os.path.isfile(crossVal_pkl) and data_renew is False:
        d = ut.load_pickle(crossVal_pkl)
        kFold_list  = d['kFoldList']
    else: sys.exit()

    #-----------------------------------------------------------------------------------------
    # parameters
    startIdx    = 4
    method_list = ROC_dict['methods'] 
    nPoints     = ROC_dict['nPoints']

    successData = d['successData']
    failureData = d['failureData']
    param_dict2  = d['param_dict']
    if 'timeList' in param_dict2.keys():
        timeList = param_dict2['timeList'][startIdx:]
    else: timeList = None


    #-----------------------------------------------------------------------------------------
    # Training HMM, and getting classifier training and testing data
    for idx, (normalTrainIdx, abnormalTrainIdx, normalTestIdx, abnormalTestIdx) \
      in enumerate(kFold_list):

        if verbose: print idx, " : training hmm and getting classifier training and testing data"
            
        ref_modeling_pkl = os.path.join(ref_data_path, 'hmm_'+task_name+'_'+str(idx)+'.pkl')
        if os.path.isfile(ref_modeling_pkl) is False:
            print "No reference modeling file exists"
            sys.exit()
        
        modeling_pkl = os.path.join(processed_data_path, modeling_pkl_prefix+'_'+str(idx)+'.pkl')
        if not (os.path.isfile(modeling_pkl) is False or HMM_dict['renew'] or data_renew): continue

        # dim x sample x length
        normalTestData    = successData[:, normalTestIdx, :] 
        abnormalTestData  = failureData[:, abnormalTestIdx, :] 

        # scaling
        if verbose: print "scaling data"
        normalTestData    *= HMM_dict['scale']
        abnormalTestData  *= HMM_dict['scale']

        # training hmm
        if verbose: print "start to fit hmm"
        dd = ut.load_pickle(ref_modeling_pkl)
        nEmissionDim = dd['nEmissionDim']
        A  = dd['A']
        B  = dd['B']
        pi = dd['pi']
        F  = dd['F']
        
        nLength      = len(normalTestData[0][0]) - startIdx
        
        #-----------------------------------------------------------------------------------------
        # Classifier test data
        #-----------------------------------------------------------------------------------------
        testDataX = []
        testDataY = []
        for i in xrange(nEmissionDim):
            temp = np.vstack([normalTestData[i], abnormalTestData[i]])
            testDataX.append( temp )

        testDataY = np.hstack([ -np.ones(len(normalTestData[0])), \
                                np.ones(len(abnormalTestData[0])) ])


        # random drop
        samples = []
        drop_idx_l = []
        drop_length = 10
        drop_prop = 0.5
        for i in xrange(len(testDataX[0])):
            ## rnd_idx_l = np.unique( np.random.randint(0, nLength-1, 20) )
            ## start_idx = np.random.randint(0, nLength-1, 1)[0]
            
            ## start_idx = np.random.randint(20, 80, 1)[0]
            ## if start_idx < startIdx: start_idx=startIdx
            ## end_idx   = start_idx+drop_length
            ## if end_idx > nLength-1: end_idx = nLength-1
            ## rnd_idx_l = range(start_idx, end_idx)
            drop_flag_l = np.random.choice(2, nLength, p=[drop_prop, 1.0-drop_prop])
            rnd_idx_l = [j for j in xrange(nLength) if drop_flag_l[j] == 0]

            sample = []
            for j in xrange(len(testDataX)):
                sample.append( np.delete( testDataX[j][i], rnd_idx_l ) )

            samples.append(sample)
            drop_idx_l.append(rnd_idx_l)
        testDataX = np.swapaxes(samples, 0, 1)

        r = Parallel(n_jobs=-1)(delayed(hmm.computeLikelihoods)(i, A, B, pi, F, \
                                                                [ testDataX[j][i] for j in xrange(nEmissionDim) ], \
                                                                nEmissionDim, nState,\
                                                                startIdx=startIdx, \
                                                                bPosterior=True)
                                                                for i in xrange(len(testDataX[0])))
        _, ll_classifier_test_idx, ll_logp, ll_post = zip(*r)

        # nSample x nLength
        ll_classifier_test_X, ll_classifier_test_Y = \
          hmm.getHMMinducedFeatures(ll_logp, ll_post, testDataY, c=1.0, add_delta_logp=add_logp_d)

        #-----------------------------------------------------------------------------------------
        d = {}
        d['nEmissionDim'] = nEmissionDim
        d['A']            = A 
        d['B']            = B 
        d['pi']           = pi
        d['F']            = F
        d['nState']       = nState
        d['startIdx']     = startIdx
        d['ll_classifier_train_X']   = dd['ll_classifier_train_X']
        d['ll_classifier_train_Y']   = dd['ll_classifier_train_Y']
        d['ll_classifier_train_idx'] = dd['ll_classifier_train_idx']
        d['ll_classifier_test_X']    = ll_classifier_test_X
        d['ll_classifier_test_Y']    = ll_classifier_test_Y            
        d['ll_classifier_test_idx']  = ll_classifier_test_idx
        d['nLength']      = nLength
        d['drop_idx_l']   = drop_idx_l
        d['drop_length']  = drop_length
        ut.save_pickle(d, modeling_pkl)

    ## fig = plt.figure()
    ## ## modeling_pkl = os.path.join(processed_data_path, modeling_pkl_prefix+'_'+str(0)+'.pkl')
    ## ## modeling_pkl = os.path.join(ref_data_path, 'hmm_'+task_name+'_'+str(0)+'.pkl')
    ## d = ut.load_pickle(modeling_pkl)
    ## ll_classifier_test_X = d['ll_classifier_test_X']
    ## ll_classifier_test_Y = d['ll_classifier_test_Y']
    ## print np.shape(ll_classifier_test_Y)
    ## for i in xrange(len(ll_classifier_test_X)):        
    ##     if ll_classifier_test_Y[i][0] > 0: continue
    ##     print "test normal: ", np.shape(ll_classifier_test_X[i])        
    ##     x = ll_classifier_test_X[i]
    ##     plt.plot(np.argmax(np.array(x)[:,2:],axis=1), np.array(x)[:,0], 'b-')
    ## plt.show()

    ## sys.exit()


    #-----------------------------------------------------------------------------------------
    roc_pkl = os.path.join(processed_data_path, 'roc_drop_'+task_name+'.pkl')
    if os.path.isfile(roc_pkl) is False or HMM_dict['renew']:        
        ROC_data = {}
    else:
        ROC_data = ut.load_pickle(roc_pkl)
        
    for i, method in enumerate(method_list):
        if method not in ROC_data.keys() or method in ROC_dict['update_list']:            
            ROC_data[method] = {}
            ROC_data[method]['complete'] = False 
            ROC_data[method]['tp_l'] = [ [] for j in xrange(nPoints) ]
            ROC_data[method]['fp_l'] = [ [] for j in xrange(nPoints) ]
            ROC_data[method]['tn_l'] = [ [] for j in xrange(nPoints) ]
            ROC_data[method]['fn_l'] = [ [] for j in xrange(nPoints) ]
            ROC_data[method]['delay_l'] = [ [] for j in xrange(nPoints) ]


    osvm_data = None ; bpsvm_data = None
    if 'bpsvm' in method_list and ROC_data['bpsvm']['complete'] is False:

        # get ll_cut_idx only for pos data
        pos_dict  = []
        drop_dict = []
        for idx in xrange(len(kFold_list)):
            modeling_pkl = os.path.join(processed_data_path, 'hmm_drop_'+task_name+'_'+str(idx)+'.pkl')
            d            = ut.load_pickle(modeling_pkl)
            ll_classifier_train_X   = d['ll_classifier_train_X']
            ll_classifier_train_Y   = d['ll_classifier_train_Y']         
            ll_classifier_train_idx = d['ll_classifier_train_idx']
            l_cut_idx = dm.getHMMCuttingIdx(ll_classifier_train_X, \
                                         ll_classifier_train_Y, \
                                         ll_classifier_train_idx)
            idx_dict={'abnormal_train_cut_idx': l_cut_idx}
            pos_dict.append(idx_dict)
            drop_dict.append([d['drop_idx_l'], d['drop_length']])
                    
        bpsvm_data = dm.getPCAData(len(kFold_list), crossVal_pkl, \
                                   window=SVM_dict['raw_window_size'], \
                                   pos_dict=pos_dict, use_test=True, use_pca=False,
                                   test_drop_elements=drop_dict)


    if find_param:
        for method in method_list:
            if method == 'osvm' or method == 'bpsvm' or 'osvm' in method: continue
            find_ROC_param_range(method, task_name, processed_data_path, param_dict, \
                                 modeling_pkl_prefix='hmm_drop_'+task_name, \
                                 add_print="eval_drop")
            
        sys.exit()

    # parallelization
    if debug: n_jobs=1
    else: n_jobs=-1
    r = Parallel(n_jobs=n_jobs, verbose=50)(delayed(cf.run_classifiers)( idx, processed_data_path, task_name, \
                                                                 method, ROC_data, \
                                                                 ROC_dict, AE_dict, \
                                                                 SVM_dict, HMM_dict, \
                                                                 raw_data=(osvm_data,bpsvm_data),\
                                                                 startIdx=startIdx, nState=nState,\
                                                                 modeling_pkl_prefix=modeling_pkl_prefix) \
                                                                 for idx in xrange(len(kFold_list)) \
                                                                 for method in method_list )
                                                                  
    l_data = r
    print "finished to run run_classifiers"

    for i in xrange(len(l_data)):
        for j in xrange(nPoints):
            try:
                method = l_data[i].keys()[0]
            except:
                print l_data[i]
                sys.exit()
            if ROC_data[method]['complete'] == True: continue
            ROC_data[method]['tp_l'][j] += l_data[i][method]['tp_l'][j]
            ROC_data[method]['fp_l'][j] += l_data[i][method]['fp_l'][j]
            ROC_data[method]['tn_l'][j] += l_data[i][method]['tn_l'][j]
            ROC_data[method]['fn_l'][j] += l_data[i][method]['fn_l'][j]
            ROC_data[method]['delay_l'][j] += l_data[i][method]['delay_l'][j]

    for i, method in enumerate(method_list):
        ROC_data[method]['complete'] = True

    ut.save_pickle(ROC_data, roc_pkl)
        
    #-----------------------------------------------------------------------------------------
    # ---------------- ROC Visualization ----------------------
    roc_info(method_list, ROC_data, nPoints, delay_plot=delay_plot, no_plot=no_plot, save_pdf=save_pdf)



def evaluation_freq(subject_names, task_name, raw_data_path, processed_data_path, param_dict,\
                    refSampleSize,\
                    data_renew=False, save_pdf=False, verbose=False, debug=False,\
                    no_plot=False, delay_plot=False):

    ## Parameters
    # data
    data_dict  = param_dict['data_param']
    data_renew = data_dict['renew']
    # AE
    AE_dict    = param_dict['AE']
    # HMM
    HMM_dict   = param_dict['HMM']
    nState     = HMM_dict['nState']
    cov        = HMM_dict['cov']
    add_logp_d = HMM_dict.get('add_logp_d', False)
    # SVM
    SVM_dict   = param_dict['SVM']

    # ROC
    ROC_dict = param_dict['ROC']

    # reference data #TODO
    ref_data_path = os.path.join(processed_data_path, '../'+str(refSampleSize)+'_4')
    modeling_pkl_prefix = 'hmm_freq_'+task_name


    #------------------------------------------
    # Get features
    if os.path.isdir(processed_data_path) is False:
        os.system('mkdir -p '+processed_data_path)

    crossVal_pkl = os.path.join(processed_data_path, 'cv_'+task_name+'.pkl')
    
    if os.path.isfile(crossVal_pkl) and data_renew is False:
        d = ut.load_pickle(crossVal_pkl)
        kFold_list  = d['kFoldList']
    else:
        '''
        Use augmented data? if nAugment is 0, then aug_successData = successData
        '''        
        d = dm.getDataSet(subject_names, task_name, raw_data_path, \
                           processed_data_path, data_dict['rf_center'], data_dict['local_range'],\
                           downSampleSize=data_dict['downSampleSize'], scale=1.0,\
                           ae_data=AE_dict['switch'],\
                           handFeatures=data_dict['handFeatures'], \
                           rawFeatures=AE_dict['rawFeatures'],\
                           cut_data=data_dict['cut_data'], \
                           data_renew=data_renew)

        # TODO: hardcoded...
        refCrossVal_pkl = os.path.join(ref_data_path, 'cv_'+task_name+'.pkl')
        dd = ut.load_pickle(refCrossVal_pkl)
        kFold_list  = dd['kFoldList']
                           
        d['kFoldList']   = kFold_list
        ut.save_pickle(d, crossVal_pkl)


    #-----------------------------------------------------------------------------------------
    # parameters
    startIdx    = 4
    method_list = ROC_dict['methods'] 
    nPoints     = ROC_dict['nPoints']

    successData = d['successData']
    failureData = d['failureData']
    param_dict2  = d['param_dict']
    if 'timeList' in param_dict2.keys():
        timeList    = param_dict2['timeList'][startIdx:]
    else: timeList = None


    #-----------------------------------------------------------------------------------------
    # Training HMM, and getting classifier training and testing data
    for idx, (normalTrainIdx, abnormalTrainIdx, normalTestIdx, abnormalTestIdx) \
      in enumerate(kFold_list):

        if verbose: print idx, " : training hmm and getting classifier training and testing data"
            

        ref_modeling_pkl = os.path.join(ref_data_path, 'hmm_'+task_name+'_'+str(idx)+'.pkl')
        if os.path.isfile(ref_modeling_pkl) is False:
            print "No reference modeling file exists"
            sys.exit()
        
        modeling_pkl = os.path.join(processed_data_path, modeling_pkl_prefix+'_'+str(idx)+'.pkl')
        if not (os.path.isfile(modeling_pkl) is False or HMM_dict['renew'] or data_renew): continue

        # dim x sample x length
        normalTestData    = successData[:, normalTestIdx, :] 
        abnormalTestData  = failureData[:, abnormalTestIdx, :] 

        # scaling
        if verbose: print "scaling data"
        normalTestData    *= HMM_dict['scale']
        abnormalTestData  *= HMM_dict['scale']

        # training hmm
        if verbose: print "start to fit hmm"
        dd = ut.load_pickle(ref_modeling_pkl)
        nEmissionDim = dd['nEmissionDim']
        A  = dd['A']
        B  = dd['B']
        pi = dd['pi']
        F  = dd['F']
        
        nLength      = len(normalTestData[0][0]) - startIdx
        
        #-----------------------------------------------------------------------------------------
        # Classifier test data
        #-----------------------------------------------------------------------------------------
        testDataX = []
        testDataY = []
        for i in xrange(nEmissionDim):
            temp = np.vstack([normalTestData[i], abnormalTestData[i]])
            testDataX.append( temp )

        testDataY = np.hstack([ -np.ones(len(normalTestData[0])), \
                                np.ones(len(abnormalTestData[0])) ])

        r = Parallel(n_jobs=-1)(delayed(hmm.computeLikelihoods)(i, A, B, pi, F, \
                                                                [ testDataX[j][i] for j in xrange(nEmissionDim) ], \
                                                                nEmissionDim, nState,\
                                                                startIdx=startIdx, \
                                                                bPosterior=True)
                                                                for i in xrange(len(testDataX[0])))
        _, ll_classifier_test_idx, ll_logp, ll_post = zip(*r)

        # nSample x nLength
        ll_classifier_test_X, ll_classifier_test_Y = \
          hmm.getHMMinducedFeatures(ll_logp, ll_post, testDataY, c=1.0, add_delta_logp=add_logp_d)

        #-----------------------------------------------------------------------------------------
        d = {}
        d['nEmissionDim'] = nEmissionDim
        d['A']            = A 
        d['B']            = B 
        d['pi']           = pi
        d['F']            = F
        d['nState']       = nState
        d['startIdx']     = startIdx
        d['ll_classifier_train_X']   = dd['ll_classifier_train_X']
        d['ll_classifier_train_Y']   = dd['ll_classifier_train_Y']
        d['ll_classifier_train_idx'] = dd['ll_classifier_train_idx']
        d['ll_classifier_test_X']    = ll_classifier_test_X
        d['ll_classifier_test_Y']    = ll_classifier_test_Y            
        d['ll_classifier_test_idx']  = ll_classifier_test_idx
        d['nLength']      = nLength
        ut.save_pickle(d, modeling_pkl)


    #-----------------------------------------------------------------------------------------
    roc_pkl = os.path.join(processed_data_path, 'roc_freq_'+task_name+'.pkl')
    if os.path.isfile(roc_pkl) is False or HMM_dict['renew']:        
        ROC_data = {}
    else:
        ROC_data = ut.load_pickle(roc_pkl)
        
    for i, method in enumerate(method_list):
        if method not in ROC_data.keys() or method in ROC_dict['update_list']:            
            ROC_data[method] = {}
            ROC_data[method]['complete'] = False 
            ROC_data[method]['tp_l'] = [ [] for j in xrange(nPoints) ]
            ROC_data[method]['fp_l'] = [ [] for j in xrange(nPoints) ]
            ROC_data[method]['tn_l'] = [ [] for j in xrange(nPoints) ]
            ROC_data[method]['fn_l'] = [ [] for j in xrange(nPoints) ]
            ROC_data[method]['delay_l'] = [ [] for j in xrange(nPoints) ]

    osvm_data = None ; bpsvm_data = None
    if 'bpsvm' in method_list and ROC_data['bpsvm']['complete'] is False:

        # get ll_cut_idx only for pos data
        pos_dict  = []
        for idx in xrange(len(kFold_list)):
            modeling_pkl = os.path.join(processed_data_path, modeling_pkl_prefix+'_'+str(idx)+'.pkl')
            d            = ut.load_pickle(modeling_pkl)
            ll_classifier_train_X   = d['ll_classifier_train_X']
            ll_classifier_train_Y   = d['ll_classifier_train_Y']         
            ll_classifier_train_idx = d['ll_classifier_train_idx']
            l_cut_idx = dm.getHMMCuttingIdx(ll_classifier_train_X, \
                                         ll_classifier_train_Y, \
                                         ll_classifier_train_idx)
            idx_dict={'abnormal_train_cut_idx': l_cut_idx}
            pos_dict.append(idx_dict)
                    
        bpsvm_data = dm.getPCAData(len(kFold_list), crossVal_pkl, \
                                   window=SVM_dict['raw_window_size'], \
                                   pos_dict=pos_dict, use_test=True, use_pca=False)

    # parallelization
    if debug: n_jobs=1
    else: n_jobs=-1
    r = Parallel(n_jobs=n_jobs, verbose=50)(delayed(cf.run_classifiers)( idx, processed_data_path, task_name, \
                                                                 method, ROC_data, \
                                                                 ROC_dict, AE_dict, \
                                                                 SVM_dict, HMM_dict, \
                                                                 raw_data=(osvm_data,bpsvm_data),\
                                                                 startIdx=startIdx, nState=nState,\
                                                                 modeling_pkl_prefix=modeling_pkl_prefix) \
                                                                 for idx in xrange(len(kFold_list)) \
                                                                 for method in method_list )
                                                                  
    l_data = r
    print "finished to run run_classifiers"

    for i in xrange(len(l_data)):
        for j in xrange(nPoints):
            try:
                method = l_data[i].keys()[0]
            except:
                print l_data[i]
                sys.exit()
            if ROC_data[method]['complete'] == True: continue
            ROC_data[method]['tp_l'][j] += l_data[i][method]['tp_l'][j]
            ROC_data[method]['fp_l'][j] += l_data[i][method]['fp_l'][j]
            ROC_data[method]['tn_l'][j] += l_data[i][method]['tn_l'][j]
            ROC_data[method]['fn_l'][j] += l_data[i][method]['fn_l'][j]
            ROC_data[method]['delay_l'][j] += l_data[i][method]['delay_l'][j]

    for i, method in enumerate(method_list):
        ROC_data[method]['complete'] = True

    ut.save_pickle(ROC_data, roc_pkl)
        
    #-----------------------------------------------------------------------------------------
    # ---------------- ROC Visualization ----------------------
    roc_info(method_list, ROC_data, nPoints, delay_plot=delay_plot, no_plot=no_plot, save_pdf=save_pdf)



                       
        

    ## # training set
    ## trainingData, param_dict = extractFeature(data_dict['trainData'], feature_list, local_range)

    ## # test set
    ## normalTestData, _ = extractFeature(data_dict['normalTestData'], feature_list, local_range, \
    ##                                         param_dict=param_dict)        
    ## abnormalTestData, _ = extractFeature(data_dict['abnormalTestData'], feature_list, local_range, \
    ##                                         param_dict=param_dict)

    ## print "======================================"
    ## print "Training data: ", np.shape(trainingData)
    ## print "Normal test data: ", np.shape(normalTestData)
    ## print "Abnormal test data: ", np.shape(abnormalTestData)
    ## print "======================================"

    ## visualization_hmm_data(feature_list, trainingData=trainingData, \
    ##                        normalTestData=normalTestData,\
    ##                        abnormalTestData=abnormalTestData, save_pdf=save_pdf)        
    

def data_selection(subject_names, task_name, raw_data_path, processed_data_path, \
                  downSampleSize=200, \
                  local_range=0.3, rf_center='kinEEPos', \
                  success_viz=True, failure_viz=False, \
                  raw_viz=False, save_pdf=False, \
                  modality_list=['audio'], data_renew=False, verbose=False):    

    ## success_list, failure_list = getSubjectFileList(raw_data_path, subject_names, task_name)
    
    # Success data
    successData = success_viz
    failureData = failure_viz

    count = 0
    while True:
        
        ## success_list, failure_list = getSubjectFileList(raw_data_path, subject_names, task_name)        
        ## print "-----------------------------------------------"
        ## print success_list[count]
        ## print "-----------------------------------------------"
        
        data_plot(subject_names, task_name, raw_data_path, processed_data_path,\
                  downSampleSize=downSampleSize, \
                  local_range=local_range, rf_center=rf_center, \
                  raw_viz=True, interp_viz=False, save_pdf=save_pdf,\
                  successData=successData, failureData=failureData,\
                  continuousPlot=True, \
                  modality_list=modality_list, data_renew=data_renew, verbose=verbose)

        break

        ## feedback  = raw_input('Do you want to exclude the data? (e.g. y:yes n:no else: exit): ')
        ## if feedback == 'y':
        ##     print "move data"
        ##     ## os.system('mv '+subject_names+' ')
        ##     data_renew = True

        ## elif feedback == 'n':
        ##     print "keep data"
        ##     data_renew = False
        ##     count += 1
        ## else:
        ##     break
   

def plotDecisionBoundaries(subjects, task, raw_data_path, save_data_path, param_dict,\
                           methods,\
                           success_viz=True, failure_viz=False, save_pdf=False,\
                           db_renew=False):
    from sklearn import preprocessing
    from sklearn.externals import joblib

    ## Parameters
    # data
    data_dict  = param_dict['data_param']
    # AE
    AE_dict     = param_dict['AE']
    # HMM
    HMM_dict = param_dict['HMM']
    nState   = HMM_dict['nState']
    cov      = HMM_dict['cov']
    # SVM
    SVM_dict = param_dict['SVM']
    # ROC
    ROC_dict = param_dict['ROC']
    nPoints  = 4 #ROC_dict['nPoints']

    foldIdx = 0

    # temp
    ROC_dict['progress_param_range'] = np.linspace(-5, 1., nPoints)
    ROC_dict['svm_param_range']      = np.logspace(-1.5, 0., nPoints)

    # Generative model ----------------------------------------------------------------------------
    if AE_dict['switch'] and AE_dict['add_option'] is not None:
        tag = ''
        for ft in AE_dict['add_option']:
            tag += ft[:2]
        modeling_pkl = os.path.join(save_data_path, 'hmm_'+task+'_raw_'+tag+'_'+str(foldIdx)+'.pkl')
    elif AE_dict['switch'] and AE_dict['add_option'] is None:
        modeling_pkl = os.path.join(save_data_path, 'hmm_'+task+'_raw_'+str(foldIdx)+'.pkl')
    else:
        modeling_pkl = os.path.join(save_data_path, 'hmm_'+task+'_'+str(foldIdx)+'.pkl')

    if os.path.isfile(modeling_pkl) is False:
        print "No HMM modeling file exists:", modeling_pkl
    else:
        d = ut.load_pickle(modeling_pkl)
        nEmissionDim = d['nEmissionDim'] 
        nState       = d['nState']    
        startIdx     = d['startIdx']     
        ll_classifier_train_X   = d['ll_classifier_train_X']  
        ll_classifier_train_Y   = d['ll_classifier_train_Y']             
        ll_classifier_train_idx = d['ll_classifier_train_idx']
        ll_classifier_test_X    = d['ll_classifier_test_X'] 
        ll_classifier_test_Y    = d['ll_classifier_test_Y']            
        ll_classifier_test_idx  = d['ll_classifier_test_idx'] 
        nLength                 = d['nLength']

    # Get time
    all_data_pkl     = os.path.join(save_data_path, task+'_all_'+data_dict['rf_center']+\
                                    '_'+str(data_dict['local_range'])+'_interp.pkl' )
    all_data_dict = ut.load_pickle(all_data_pkl)
    timeList  = all_data_dict['timesList'][0][startIdx:]
    print np.shape(timeList)

    # ----------------------------------------------------------
    bd_data    = os.path.join(save_data_path, 'hmm_bd_data_'+task+'_'+str(foldIdx)+'.pkl')
    scaler_model = os.path.join(save_data_path, 'hmm_bd_scaler_'+task+'_'+str(foldIdx)+'.pkl')
    if os.path.isfile(bd_data) and db_renew is False:
        dd = ut.load_pickle(bd_data)
        X_train_flat        = dd['X_train_flat']
        Y_train_flat        = dd['Y_train_flat']
        idx_train_flat      = dd['idx_train_flat']
        X_train_flat_scaled = dd['X_train_flat_scaled']            
        X_test_flat        = dd['X_test_flat']
        Y_test_flat        = dd['Y_test_flat'] 
        X_test_flat_scaled = dd['X_test_flat_scaled']
        X_bg        = dd['X_bg']
        x1          = dd['x1']
        x2          = dd['x2']
        xx_normal   = dd['xx_normal']
        xx_abnormal = dd['xx_abnormal']
        
        if os.path.isfile(scaler_model):
            ml_scaler = joblib.load(scaler_model)
        else:
            ml_scaler = preprocessing.StandardScaler()
            X_train_flat_scaled = ml_scaler.fit_transform(X_train_flat)         
    else:    
        # flatten train data
        X_train_flat = [] #
        Y_train_flat = [] #
        idx_train_flat = []
        post_list = []
        for i in xrange(len(ll_classifier_train_X)):
            for j in xrange(len(ll_classifier_train_X[i])):
                X_train_flat.append(ll_classifier_train_X[i][j])
                Y_train_flat.append(ll_classifier_train_Y[i][j])
                idx_train_flat.append(ll_classifier_train_idx[i][j])
                post_list.append(ll_classifier_train_X[i][j][1:])

        # flatten test data
        X_test_flat, Y_test_flat, _ = flattenSample(ll_classifier_test_X, \
                                                    ll_classifier_test_Y, \
                                                    ll_classifier_test_idx)


        # ------------------ scaling -----------------------------------------------
        if os.path.isfile(scaler_model):
            ml_scaler = joblib.load(scaler_model)
            X_train_flat_scaled = ml_scaler.transform(X_train_flat)
        else:
            ml_scaler = preprocessing.StandardScaler()
            X_train_flat_scaled = ml_scaler.fit_transform(X_train_flat) 
            joblib.dump(ml_scaler, scaler_model)
        X_test_flat_scaled  = ml_scaler.transform(X_test_flat)
        X_train_flat_scaled = np.array(X_train_flat_scaled) #
        X_test_flat_scaled  = np.array(X_test_flat_scaled) #
        
        # --------------------------------------------------------------------------
        # Generate hidden-state distribution axis over center...
        n_logp = 100
        ## n_post = 100
        ## post_exp_list = np.zeros((n_post,nState))
        ## mean_list     = np.linspace(0,nState-1,n_post)
        ## std_list      = [0.3]*n_post #[0.5]*n_post

        ## from scipy.stats import norm
        ## for i in xrange(n_post):
        ##     rv = norm(loc=mean_list[i],scale=std_list[i])
        ##     post_exp_list[i] = rv.pdf(np.linspace(0,nState-1,nState))
        ##     post_exp_list[i] /=np.sum(post_exp_list[i])

        n_post = len(ll_classifier_train_X[0])
        post_exp_list = []
        for i in xrange(len(ll_classifier_train_X[0])):
            post = np.array(ll_classifier_train_X)[:,i,1:]
            post = np.mean(post, axis=0)
            post /= np.sum(post)
            post_exp_list.append(post)
        post_exp_list = np.array(post_exp_list)

        # Discriminative classifier ---------------------------------------------------
        # Adjusting range
        ## x1_min, x1_max = X_train_flat_pca[:, 0].min() , X_train_flat_pca[:, 0].max() 
        x2_min, x2_max = np.array(X_train_flat)[:,:1].min() , np.array(X_train_flat)[:,:1].max()

        # create a mesh to plot in
        x1, x2 = np.meshgrid(range(n_post),
                             np.linspace(x2_min, x2_max, n_logp) )

        # Background
        print "Run background data"
        data = np.c_[x1.ravel(), x2.ravel()]
        X_bg = np.hstack([ np.array([x2.ravel()]).T, post_exp_list[x1.ravel().tolist()] ])
        print np.shape(X_bg)

        # test points
        print "Run test data"
        ## Y_test_flat_est = dtc.predict(np.array(X_test_flat))
        xx_normal = []
        xx_abnormal = []
        for x,y in zip(X_test_flat, Y_test_flat):
            post = x[1:]
            ## min_index, min_dist = cf.findBestPosteriorDistribution(post, post_exp_list)
            if y > 0: xx_abnormal.append([min_index,x[0]])
            else:     xx_normal.append([min_index,x[0]])
        xx_normal   = np.array(xx_normal)
        xx_abnormal = np.array(xx_abnormal)

        dd = {}
        dd['X_train_flat']       = X_train_flat 
        dd['Y_train_flat']       = Y_train_flat
        dd['idx_train_flat']     = idx_train_flat
        dd['X_train_flat_scaled']= X_train_flat_scaled
        dd['X_test_flat']        = X_test_flat
        dd['Y_test_flat']        = Y_test_flat
        dd['X_test_flat_scaled'] = X_test_flat_scaled
        dd['X_bg']               = X_bg
        dd['x1']                 = x1
        dd['x2']                 = x2
        dd['xx_normal']          = xx_normal
        dd['xx_abnormal']        = xx_abnormal        
        ut.save_pickle(dd, bd_data)

    # -----------------------------------------------------------------------------
    print "Run classifier"
    methods = ['svm']
    methods = ['progress']

    from matplotlib import rc
    rc('font',**{'family':'sans-serif','sans-serif':['Helvetica']})
    rc('text', usetex=True)
    fig = plt.figure(1)
    for method in methods:
        
        lines  = []
        labels = []
        print "Current method ", method
        bd_method_data = os.path.join(save_data_path, 'hmm_bd_'+task+'_'+str(foldIdx)+'_'+method+'.pkl')
        if os.path.isfile(bd_method_data):
            d = ut.load_pickle(bd_method_data)
        else:
            d = {}
            d[method] = method
            d['data'] = []

            # scaling?
            if method.find('svm')>=0: X_scaled = X_train_flat_scaled
            else: X_scaled = X_train_flat            
            dtc = cf.classifier( method=method, nPosteriors=nState, nLength=nLength)

            # weight number
            startPoint = 0
            for j in xrange(nPoints):
                dtc.set_params( **SVM_dict )
                if method == 'svm':
                    weights = ROC_dict['svm_param_range']
                    dtc.set_params( class_weight=weights[j] )
                    dtc.set_params( kernel_type=0 ) # temp
                    ret = dtc.fit(X_scaled, Y_train_flat, idx_train_flat, parallel=False)                
                elif method == 'cssvm':
                    weights = ROC_dict['cssvm_param_range']
                    dtc.set_params( class_weight=weights[j] )
                    ret = dtc.fit(X_scaled, Y_train_flat, idx_train_flat, parallel=False)                
                elif method == 'progress' or method == 'fixed':
                    weights = ROC_dict[method+'_param_range']
                    dtc.set_params( ths_mult=weights[j] )
                    if j==startPoint:
                        ret = dtc.fit(X_scaled, Y_train_flat, idx_train_flat, parallel=False)                

                if method.find('svm')>=0:
                    print "SVM Weight: ", weights[j], np.shape(X_bg)
                    X_bg_scaled = ml_scaler.transform(X_bg)
                else:
                    print "Progress? Weight: ", weights[j]
                    X_bg_scaled = X_bg

                z = dtc.predict(np.array(X_bg_scaled))                
                print np.amin(z), np.amax(z), " : ", np.amin(Y_train_flat), np.amax(Y_train_flat)

                if np.amax(z) == np.amin(z):
                    print "Max equals to min. Wrong classification!"
                z = np.array(z)
                z = z.reshape(np.shape(x1)) 
                ## plt.contourf(x1, x2, z, cmap=plt.cm.Paired)
                #plt.contourf(x1, x2, z, levels=np.linspace(z.min(), 0, 7), cmap=plt.cm.Blues_r) # -1: blue, 1.0: red
                #plt.contourf(x1, x2, z, levels=[0, z.max()], colors='orange')
                d['data'].append( {'x1': x1, 'x2': x2, 'z':z, 'weight':weights[j] } )

            ut.save_pickle(d, bd_method_data)

        for data in d['data']:
            x1     = data['x1']
            x2     = data['x2']
            z      = data['z']
            weight = data['weight']
            
            color = colors.next()
            CS=plt.contour(x1, x2, z, levels=[0], linewidths=2, colors=color)
            ## plt.clabel(CS, inline=1, fontsize=10)
            lines.append(CS.collections[0])
            if method.find('svm')>=0:
                labels.append( r'$w_{+1}$ = '+'{0:.3f}'.format(weight) )
            else:
                labels.append( r'$c$ = '+'{0:.3f}'.format(weight) )

        plt.scatter(xx_abnormal[:,0],xx_abnormal[:,1],c='red', marker='x', \
                    label="Anomalous data")
        plt.scatter(xx_normal[:,0],xx_normal[:,1],c='blue', marker='o', lw=0,\
                    label="Non-anomalous data")
        plt.axis('tight')
        ## plt.axis('off')
        if np.amin(xx_normal[:,1])>0:
            plt.ylim([ np.amin(xx_normal[:,1])-150, np.amax(xx_normal[:,1])*1. ])
        else:
            plt.ylim([ np.amin(xx_normal[:,1])*1.3, np.amax(xx_normal[:,1])*1. ])
            
        plt.legend(lines, labels, loc=4, prop={'size':12})
        plt.ylabel("Log-likelihood", fontsize=22)
        plt.xlabel("Progress Vector Change [Index]", fontsize=22)
        ## plt.xlabel("Time [s]", fontsize=22)

        n_post = len(ll_classifier_train_X[0])
        time_array = np.linspace(0,n_post-1,3)
        plt.xticks(np.linspace(0,n_post-1,3).astype(int))
        ## time_array = np.linspace(timeList[0], timeList[-1],3)
        ## tick_list = []
        ## for i in xrange(3):
        ##     tick_list.append( "{0:.3f}".format(time_array[i]) )
        ## plt.xticks(np.linspace(0,n_post-1,3), tick_list )

        if save_pdf is False:
            plt.show()
        else:
            print "Save pdf to Dropbox folder "
            fig.savefig('test.pdf')
            fig.savefig('test.png')
            os.system('mv test.* ~/Dropbox/HRL/')

def plotEvalDelay(dim, rf_center, local_range, save_pdf=False):

    task_list = ['pushing_microblack', 'pushing_microwhite', 'pushing_toolcase','scooping', 'feeding']
    method_list = ['hmmgp', 'progress', 'fixed']
    ref_method = 'svm'

    delay_dict = {}
    acc_dict   = {}
    for task in task_list:
        delay_dict[task] = {}
        acc_dict[task]   = {}        
        for method in method_list:            
            delay_dict[task][method] = []
            acc_dict[task][method]   = []

    # load each task
    for task in task_list:

        _, save_data_path, param_dict = getParams(task, False, \
                                                  False, False, dim,\
                                                  rf_center, local_range)

        roc_pkl = os.path.join(save_data_path, 'roc_'+task+'.pkl')
        ROC_data = ut.load_pickle(roc_pkl)

        crossVal_pkl = os.path.join(save_data_path, 'cv_'+task+'.pkl')
        d = ut.load_pickle(crossVal_pkl)
        param_dict2  = d['param_dict']

        # Dict
        ROC_dict  = param_dict['ROC']
        data_dict = param_dict['data_param']

        startIdx    = 4        
        if 'timeList' in param_dict2.keys():
            timeList    = param_dict2['timeList'][startIdx:]
        else: timeList = None
        
        nPoints   = ROC_dict['nPoints']
        nFiles    = data_dict['nNormalFold']*data_dict['nAbnormalFold']
        max_acc_dict = {}

        for method in method_list:
            print task, method
            # find Max ACC's delay and idx
            tp_ll = ROC_data[method]['tp_l']
            fp_ll = ROC_data[method]['fp_l']
            tn_ll = ROC_data[method]['tn_l']
            fn_ll = ROC_data[method]['fn_l']
            delay_ll = ROC_data[method]['delay_l']
            tp_delay_ll = ROC_data[method]['tp_delay_l']
            tp_idx_ll   = ROC_data[method]['tp_idx_l']

            acc_l = []

            if timeList is not None:
                time_step = (timeList[-1]-timeList[0])/float(len(timeList)-1)
            else:
                time_step = 1.0

            for i in xrange(nPoints):
                acc_l.append( float(np.sum(tp_ll[i]+tn_ll[i])) / \
                              float(np.sum(tp_ll[i]+fn_ll[i]+fp_ll[i]+tn_ll[i])) * 100.0 )

            max_point_idx = np.argmax(acc_l)
            max_acc_dict[method] = [[],[]]
            max_acc_dict[method][0] = tp_idx_ll[max_point_idx]
            max_acc_dict[method][1] = tp_delay_ll[max_point_idx]
            acc_dict[task][method] = np.amax(acc_l)
            
        # compare idx and take time only
        for method in method_list:
            if method is not ref_method:

                delay_l = []
                for i in xrange(nFiles):
                    idx_l = list(set(max_acc_dict[ref_method][0][i]).intersection(max_acc_dict[method][0][i]))
                    ref_idx_l = [ idx for idx, x in enumerate(max_acc_dict[ref_method][0][i]) if x in idx_l ]
                    tgt_idx_l = [ idx for idx, x in enumerate(max_acc_dict[method][0][i]) if x in idx_l ]
                    
                    ref_delay_l = np.array(max_acc_dict[ref_method][1][i])[ref_idx_l] * time_step
                    tgt_delay_l = np.array(max_acc_dict[method][1][i])[tgt_idx_l] * time_step

                    delay_l += (tgt_delay_l-ref_delay_l).tolist()

                delay_dict[task][method] += delay_l
            else:
                delay_dict[task][method] = [0.0]


    colors = itertools.cycle(['r', 'g', 'b', 'k', 'y', ])
    shapes = itertools.cycle(['x','v', 'o', '+'])
    tasks   = ['Closing a microwave(B)','Closing a microwave(W)','Locking a toolcase','Scooping','Feeding'] 
    methods = ['HMM-GP', 'HMM-D', 'HMM-F', 'OSVM']

    if False:
        fig = plt.figure(1)
        for method in method_list:
            color = colors.next()
            for task in task_list:
                shape = shapes.next()
                plt.scatter(acc_dict[task][method], np.mean(delay_dict[task][method]), c=color, \
                            marker=shape, s=124)

                print task, method, " : ", acc_dict[task][method], np.mean(delay_dict[task][method]), \
                  np.std(delay_dict[task][method])


        import matplotlib.patches as mpatches
        colors  = ['r', 'g', 'b', 'k', 'y', ]
        recs = []
        for i, method in enumerate(methods):       
            recs.append(mpatches.Rectangle((0,0),1,1,fc=colors[i]))

        plt.legend(recs,methods,loc='lower left', prop={'size':22})

        ## plt.legend(lines, labels, loc=4, prop={'size':12})
        plt.xlabel("Accuracy [Percentage]", fontsize=22)
        plt.ylabel("Detection Time [sec]", fontsize=22)

    elif True:
        fig = plt.figure(1)
        acc_mean_l = []
        acc_std_l  = []
        delay_mean_l = []
        delay_std_l  = []
        delay_data = []

        width = .35
        ind = np.arange(len(methods)) #*0.9 #+width/2.0

        count = 0
        for method in method_list:
            acc_l   = []
            delay_l = []
            for task in task_list:
                acc_l.append(acc_dict[task][method])
                delay_l += delay_dict[task][method] 
                
            acc_mean_l.append( np.mean(acc_l) )
            acc_std_l.append( np.std(acc_l) )

            delay_mean_l.append( np.mean(delay_l) )
            delay_std_l.append( np.std(delay_l) )

            ## data = np.concatenate( (delay_l, [ind[count]+width*1.5]*len(delay_l) ),0 )
            data = delay_l
            delay_data.append( data )
            count += 1
            
        # MAX ACC        
        ax1 = plt.gca()
        rects1 = ax1.bar(ind, acc_mean_l, width, color='r', yerr=acc_std_l, \
                         error_kw=dict(elinewidth=6, ecolor='pink'))
        ax1.set_ylabel("Accuracy [Percentage]", fontsize=22)

        ax2 = ax1.twinx()
        ## rects2 = ax2.bar(ind+width*1.5, delay_mean_l, width, color='y', yerr=delay_std_l, \
        ##                  error_kw=dict(elinewidth=6, ecolor='yellow'))                         
        ## rects2 = ax2.boxplot(delay_data, positions=ind+width*1.5+0.05, widths=width)                         
        rects2 = ax2.errorbar(ind+width*1.5+0.05, delay_mean_l, delay_std_l, linestyle='None', marker='o',\
                              )
        ax2.set_ylabel("Detection Time [sec]", fontsize=22)
        ## plt.legend( (rects1[0], rects1[0]), ('Max Accuracy', 'Detection Delay') )
        plt.legend( (rects1[0], rects2[0]), ('Max Accuracy', 'Detection Delay'), loc='lower left', \
                    fontsize=18 )
        plt.xlim([-0.2, (ind+width*2.0+0.2)[-1]])
        plt.xticks(ind+width, methods, fontsize=40 )
        for tick in ax1.xaxis.get_major_ticks():
            tick.label.set_fontsize(18) 

        ## plt.legend(recs,methods,loc='lower left', prop={'size':22})


    if save_pdf is False:
        plt.show()
    else:
        print "Save pdf to Dropbox folder "
        fig.savefig('test.pdf')
        fig.savefig('test.png')
        os.system('mv test.* ~/Dropbox/HRL/')



if __name__ == '__main__':

    import optparse
    p = optparse.OptionParser()
    p.add_option('--dataRenew', '--dr', action='store_true', dest='bDataRenew',
                 default=False, help='Renew pickle files.')
    p.add_option('--AERenew', '--ar', action='store_true', dest='bAERenew',
                 default=False, help='Renew AE data.')
    p.add_option('--hmmRenew', '--hr', action='store_true', dest='bHMMRenew',
                 default=False, help='Renew HMM parameters.')
    p.add_option('--cfRenew', '--cr', action='store_true', dest='bClassifierRenew',
                 default=False, help='Renew Classifiers.')

    p.add_option('--task', action='store', dest='task', type='string', default='pushing_microwhite',
                 help='type the desired task name')
    p.add_option('--dim', action='store', dest='dim', type=int, default=3,
                 help='type the desired dimension')
    p.add_option('--aeswtch', '--aesw', action='store_true', dest='bAESwitch',
                 default=False, help='Enable AE data.')

    p.add_option('--rawplot', '--rp', action='store_true', dest='bRawDataPlot',
                 default=False, help='Plot raw data.')
    p.add_option('--interplot', '--ip', action='store_true', dest='bInterpDataPlot',
                 default=False, help='Plot raw data.')
    p.add_option('--feature', '--ft', action='store_true', dest='bFeaturePlot',
                 default=False, help='Plot features.')
    p.add_option('--likelihoodplot', '--lp', action='store_true', dest='bLikelihoodPlot',
                 default=False, help='Plot the change of likelihood.')
    p.add_option('--dataselect', '--ds', action='store_true', dest='bDataSelection',
                 default=False, help='Plot data and select it.')
    p.add_option('--data_generation', action='store_true', dest='bDataGen',
                 default=False, help='Data generation before evaluation.')
    p.add_option('--decision_boundary', '--db', action='store_true', dest='bDecisionBoundary',
                 default=False, help='Plot decision boundaries.')
    
    p.add_option('--aeDataExtraction', '--ae', action='store_true', dest='bAEDataExtraction',
                 default=False, help='Extract auto-encoder data.')
    p.add_option('--aeDataExtractionPlot', '--aep', action='store_true', dest='bAEDataExtractionPlot',
                 default=False, help='Extract auto-encoder data and plot it.')
    p.add_option('--aeDataAddFeature', '--aea', action='store_true', dest='bAEDataAddFeature',
                 default=False, help='Add hand-crafted data.')

    p.add_option('--evaluation_all', '--ea', action='store_true', dest='bEvaluationAll',
                 default=False, help='Evaluate a classifier with cross-validation.')
    p.add_option('--evaluation_delay', '--eadl', action='store_true', dest='bEvaluationDelay',
                 default=False, help='Evaluate the delay.')
    p.add_option('--evaluation_drop', '--ead', action='store_true', dest='bEvaluationWithDrop',
                 default=False, help='Evaluate a classifier with cross-validation plus drop.')
    p.add_option('--evaluation_noise', '--ean', action='store_true', dest='bEvaluationWithNoise',
                 default=False, help='Evaluate a classifier with cross-validation plus noise.')
    p.add_option('--plot_progress_hmmosvm', '--pph', action='store_true', dest='bPlotProgressVSHMMOSVM',
                 default=False, help='plot.')
    p.add_option('--evaluation_freq', '--eaf', action='store_true', dest='bEvaluationWithDiffFreq',
                 default=False, help='Evaluate a classifier with cross-validation and different sampling\
                 frequency.')
    p.add_option('--findParams', '--frp', action='store_true', dest='bFindROCparamRange',
                 default=False, help='Evaluate a classifier with cross-validation and different sampling\
                 frequency.')
                 
    
    p.add_option('--debug', '--dg', action='store_true', dest='bDebug',
                 default=False, help='Set debug mode.')
    p.add_option('--renew', action='store_true', dest='bRenew',
                 default=False, help='Renew pickle files.')
    p.add_option('--savepdf', '--sp', action='store_true', dest='bSavePdf',
                 default=False, help='Save pdf files.')    
    p.add_option('--noplot', '--np', action='store_true', dest='bNoPlot',
                 default=False, help='No Plot.')    
    p.add_option('--noupdate', '--nu', action='store_true', dest='bNoUpdate',
                 default=False, help='No update.')    
    p.add_option('--verbose', '--v', action='store_true', dest='bVerbose',
                 default=False, help='Print out.')

    
    opt, args = p.parse_args()

    #---------------------------------------------------------------------------           
    # Run evaluation
    #---------------------------------------------------------------------------           
    rf_center     = 'kinEEPos'        
    scale         = 1.0
    # Dectection TEST 
    local_range    = 10.0    

    #---------------------------------------------------------------------------
    if opt.task == 'scooping':
        subjects = ['Wonyoung', 'Tom', 'lin', 'Ashwin', 'Song', 'Henry2'] #'Henry', 
    #---------------------------------------------------------------------------
    elif opt.task == 'feeding':
        subjects = [ 'Ashwin', 'Song', 'tom' , 'lin', 'wonyoung']
    #---------------------------------------------------------------------------           
    elif opt.task == 'pushing_microwhite':
        subjects = ['gatsbii']
    #---------------------------------------------------------------------------           
    elif opt.task == 'pushing_microblack':
        subjects = ['gatsbii']
    #---------------------------------------------------------------------------           
    elif opt.task == 'pushing_toolcase':
        subjects = ['gatsbii']
    else:
        print "Selected task name is not available."
        sys.exit()

    raw_data_path, save_data_path, param_dict = getParams(opt.task, opt.bDataRenew, \
                                                          opt.bAERenew, opt.bHMMRenew, opt.dim,\
                                                          rf_center, local_range, \
                                                          bAESwitch=opt.bAESwitch)
    if opt.bClassifierRenew: param_dict['SVM']['renew'] = True
        
    
    #---------------------------------------------------------------------------           
    #---------------------------------------------------------------------------           
    #---------------------------------------------------------------------------           
    #---------------------------------------------------------------------------           
    

    if opt.bRawDataPlot or opt.bInterpDataPlot:
        '''
        Before localization: Raw data plot
        After localization: Raw or interpolated data plot
        '''
        successData = True
        failureData = False
        modality_list   = ['kinematics', 'audio', 'ft', 'vision_artag'] # raw plot
        
        data_plot(subjects, opt.task, raw_data_path, save_data_path,\
                  downSampleSize=param_dict['data_param']['downSampleSize'], \
                  local_range=local_range, rf_center=rf_center, \
                  raw_viz=opt.bRawDataPlot, interp_viz=opt.bInterpDataPlot, save_pdf=opt.bSavePdf,\
                  successData=successData, failureData=failureData,\
                  modality_list=modality_list, data_renew=opt.bDataRenew, verbose=opt.bVerbose)

    elif opt.bDataSelection:
        '''
        Manually select and filter bad data out
        '''
        ## modality_list   = ['kinematics', 'audioWrist','audio', 'fabric', 'ft', \
        ##                    'vision_artag', 'vision_change', 'pps']
        modality_list   = ['kinematics', 'ft']
        success_viz = True
        failure_viz = False

        data_selection(subjects, opt.task, raw_data_path, save_data_path,\
                       downSampleSize=param_dict['data_param']['downSampleSize'], \
                       local_range=local_range, rf_center=rf_center, \
                       success_viz=success_viz, failure_viz=failure_viz,\
                       raw_viz=opt.bRawDataPlot, save_pdf=opt.bSavePdf,\
                       modality_list=modality_list, data_renew=opt.bDataRenew, verbose=opt.bVerbose)        

    elif opt.bFeaturePlot:
        success_viz = True
        failure_viz = False
        
        dm.getDataSet(subjects, opt.task, raw_data_path, save_data_path,
                      param_dict['data_param']['rf_center'], param_dict['data_param']['local_range'],\
                      downSampleSize=param_dict['data_param']['downSampleSize'], scale=scale, \
                      success_viz=success_viz, failure_viz=failure_viz,\
                      ae_data=False,\
                      cut_data=param_dict['data_param']['cut_data'],\
                      save_pdf=opt.bSavePdf, solid_color=False,\
                      handFeatures=param_dict['data_param']['handFeatures'], data_renew=opt.bDataRenew)

    elif opt.bDecisionBoundary:
        success_viz = True
        failure_viz = False
        methods     = ['svm', 'progress']

        plotDecisionBoundaries(subjects, opt.task, raw_data_path, save_data_path, param_dict,\
                               methods,\
                               success_viz, failure_viz, save_pdf=opt.bSavePdf, db_renew=opt.bClassifierRenew)

    elif opt.bAEDataExtraction:
        param_dict['AE']['switch']     = True
        aeDataExtraction(subjects, opt.task, raw_data_path, save_data_path, param_dict, verbose=opt.bVerbose)

    elif opt.bAEDataExtractionPlot:
        success_viz = True
        failure_viz = True
        handFeature_viz = False
        param_dict['AE']['switch']     = True        
        aeDataExtraction(subjects, opt.task, raw_data_path, save_data_path, param_dict,\
                         handFeature_viz=handFeature_viz,\
                         success_viz=success_viz, failure_viz=failure_viz,\
                         verbose=opt.bVerbose)


    elif opt.bLikelihoodPlot:
        import hrl_anomaly_detection.data_viz as dv        
        dv.vizLikelihoods(subjects, opt.task, raw_data_path, save_data_path, param_dict,\
                          decision_boundary_viz=True, method='hmmgp', \
                          useTrain=True, useNormalTest=False, useAbnormalTest=False,\
                          useTrain_color=False, useNormalTest_color=False, useAbnormalTest_color=False,\
                          hmm_renew=opt.bHMMRenew, data_renew=opt.bDataRenew, save_pdf=opt.bSavePdf,\
                          verbose=opt.bVerbose)
                              
    elif opt.bEvaluationAll or opt.bPlotProgressVSHMMOSVM or opt.bDataGen:
        ## if opt.bHMMRenew: param_dict['ROC']['methods'] = ['fixed', 'progress'] #, 'change']
        if opt.bNoUpdate: param_dict['ROC']['update_list'] = []
        if opt.bPlotProgressVSHMMOSVM:
            param_dict['ROC']['methods'] = ['hmmosvm', 'progress'] 
            param_dict['ROC']['update_list'] = []
            param_dict['HMM']['renew'] = False
            param_dict['SVM']['renew'] = False
        if opt.bEvaluationDelay:
            param_dict['ROC']['methods']     = [ 'progress', 'fixed', 'osvm'] 
            param_dict['ROC']['update_list'] = [ 'progress', 'fixed', 'osvm']
        if opt.bFindROCparamRange:
            param_dict['ROC']['methods']     = [ 'progress', 'progress_diag', 'progress_svm'] 
            
                    
        evaluation_all(subjects, opt.task, raw_data_path, save_data_path, param_dict, save_pdf=opt.bSavePdf, \
                       verbose=opt.bVerbose, debug=opt.bDebug, no_plot=opt.bNoPlot, \
                       find_param=opt.bFindROCparamRange, data_gen=opt.bDataGen)

    elif opt.bEvaluationWithNoise:
        param_dict['ROC']['methods']     = ['fixed', 'change'] #'progress', 'hmmgp', 
        param_dict['ROC']['update_list'] = []
        
        ## evaluation_noise(subjects, opt.task, raw_data_path, save_data_path, param_dict, \
        ##                  save_pdf=opt.bSavePdf, \
        ##                  verbose=opt.bVerbose, debug=opt.bDebug, no_plot=opt.bNoPlot)
        evaluation_step_noise(subjects, opt.task, raw_data_path, save_data_path, param_dict,\
                              save_pdf=opt.bSavePdf, verbose=opt.bVerbose, debug=opt.bDebug, \
                              no_plot=opt.bNoPlot, delay_plot=True)


    elif opt.bEvaluationWithDrop:

        param_dict['ROC']['methods']     = ['svm', 'hmmsvm_LSLS', 'hmmsvm_dL', 'hmmsvm_no_dL']
        param_dict['ROC']['update_list'] = ['svm', 'hmmsvm_LSLS', 'hmmsvm_dL', 'hmmsvm_no_dL']
        if opt.bNoUpdate: param_dict['ROC']['update_list'] = []

        save_data_path = os.path.expanduser('~')+\
          '/hrl_file_server/dpark_data/anomaly/RSS2016/'+opt.task+'_data/'+\
          str(param_dict['data_param']['downSampleSize'])+'_'+str(opt.dim)+'_drop'

        import hrl_anomaly_detection.params_eval_drop as ped
        param_dict = ped.getParams(opt.task, param_dict)

        evaluation_drop(subjects, opt.task, raw_data_path, save_data_path, param_dict, \
                        save_pdf=opt.bSavePdf, \
                        verbose=opt.bVerbose, debug=opt.bDebug, no_plot=opt.bNoPlot, \
                        find_param=opt.bFindROCparamRange)

    elif opt.bFindROCparamRange:
        param_dict['ROC']['methods']     = ['svm']
        param_dict['ROC']['update_list'] = ['svm']
        if opt.bNoUpdate: param_dict['ROC']['update_list'] = []

        for method in param_dict['ROC']['methods']:
            find_ROC_param_range(method, opt.task, save_data_path, param_dict, debug=opt.bDebug)

    elif opt.bEvaluationDelay:
        plotEvalDelay(opt.dim, rf_center, local_range, save_pdf=opt.bSavePdf)
            

    elif opt.bEvaluationWithDiffFreq:
        '''
        Change into different sampling frequency or sample drop
        '''
        param_dict['ROC']['methods'] = ['svm', 'hmmsvm_LSLS', 'hmmsvm_dL', 'hmmsvm_no_dL']
        param_dict['ROC']['update_list'] = []
        if opt.bNoUpdate: param_dict['ROC']['update_list'] = []
        param_dict['HMM']['renew'] = False
        param_dict['SVM']['renew'] = False
        nPoints = param_dict['ROC']['nPoints']
        refSampleSize = param_dict['data_param']['downSampleSize']
        
        
        for sampleSize in [50, 400]:
            print "============================="
            print "Sample Size: ", sampleSize
            print "============================="
            param_dict['data_param']['downSampleSize'] = sampleSize
            save_data_path = os.path.expanduser('~')+\
              '/hrl_file_server/dpark_data/anomaly/RSS2016/'+opt.task+'_data/'+\
              str(param_dict['data_param']['downSampleSize'])+'_'+str(opt.dim)

            if sampleSize == 50:
                param_dict['ROC']['update_list'] = ['hmmsvm_no_dL', 'hmmsvm_dL', 'hmmsvm_LSLS', 'svm']
                if opt.bNoUpdate: param_dict['ROC']['update_list'] = ['bpsvm']
                if opt.task == "pushing_microwhite":
                    param_dict['ROC']['hmmsvm_dL_param_range'] *= 1.0
                    param_dict['ROC']['hmmsvm_LSLS_param_range'] *= 1.0
                    param_dict['ROC']['svm_param_range'] = np.logspace(-2.0, -0.1, nPoints)
                if opt.task == "pushing_toolcase":
                    param_dict['ROC']['hmmsvm_dL_param_range'] *= 1.0
                    param_dict['ROC']['hmmsvm_LSLS_param_range'] = np.logspace(-1.5, 0.0, nPoints)
                    param_dict['ROC']['svm_param_range'] = np.logspace(-2.5, 0.0, nPoints)
                if opt.task == "scooping":
                    param_dict['ROC']['hmmsvm_dL_param_range'] = np.logspace(-2.5, 0.0, nPoints) 
                    param_dict['ROC']['hmmsvm_LSLS_param_range'] = np.logspace(-4, 0.0, nPoints)
                    param_dict['ROC']['svm_param_range'] = np.logspace(-4, -1.5, nPoints) 
                    param_dict['ROC']['hmmsvm_no_dL_param_range'] = np.logspace(-4.5, -3.0, nPoints)
                    param_dict['ROC']['bpsvm_param_range'] = np.logspace(-1.6, 2.0, nPoints)
                if opt.task == "feeding":
                    param_dict['ROC']['hmmsvm_dL_param_range'] *= 1.0
                    param_dict['ROC']['hmmsvm_LSLS_param_range'] = np.logspace(-3, 0.8, nPoints)
                    param_dict['ROC']['svm_param_range'] = np.logspace(0.9, -3.0, nPoints)
                    
            elif sampleSize == 100:
                param_dict['ROC']['update_list'] = ['hmmsvm_dL', 'hmmsvm_LSLS', 'svm']
                if opt.bNoUpdate: param_dict['ROC']['update_list'] = []
                if opt.task == "pushing_microwhite":
                    param_dict['ROC']['hmmsvm_dL_param_range'] *= 1.0
                    param_dict['ROC']['hmmsvm_LSLS_param_range'] *= 1.0
                    param_dict['ROC']['svm_param_range'] = np.logspace(-2.0, -0.1, nPoints)
                if opt.task == "pushing_toolcase":
                    param_dict['ROC']['hmmsvm_dL_param_range'] *= 1.0
                    param_dict['ROC']['hmmsvm_LSLS_param_range'] = np.logspace(-1.5, 0.0, nPoints)
                    param_dict['ROC']['svm_param_range'] = np.logspace(-2.5, 0.0, nPoints)
                if opt.task == "scooping":
                    param_dict['ROC']['hmmsvm_dL_param_range'] = np.logspace(-2.5, 1.0, nPoints) 
                    param_dict['ROC']['hmmsvm_LSLS_param_range'] *= 0.1
                    param_dict['ROC']['svm_param_range'] = np.logspace(-3, 0.0, nPoints) 
                if opt.task == "feeding":
                    param_dict['ROC']['hmmsvm_dL_param_range'] *= 1.0
                    param_dict['ROC']['hmmsvm_LSLS_param_range'] = np.logspace(-3, 0.8, nPoints)
                    param_dict['ROC']['svm_param_range'] = np.logspace(0.9, -3.0, nPoints)
                    
            elif sampleSize > 200:
                param_dict['ROC']['update_list'] = ['hmmsvm_no_dL', 'hmmsvm_dL', 'hmmsvm_LSLS' , 'svm']
                if opt.bNoUpdate: param_dict['ROC']['update_list'] = ['bpsvm']
                if opt.task == "pushing_microblack":
                    param_dict['ROC']['hmmsvm_dL_param_range'] = np.logspace(-4, 0.0, nPoints)
                    param_dict['ROC']['hmmsvm_LSLS_param_range'] *= 3.0
                    param_dict['ROC']['svm_param_range'] = np.logspace(-3.0, 0.0, nPoints)
                if opt.task == "pushing_microwhite":
                    param_dict['ROC']['hmmsvm_dL_param_range'] = np.logspace(-3.0, 1.2, nPoints)
                    param_dict['ROC']['hmmsvm_LSLS_param_range'] *= 15.0
                    param_dict['ROC']['svm_param_range'] *= 10.0
                if opt.task == "pushing_toolcase":
                    param_dict['ROC']['hmmsvm_dL_param_range'] *= 1.0
                    param_dict['ROC']['hmmsvm_LSLS_param_range'] = np.logspace(-4.0, 0.0, nPoints) 
                    param_dict['ROC']['svm_param_range'] = np.logspace(-3.2, 0.2, nPoints)
                if opt.task == "scooping":
                    param_dict['ROC']['hmmsvm_dL_param_range']    = np.logspace(-4.0, 3.2, nPoints) 
                    param_dict['ROC']['hmmsvm_LSLS_param_range'] *= 1.0
                    param_dict['ROC']['svm_param_range'] = np.logspace(-2.0, 1.8, nPoints) 
                    param_dict['ROC']['hmmsvm_no_dL_param_range'] = np.logspace(-1.0, 0.7, nPoints)
                    param_dict['ROC']['bpsvm_param_range'] = np.logspace(-2.2, 0.5, nPoints)
                if opt.task == "feeding":
                    param_dict['ROC']['hmmsvm_dL_param_range'] *= 15.0
                    param_dict['ROC']['hmmsvm_LSLS_param_range'] = np.logspace(-3, 1.5, nPoints)
                    param_dict['ROC']['svm_param_range'] = np.logspace(1.5, -2.5, nPoints)


            evaluation_freq(subjects, opt.task, raw_data_path, save_data_path, param_dict, \
                            refSampleSize,\
                            save_pdf=opt.bSavePdf, \
                            verbose=opt.bVerbose, debug=opt.bDebug, no_plot=opt.bNoPlot)

                            
