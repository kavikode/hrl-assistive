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
import numpy
import numpy as np
import scipy
np.random.seed(1337)

# Keras
import h5py 
from keras.models import Sequential, Model
from keras.layers import Input, TimeDistributed, Layer
from keras.layers import Activation, Dropout, Flatten, Dense, merge, Lambda, RepeatVector, LSTM, GaussianNoise
from keras.layers.advanced_activations import PReLU, LeakyReLU
from keras.utils.np_utils import to_categorical
from keras.optimizers import SGD, Adagrad, Adadelta, RMSprop, Adam
from keras import backend as K
from keras import objectives

from hrl_anomaly_detection.RAL18_detection import keras_util as ku
from hrl_anomaly_detection.RAL18_detection import util as vutil

import gc



def lstm_vae(trainData, testData, weights_file=None, batch_size=32, nb_epoch=500, \
             patience=20, fine_tuning=False, save_weights_file=None, \
             noise_mag=0.0, timesteps=4, sam_epoch=1, \
             x_std_div=1, x_std_offset=0.001, z_std=0.5,\
             phase=1.0,\
             re_load=False, renew=False, plot=False, trainable=None, **kwargs):
    """
    Variational Autoencoder with two LSTMs and one fully-connected layer
    x_train is (sample x length x dim)
    x_test is (sample x length x dim)
    """

    x_train = trainData[0]
    y_train = trainData[1]
    x_test = testData[0]
    y_test = testData[1]

    input_dim = len(x_train[0][0])
    length = len(x_train[0])

    h1_dim = kwargs.get('h1_dim', input_dim)
    z_dim  = kwargs.get('z_dim', 2) 
           
    inputs = Input(batch_shape=(batch_size, timesteps, input_dim+1))
    def slicing(x): return x[:,:,:input_dim]
    encoded = Lambda(slicing)(inputs)     
    encoded = GaussianNoise(noise_mag)(encoded)
    encoded = LSTM(h1_dim, return_sequences=False, activation='tanh', stateful=True)(encoded)
    z_mean  = Dense(z_dim)(encoded) 
    z_log_var = Dense(z_dim)(encoded) 
    
    def sampling(args):
        z_mean, z_log_var = args
        epsilon = K.random_normal(shape=K.shape(z_mean), mean=0., stddev=1.0) 
        return z_mean + K.exp(z_log_var/2.0) * epsilon    
        
    # we initiate these layers to reuse later.
    decoded_h1 = Dense(h1_dim) 
    decoded_h2 = RepeatVector(timesteps)
    decoded_L1 = LSTM(input_dim, return_sequences=True, activation='tanh', stateful=True)
    decoded_mu    = TimeDistributed(Dense(input_dim, activation='linear'))
    decoded_sigma = TimeDistributed(Dense(input_dim, activation='softplus')) 

    # Custom loss layer
    class CustomVariationalLayer(Layer):
        def __init__(self, **kwargs):
            self.is_placeholder = True
            super(CustomVariationalLayer, self).__init__(**kwargs)

        def vae_loss(self, x, x_d_mean, x_d_std, p):
            '''
            p : phase variable
            '''
            log_p_x_z = -0.5 * ( K.sum(K.square((x-x_d_mean)/x_d_std), axis=-1) \
                                 + float(input_dim) * K.log(2.0*np.pi) + K.sum(K.log(K.square(x_d_std)),
                                                                               axis=-1) )
            xent_loss = K.mean(-log_p_x_z, axis=-1)


            kl_loss = - 0.5 * K.sum( - K.exp(z_log_var)/(z_std*z_std)
                                     - K.square((z_mean-p)/(z_std*z_std))
                                     + 1.
                                     - K.log(z_std*z_std) + z_log_var, axis=-1)  
            return K.mean(xent_loss + kl_loss) 

        def call(self, args):
            x = args[0][:,:,:input_dim]
            p = args[0][:,0,input_dim:input_dim+1]
            x_d_mean = args[1][:,:,:input_dim]
            x_d_std  = args[1][:,:,input_dim:]/x_std_div + x_std_offset

            p = K.concatenate([K.zeros(shape=(batch_size, z_dim-1)),p], axis=-1)
            
            loss = self.vae_loss(x, x_d_mean, x_d_std, p)
            self.add_loss(loss, inputs=args)
            # We won't actually use the output.
            return x_d_mean


    z = Lambda(sampling)([z_mean, z_log_var])    
    decoded = decoded_h1(z)
    decoded = decoded_h2(decoded)
    decoded = decoded_L1(decoded)
    decoded1 = decoded_mu(decoded)
    decoded2 = decoded_sigma(decoded)
    decoded = merge([decoded1, decoded2], mode='concat')  
    outputs = CustomVariationalLayer()([inputs, decoded])

    vae_autoencoder = Model(inputs, outputs)
    print(vae_autoencoder.summary())

    # Encoder --------------------------------------------------
    vae_encoder_mean = Model(inputs, z_mean)
    vae_encoder_var  = Model(inputs, z_log_var)

    # Decoder (generator) --------------------------------------
    generator = None

    # VAE --------------------------------------
    vae_mean_std = Model(inputs, decoded)

    if weights_file is not None and os.path.isfile(weights_file) and fine_tuning is False and\
        re_load is False and renew is False:
        vae_autoencoder.load_weights(weights_file)
    else:
        if fine_tuning:
            vae_autoencoder.load_weights(weights_file)
            lr = 0.001
            optimizer = Adam(lr=lr, clipvalue=10.) #4.)# 5)
            vae_autoencoder.compile(optimizer=optimizer, loss=None)
            vae_autoencoder.compile(optimizer='adam', loss=None)
        else:
            if re_load and os.path.isfile(weights_file):
                vae_autoencoder.load_weights(weights_file)
            lr = 0.01
            #optimizer = RMSprop(lr=lr, rho=0.9, epsilon=1e-08, decay=0.0001, clipvalue=10)
            optimizer = Adam(lr=lr, clipvalue=10) #, decay=1e-5)                
            #vae_autoencoder.compile(optimizer=optimizer, loss=None)
            vae_autoencoder.compile(optimizer='adam', loss=None)
            #vae_autoencoder.compile(optimizer='rmsprop', loss=None)

        # ---------------------------------------------------------------------------------
        nDim         = len(x_train[0][0])
        wait         = 0
        plateau_wait = 0
        min_loss = 1e+15
        np.random.seed(3334)
        for epoch in xrange(nb_epoch):
            print 

            mean_tr_loss = []
            for sample in xrange(sam_epoch):

                # shuffle
                idx_list = range(len(x_train))
                np.random.shuffle(idx_list)
                x_train = x_train[idx_list]
                
                for i in xrange(0,len(x_train),batch_size):
                    seq_tr_loss = []

                    if i+batch_size > len(x_train):
                        r = (i+batch_size-len(x_train))%len(x_train)
                        idx_list = range(len(x_train))
                        random.shuffle(idx_list)
                        x = np.vstack([x_train[i:],
                                       x_train[idx_list[:r]]])
                        while True:
                            if len(x)<batch_size: x = np.vstack([x, x_train])
                            else:                 break
                    else:
                        x = x_train[i:i+batch_size]


                    for j in xrange(len(x[0])-timesteps+1): # per window
                        p = float(j)/float(length-timesteps+1) *2.0*phase - phase
                        tr_loss = vae_autoencoder.train_on_batch(
                            np.concatenate((x[:,j:j+timesteps],
                                            p*np.ones((len(x), timesteps, 1))), axis=-1),
                            x[:,j:j+timesteps] )

                        seq_tr_loss.append(tr_loss)
                    mean_tr_loss.append( np.mean(seq_tr_loss) )
                    vae_autoencoder.reset_states()

                sys.stdout.write('Epoch {} / {} : loss training = {} , loss validating = {}\r'.format(epoch, nb_epoch, np.mean(mean_tr_loss), 0))
                sys.stdout.flush()   

            mean_te_loss = []
            for i in xrange(0,len(x_test),batch_size):
                seq_te_loss = []

                # batch augmentation
                if i+batch_size > len(x_test):
                    x = x_test[i:]
                    r = i+batch_size-len(x_test)

                    for k in xrange(r/len(x_test)):
                        x = np.vstack([x, x_test])
                    
                    if (r%len(x_test)>0):
                        idx_list = range(len(x_test))
                        random.shuffle(idx_list)
                        x = np.vstack([x,
                                       x_test[idx_list[:r%len(x_test)]]])
                else:
                    x = x_test[i:i+batch_size]
                
                for j in xrange(len(x[0])-timesteps+1):
                    p = float(j)/float(length-timesteps+1) * 2.0* phase - phase
                    te_loss = vae_autoencoder.test_on_batch(
                        np.concatenate((x[:,j:j+timesteps],
                                        p*np.ones((len(x), timesteps,1))), axis=-1),
                        x[:,j:j+timesteps] )
                    seq_te_loss.append(te_loss)
                mean_te_loss.append( np.mean(seq_te_loss) )
                vae_autoencoder.reset_states()

            val_loss = np.mean(mean_te_loss)
            sys.stdout.write('Epoch {} / {} : loss training = {} , loss validating = {}\r'.format(epoch, nb_epoch, np.mean(mean_tr_loss), val_loss))
            sys.stdout.flush()   


            # Early Stopping
            if val_loss <= min_loss:
                min_loss = val_loss
                wait         = 0
                plateau_wait = 0

                if save_weights_file is not None:
                    vae_autoencoder.save_weights(save_weights_file)
                else:
                    vae_autoencoder.save_weights(weights_file)
                
            else:
                if wait > patience:
                    print "Over patience!"
                    break
                else:
                    wait += 1
                    plateau_wait += 1

            #ReduceLROnPlateau
            if plateau_wait > 2:
                old_lr = float(K.get_value(vae_autoencoder.optimizer.lr))
                new_lr = old_lr * 0.2
                K.set_value(vae_autoencoder.optimizer.lr, new_lr)
                plateau_wait = 0
                print 'Reduced learning rate {} to {}'.format(old_lr, new_lr)

        gc.collect()

    # ---------------------------------------------------------------------------------
    # visualize outputs
    if plot:
        print "Data visualization"
        nDim = len(x_test[0,0]) 
        
        for i in xrange(len(x_test)):
            #if i!=6: continue #for data viz lstm_vae_custom -4 

            x_pred_mean, x_pred_std = predict(x_test[i:i+1], vae_mean_std, nDim, batch_size, timesteps,\
                                              x_std_div, x_std_offset)
            vutil.graph_variations(x_test[i], x_pred_mean, x_pred_std, scaler_dict=kwargs['scaler_dict'])
        


    return vae_autoencoder, vae_mean_std, vae_mean_std, vae_encoder_mean, vae_encoder_var, generator



def predict(x_test, vae_mean_std, nDim, batch_size, timesteps=1, x_std_div=4, x_std_offset=0.1 ):
    '''
    x_test: 1 x timestep x dim
    '''

    vae_mean_std.reset_states()

    x = x_test
    for j in xrange(batch_size-1):
        x = np.vstack([x,x_test])
    
    x_pred_mean = []
    x_pred_std  = []
    for j in xrange(len(x[0])-timesteps+1):
        x_pred = vae_mean_std.predict(np.concatenate((x[:,j:j+timesteps],
                                                      np.zeros((len(x), timesteps,1))
                                                      ), axis=-1),
                                                      batch_size=batch_size)
        x_pred_mean.append(x_pred[0,-1,:nDim])
        x_pred_std.append(x_pred[0,-1,nDim:]/x_std_div*1.5+x_std_offset)

    return x_pred_mean, x_pred_std


## class ResetStatesCallback(Callback):
##     def __init__(self, max_len):
##         self.counter = 0
##         self.max_len = max_len
        
##     def on_batch_begin(self, batch, logs={}):
##         if self.counter % self.max_len == 0:
##             self.model.reset_states()
##         self.counter += 1

