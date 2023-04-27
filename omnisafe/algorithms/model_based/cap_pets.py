# Copyright 2023 OmniSafe Team. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Implementation of the Conservative and Adaptive Penalty algorithm."""
from __future__ import annotations

import numpy as np

from omnisafe.algorithms import registry
from omnisafe.algorithms.model_based.base import PETS
from omnisafe.algorithms.model_based.base.ensemble import EnsembleDynamicsModel
from omnisafe.algorithms.model_based.planner.cap import CAPPlanner
from omnisafe.common.lagrange import Lagrange


@registry.register
# pylint: disable-next=too-many-instance-attributes, too-few-public-methods
class CAPPETS(PETS):
    """The Conservative and Adaptive Penalty (CAP) algorithm implementation based on PETS.

    References:

        - Title: Conservative and Adaptive Penalty for Model-Based Safe Reinforcement Learning
        - Authors: Yecheng Jason Ma, Andrew Shen, Osbert Bastani, Dinesh Jayaraman.
        - URL: `CAP <https://arxiv.org/abs/2112.07701>`_
    """

    def _init_model(self) -> None:
        """Initialize the dynamics model and the planner."""
        if self._env.action_space is not None and len(self._env.action_space.shape) > 0:
            self._action_dim = self._env.action_space.shape[0]
        else:
            # error handling for action dimension is none of shape of action less than 0
            raise ValueError('Action dimension is None or less than 0')
        self._dynamics_state_space = (
            self._env.coordinate_observation_space
            if self._env.coordinate_observation_space is not None
            else self._env.observation_space
        )
        self._dynamics = EnsembleDynamicsModel(
            model_cfgs=self._cfgs.dynamics_cfgs,
            device=self._device,
            state_shape=self._dynamics_state_space.shape,
            action_shape=self._env.action_space.shape,
            reward_size=1,
            cost_size=1,
            use_cost=True,
            use_terminal=False,
            use_var=True,
            use_reward_critic=False,
            use_cost_critic=False,
            actor_critic=None,
            rew_func=None,
            cost_func=self._env.get_cost_from_obs_tensor,
            terminal_func=None,
        )

        self._lagrange = Lagrange(**self._cfgs.lagrange_cfgs)

        self._planner = CAPPlanner(
            dynamics=self._dynamics,
            num_models=self._cfgs.dynamics_cfgs.num_ensemble,
            horizon=self._cfgs.algo_cfgs.plan_horizon,
            num_iterations=self._cfgs.algo_cfgs.num_iterations,
            num_particles=self._cfgs.algo_cfgs.num_particles,
            num_samples=self._cfgs.algo_cfgs.num_samples,
            num_elites=self._cfgs.algo_cfgs.num_elites,
            momentum=self._cfgs.algo_cfgs.momentum,
            epsilon=self._cfgs.algo_cfgs.epsilon,
            init_var=self._cfgs.algo_cfgs.init_var,
            gamma=self._cfgs.algo_cfgs.gamma,
            cost_gamma=self._cfgs.algo_cfgs.cost_gamma,
            cost_limit=self._cfgs.lagrange_cfgs.cost_limit,
            lagrange=self._lagrange,
            device=self._device,
            dynamics_state_shape=self._dynamics_state_space.shape,
            action_shape=self._env.action_space.shape,
            action_max=1.0,
            action_min=-1.0,
        )

        self._use_actor_critic = False
        self._update_dynamics_cycle = int(self._cfgs.algo_cfgs.update_dynamics_cycle)

    def _init_log(self) -> None:
        """Initialize the logger"""
        super()._init_log()
        self._logger.register_key('Plan/feasible_num')
        self._logger.register_key('Plan/episode_costs_max')
        self._logger.register_key('Plan/episode_costs_mean')
        self._logger.register_key('Plan/episode_costs_min')
        self._logger.register_key('Metrics/LagrangeMultiplier')
        self._logger.register_key('Plan/var_penalty_max')
        self._logger.register_key('Plan/var_penalty_mean')
        self._logger.register_key('Plan/var_penalty_min')

    def _update_epoch(self) -> None:
        # note that logger already uses MPI statistics across all processes..
        Jc = self._logger.get_stats('Metrics/EpCost')[0]
        assert not np.isnan(Jc), 'cost for updating lagrange multiplier is nan'
        # first update Lagrange multiplier parameter
        self._lagrange.update_lagrange_multiplier(Jc)
        # then update the policy and value function
        self._logger.store(**{'Metrics/LagrangeMultiplier': self._lagrange.lagrangian_multiplier})
