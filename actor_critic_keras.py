from keras import backend as K
from keras.layers import Dense, Activation, Input, Conv2D, Flatten, LSTM, Dropout
from keras.models import Model, load_model
from keras.optimizers import Adam
from keras.callbacks import ModelCheckpoint
from keras.layers.wrappers import TimeDistributed
import tensorflow as tf
import sys
import pickle
import numpy as np
from math import log
import cv2
from collections import deque
import matplotlib.pyplot as plt

stack_size = 4

class Agent(object):
    def __init__(self, alpha, beta, gamma=0.99, n_actions=4,
                 layer1_size=1024, layer2_size=512, input_dims=8, env_name = ''):
        self.gamma = gamma
        self.alpha = alpha
        self.beta = beta
        self.input_dims = input_dims
        self.fc1_dims = layer1_size
        self.fc2_dims = layer2_size
        self.n_actions = n_actions
        self.score_history = []
        self.stacked_frames = deque([np.zeros((76, 84), dtype=np.int) for i in range(stack_size)], maxlen=4)
        self.actor, self.critic, self.policy = self.build_actor_critic_network(env_name)
        self.action_space = [i for i in range(n_actions)]

    def getEntropia():
        return self.entropy

    def initialize_stacked_frames(self, initial_frame):
        frame = self.preprocess(initial_frame)
        for i in range(stack_size):
            stacked_frames.append(frame)
        
        stacked_state = np.stack(stacked_frames, axis = 2)
        return stacked_state
            
    #funzione di preprocess: rendiamo i frame monocromatici e
    #tagliamo tutte le parti di immagine inutili all'apprendimento e normalizziamo tutti i valori a 1
    def preprocess(self, observation):
        retObs = cv2.cvtColor(cv2.resize(observation, (84, 110)), cv2.COLOR_BGR2GRAY)
        retObs = retObs[9:102,:]
        ret, retObs = cv2.threshold(retObs,1,255,cv2.THRESH_BINARY)
        # plt.imshow(np.squeeze(retObs))
        # plt.show()
        return np.reshape(retObs / 255,(93,84,1))

    #creiamo uno stack di frames, tenendo traccia delle tre osservazioni precedenti ricevute
    def stack_frames(self, state, isNewEpisode = False):
        frame = self.preprocess(state)
        if isNewEpisode: #nel caso dell'inizio di un nuovo episodio lo stack viene riempito del primo frame più volte
            #Clear our stack
            self.stacked_frames = deque([np.zeros((93, 84), dtype= np.int) for i in range(stack_size)], maxlen=stack_size)

            #since qu're in a new episode copy the same frame 4x
            self.stacked_frames.append(frame)
            self.stacked_frames.append(frame)
            self.stacked_frames.append(frame)
            self.stacked_frames.append(frame)

            stacked_state = np.stack(self.stacked_frames, axis=2)
            stacked_frames = self.stacked_frames
        else: #se si continua un nuovo episodio, aggiungiamo il nuovo stato togliendo il vecchio
            stacked_frames = self.stacked_frames
            stacked_frames.append(frame)
            stacked_state = np.stack(stacked_frames, axis=2)#???
        
        out = np.reshape(stacked_state,(93, 84, 4)) #conversione in un formato elggibile alla rete
        return out, stacked_frames

    def build_actor_critic_network(self, env_name):
        #creazione della struttura delle nostre due reti
        entropia = Input(shape = [1])
        delta = Input(shape = [1])
        input = Input(shape=(93, 84, 4))
        head = Conv2D(16, kernel_size=(3, 3), activation='relu')(input)
        conv1 = Conv2D(16, kernel_size=(3, 3), activation='relu')(head)
        input_tail_network = Flatten()(conv1)
        # input_tail_network = Input(shape=self.input_dims)
        # input = input_tail_network
        dense1 = Dense(self.fc1_dims, activation='relu')(input_tail_network)
        dense2 = Dense(self.fc2_dims, activation='relu')(dense1)
        probs = Dense(self.n_actions, activation='softmax')(dense2)
        values = Dense(1, activation='linear')(dense2)

        actor = Model(input=[input, entropia, delta], output=[probs])
        critic = Model(input=[input], output=[values])
        actor.summary()
        policy = Model(input=[input], output=[probs])

        if (env_name != ''):
            actor.load_weights(env_name + '_actor.h5')        
            critic.load_weights(env_name + '_critic.h5')
            with open (env_name + '_scores.dat', 'rb') as fp:
                self.score_history = pickle.load(fp)
            
        def custom_loss(y_true, y_pred):
            out = K.clip(y_pred, 1e-5, 1-1e-5)
            log_lik = y_true*K.log(out) + 0 * entropia
            return K.sum(-log_lik*delta)
    
        actor.compile(optimizer=Adam(lr=self.alpha), loss=custom_loss)
        critic.compile(optimizer=Adam(lr=self.beta), loss='mean_squared_error')

        return actor, critic, policy

    def choose_action(self, stacked_observation):
        state = stacked_observation[np.newaxis, :]
        probabilities = self.policy.predict(state)[0] 
        action = np.random.choice(self.action_space, p=probabilities)

        # print(probabilities)
        #Il clipping delle probabilità evita il logaritmo -inf
        self.entropy = - (tf.math.reduce_sum(probabilities * tf.math.log(tf.clip_by_value(probabilities,1e-5,1.0 - 1e-5))))
        return action

    def learn(self, current_stacked_state, action, reward, state_, done):
        state = current_stacked_state[np.newaxis,:]

        s_, dump = self.stack_frames(state_)
        state_ = s_[np.newaxis,:]
        # state_ = state_[np.newaxis,:]


        value = self.critic.predict(state)[0]
        next_value = self.critic.predict(state_)[0]

        if done:
            target = reward + self.gamma * next_value * 0
        else:
            target = reward + self.gamma * next_value
        
        advantage = target - value
        actions = np.zeros([1, self.n_actions])
        actions[np.arange(1), action] = 1
        # print(target.shape)
        # target = np.reshape(target, (1, target.shape[1]))


        self.actor.fit([state, np.reshape(self.entropy, (1, 1)), advantage], actions, epochs=1, verbose = 0)
        self.critic.fit(state, target, epochs=1, verbose=0)

    def save(self, envName):
        self.actor.save_weights(envName + '_actor.h5')        
        self.critic.save_weights(envName + '_critic.h5')
        with open(envName + '_scores.dat', 'wb') as fp:
            pickle.dump(self.score_history, fp)

        