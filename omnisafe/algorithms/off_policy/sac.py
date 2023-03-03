# Copyright 2022-2023 OmniSafe Team. All Rights Reserved.
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
"""Implementation of the Soft Actor-Critic algorithm."""


import torch
from torch import nn, optim

from omnisafe.algorithms import registry
from omnisafe.algorithms.off_policy.ddpg import DDPG
from omnisafe.utils import distributed
from omnisafe.utils.config import Config


@registry.register
# pylint: disable-next=too-many-instance-attributes, too-few-public-methods
class SAC(DDPG):
    """The Soft Actor-Critic (SAC) algorithm.

    References:
        - Title: Soft Actor-Critic: Off-Policy Maximum Entropy Deep Reinforcement Learning with a Stochastic Actor
        - Authors: Tuomas Haarnoja, Aurick Zhou, Pieter Abbeel, Sergey Levine.
        - URL: `SAC <https://arxiv.org/abs/1801.01290>`_
    """

    def __init__(self, env_id: str, cfgs: Config) -> None:
        super().__init__(env_id, cfgs)
        self._log_alpha: torch.Tensor
        self._alpha_optimizer: optim.Optimizer
        self._target_entropy: float

    def _init(self) -> None:
        super()._init()
        if self._cfgs.auto_alpha:
            self._target_entropy = -torch.prod(torch.Tensor(self._env.action_space.shape)).item()
            self._log_alpha = torch.zeros(1, requires_grad=True, device=self._device)
            self._alpha_optimizer = optim.Adam(
                [self._log_alpha], lr=self._cfgs.model_cfgs.critic.lr
            )
        else:
            self._log_alpha = torch.log(torch.tensor(self._cfgs.alpha, device=self._device))

    def _init_log(self) -> None:
        super()._init_log()
        self._logger.register_key('Value/alpha')
        self._logger.register_key('Loss/alpha_loss')

    @property
    def _alpha(self) -> float:
        return self._log_alpha.exp().item()

    def _update_rewrad_critic(
        self,
        obs: torch.Tensor,
        action: torch.Tensor,
        reward: torch.Tensor,
        done: torch.Tensor,
        next_obs: torch.Tensor,
    ) -> None:
        with torch.no_grad():
            next_action = self._target_actor_critic.actor.predict(next_obs, deterministic=False)
            next_logp = self._target_actor_critic.actor.log_prob(next_action)
            next_q1_value_r, next_q2_value_r = self._target_actor_critic.reward_critic(
                next_obs, next_action
            )
            next_q_value_r = torch.min(next_q1_value_r, next_q2_value_r) - next_logp * self._alpha
            target_q_value_r = reward + self._cfgs.gamma * (1 - done) * next_q_value_r

        q1_value_r, q2_value_r = self._actor_critic.reward_critic(obs, action)
        loss = nn.functional.mse_loss(q1_value_r, target_q_value_r) + nn.functional.mse_loss(
            q2_value_r, target_q_value_r
        )

        if self._cfgs.use_critic_norm:
            for param in self._actor_critic.reward_critic.parameters():
                loss += param.pow(2).sum() * self._cfgs.critic_norm_coeff

        self._actor_critic.reward_critic_optimizer.zero_grad()
        loss.backward()

        if self._cfgs.use_max_grad_norm:
            torch.nn.utils.clip_grad_norm_(
                self._actor_critic.reward_critic.parameters(), self._cfgs.max_grad_norm
            )
        distributed.avg_grads(self._actor_critic.reward_critic)
        self._actor_critic.reward_critic_optimizer.step()
        self._logger.store(
            **{
                'Loss/Loss_reward_critic': loss.mean().item(),
                'Value/reward_critic': q1_value_r.mean().item(),
            }
        )

    def _update_actor(
        self,
        obs: torch.Tensor,
    ) -> None:
        super()._update_actor(obs)

        if self._cfgs.auto_alpha:
            with torch.no_grad():
                action = self._actor_critic.actor.predict(obs, deterministic=False)
                log_prob = self._actor_critic.actor.log_prob(action)
            alpha_loss = -self._log_alpha * (log_prob + self._target_entropy).mean()

            self._alpha_optimizer.zero_grad()
            alpha_loss.backward()
            self._alpha_optimizer.step()
        self._logger.store(
            **{
                'Value/alpha': self._alpha,
            }
        )

    def _loss_pi(
        self,
        obs: torch.Tensor,
    ) -> torch.Tensor:
        action = self._actor_critic.actor.predict(obs, deterministic=False)
        log_prob = self._actor_critic.actor.log_prob(action)
        q1_value_r, q2_value_r = self._actor_critic.reward_critic(obs, action)
        loss = (self._alpha * log_prob - torch.min(q1_value_r, q2_value_r)).mean()
        return loss

    def _log_when_not_update(self) -> None:
        super()._log_when_not_update()
        self._logger.store(
            **{
                'Value/alpha': self._alpha,
            }
        )
