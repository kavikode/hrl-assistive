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

import time
import random
import numpy as np
from scipy.stats import randint as sp_randint
from sklearn.grid_search import RandomizedSearchCV, GridSearchCV
from sklearn.base import BaseEstimator, ClassifierMixin
from learning_hmm_multi_n import learning_hmm_multi_n
from util import getSubjectFiles
from .. import util as dataUtil
import learning_util as util
from .. import data_manager as dataMng

# catkin_make_isolated --only-pkg-with-deps hrl_anomaly_detection --merge
# nohup rosrun hrl_anomaly_detection hmmOptimization.py > optimization.log &
# sed '/GHMM ghmm.py/d' optimization.log > optimizationClean.log

'''
This HMM optimizer is meant to be used in conjunction with the scooping data most recently recorded by Daehyung.
'''

paramSet = ''
scores = []

class HmmClassifier(BaseEstimator, ClassifierMixin):

    def __init__(self, downSampleSize=200, scale=1.0, nState=20, cov_mult=1.0, isScooping=True):
        self.downSampleSize = downSampleSize
        self.scale = scale
        self.nState = nState
        self.cov_mult = cov_mult
        # print 'Testing', downSampleSize, scale, nState, cov_mult

        self.train_cutting_ratio = [0.0, 0.65]
        self.anomaly_offset = 0.0
        self.isScooping = isScooping
        self.verbose = False

        self.isFitted = False
        self.hmm = None
        self.trainData = None

    def set_params(self, **parameters):
        global paramSet, scores
        params = ''
        for parameter, value in parameters.items():
            setattr(self, parameter, value)
            params += '%s: %s, ' % (parameter, str(value))
        if params != paramSet:
            paramSet = params
            if scores:
                print 'Average score: %f\n' % (sum(scores) / float(len(scores)))
                scores = []
        print params
        return self

    def fit(self, X=None, y=None):
        """
        This should fit classifier. All the "work" should be done here.

        Note: assert is not a good choice here and you should rather
        use try/except blog with exceptions. This is just for short syntax.
        """

        t = time.time()
        trainingData = self.loadData()
        print 'time 1:', time.time() - t
        t = time.time()

        # Possible pass in trainData through X (thus utilizing the cross-validation in sklearn)
        #print 'Number of modalities (dimensions):', len(trainData)
        #print 'Lengths of data:', [len(trainData[i]) for i in xrange(len(trainData))]
        #print 'Lengths of internal data:', [len(trainData[i][0]) for i in xrange(len(trainData))]

        self.hmm = learning_hmm_multi_n(nState=self.nState, nEmissionDim=len(trainingData), scale=self.scale, check_method='progress', cluster_type='time', anomaly_offset=self.anomaly_offset, verbose=self.verbose)
        print 'time 2:', time.time() - t
        t = time.time()
        ret = self.hmm.fit(xData=self.trainData, cov_mult=[self.cov_mult]*16)
        print 'time 3:', time.time() - t

        if ret == 'Failure':
            print 'HMM return was a failure!'
            return self

        self.isFitted = True

        return self

    def score(self, X, y, sample_weight=None):
        global scores
        if not self.isFitted:
            return 0

        log_ll = []
        t = time.time()
        # exp_log_ll = []        
        for i in xrange(len(self.trainData[0])):
            log_ll.append([])
            # exp_log_ll.append([])
            # Compute likelihood values for data
            for j in range(2, len(self.trainData[0][i])):
                X = [x[i,:j] for x in np.array(self.trainData)]
                # t1 = time.time()
                exp_logp, logp = self.hmm.expLoglikelihood(X, self.hmm.l_ths_mult, bLoglikelihood=True)
                # print 'time exp:', time.time() - t1
                log_ll[i].append(logp)
                # exp_log_ll[i].append(exp_logp)

        print 'time 4:', time.time() - t
        # Return average log-likelihood
        logs = [x[-1] for x in log_ll]
        score = sum(logs) / float(len(logs))
        scores.append(score)
        print 'expLoglikelihood() log_ll:', np.shape(log_ll), score
        return score

        # print 'expLoglikelihood() exp_log_ll:', np.shape(exp_log_ll), [x[-1] for x in exp_log_ll]

        # print 'loglikelihood()', self.hmm.loglikelihood(self.trainData)
        # print '-'*50
        # likelihood, posterior = self.hmm.loglikelihoods(self.trainData, bPosterior=True)
        # print 'loglikelihoods(), likelihood:', likelihood
        # print 'loglikelihoods(), posterior:', posterior
        # print '-'*50
        # exp_logp, logp = self.hmm.expLoglikelihood(self.trainData, self.hmm.l_ths_mult, bLoglikelihood=True)
        # print 'expLoglikelihood() exp_logp:', exp_logp
        # print 'expLoglikelihood() logp:', logp

        # return 0

    # Load training data similar to the approach taken in data_manager.py
    def loadData(self):
        # Loading success and failure data
        root_path = '/home/mycroft/gatsbii_scooping'
        success_list, _ = getSubjectFiles(root_path)

        feature_list = ['unimodal_audioPower',
                        'unimodal_audioWristRMS',
                        'unimodal_kinVel',
                        'unimodal_ftForce',
                        'unimodal_ppsForce',
                        'unimodal_visionChange',
                        'unimodal_fabricForce',
                        'crossmodal_targetEEDist',
                        'crossmodal_targetEEAng',
                        'crossmodal_artagEEDist',
                        'crossmodal_artagEEAng']

        rawDataDict, dataDict = dataUtil.loadData(success_list, isTrainingData=True, downSampleSize=self.downSampleSize, local_range=0.15, verbose=self.verbose)
        trainingData, _ = dataMng.extractLocalFeature(dataDict, feature_list)
        trainingData = np.array(trainingData)

        if True:
            # exclude stationary data
            thres = 0.025
            n,m,k = np.shape(trainingData)
            diff_all_data = trainingData[:,:,1:] - trainingData[:,:,:-1]
            add_idx = []
            for i in xrange(n):
                std = np.max(np.max(diff_all_data[i], axis=1))
                if std >= thres:
                    add_idx.append(i)
            trainingData  = trainingData[add_idx]

        return trainingData


