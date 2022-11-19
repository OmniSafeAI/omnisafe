import abc

import torch.nn as nn


class Actor(abc.ABC, nn.Module):
    def __init__(self, obs_dim, act_dim, weight_initialization_mode, shared=None):
        super(Actor, self).__init__()
        self.obs_dim = obs_dim
        self.act_dim = act_dim
        self.shared = shared
        self.weight_initialization_mode = weight_initialization_mode

    @abc.abstractmethod
    def dist(self, obs):
        """
        Returns:
            torch.distributions.Distribution
        """
        pass

    @abc.abstractmethod
    def log_prob_from_dist(self, pi, act):
        """
        Returns:
            torch.Tensor
        """
        pass

    def forward(self, obs, act=None):
        """
        Returns:
            the distributions for given obs and the log likelihood of given actions under the distributions.
        """
        pi = self.dist(obs)
        logp_a = None
        if act is not None:
            logp_a = self.log_prob_from_dist(pi, act)
        return pi, logp_a

    @abc.abstractmethod
    def predict(self, obs, determinstic=False):
        """
        Returns:
            Predict action based on observation without exploration noise.
            Use this method for evaluation purposes.
        """
        pass
