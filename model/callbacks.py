import os
import numpy as np
from stable_baselines3.common.callbacks import BaseCallback

class TrainingCallback(BaseCallback):

    def __init__( self, log_freq: int, verbose=1 ):
        super( TrainingCallback, self ).__init__( verbose )
        self.log_freq = log_freq

    def _on_step( self ):
        #
        if self.n_calls % self.log_freq == 0:
            if len( self.model.ep_info_buffer ) > 0:
                mean_reward = np.mean([ep_info['r'] for ep_info in self.model.ep_info_buffer])
                mean_length = np.mean([ep_info['l'] for ep_info in self.model.ep_info_buffer])

                print(f"Step: {self.num_timesteps:<10} | Mean Reward: {mean_reward:<8.2f} | Mean Ep Length: {mean_length:<8.0f}")
        return True