# Loading success and failure data
root_path = '/home/mycroft/gatsbii_scooping'
success_list, _ = getSubjectFiles(root_path)

print "--------------------------------------------"
print "# of Success files: ", len(success_list)
print "--------------------------------------------"

featureIndices = xrange(len(success_list))
random.shuffle(featureIndices)

print '\n', '-'*50, '\nBeginning Grid Search\n', '-'*50, '\n'

# Specify parameters and possible parameter values
# Try cov_mult between 8.0 and 12.0
#tuned_params = {'downSampleSize': [400, 500, 600, 700], 'scale': [1], 'nState': [20, 30], 'cov_mult': [10.0]}
tuned_params = {'downSampleSize': [100], 'scale': [1], 'nState': [20, 30], 'cov_mult': [10.0]}

# Run grid search
gs = GridSearchCV(HmmClassifier(), tuned_params)
gs.fit(X=featureIndices, y=[1]*len(featureIndices))

print 'Grid Search:'
print 'Best params:', gs.best_params_
print 'Best Score:', gs.best_score_
# print 'Grid scores:', gs.grid_scores_

#print '\n', '-'*50, '\nBeginning Randomized Search\n', '-'*50, '\n'

# specify parameters and distributions to sample from
#param_dist = {'downSampleSize': sp_randint(300, 400),
#              'scale': sp_randint(1, 3),
#              'nState': sp_randint(20, 30),
#              'cov_mult': sp_randint(10, 15)}

# Run randomized search
#random_search = RandomizedSearchCV(HmmClassifier(), param_distributions=param_dist, n_iter=50)
#random_search.fit(X=featureIndices, y=[1]*len(featureIndices))

#print 'Randomized Search:'
#print 'Best params:', random_search.best_params_
#print 'Best Score:', random_search.best_score_
# print 'Grid scores:', random_search.grid_scores_
