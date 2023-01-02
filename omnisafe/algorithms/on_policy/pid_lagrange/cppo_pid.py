# Copyright 2022 OmniSafe Team. All Rights Reserved.
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
"""Implementation of the PID-Lagrange version of the CPPO algorithm."""

from typing import NamedTuple

import torch

from omnisafe.algorithms import registry
from omnisafe.algorithms.on_policy.base.policy_gradient import PolicyGradient
from omnisafe.common.pid_lagrange import PIDLagrangian
from omnisafe.utils.config_utils import namedtuple2dict


@registry.register
class CPPOPid(PolicyGradient, PIDLagrangian):
    r"""The PID-Lagrange version of the CPPO algorithm.

    Similar to :class:`PDO`, which is a simple combination of :class:`PolicyGradient` and :class:`Lagrange`,
    this class is a simple combination of :class:`PolicyGradient` and :class:`PIDLagrangian`.

    .. note::
        The PID-Lagrange is more general than the Lagrange, and can be used in any policy gradient algorithm.
        (``omnisafe`` provide the PID-Lagrange version of the PPO (just this class) and TRPO.)
        Furthermore, it is more stable than the naive Lagrange.

    References:
        - Title: Responsive Safety in Reinforcement Learning by PID Lagrangian Methods
        - Authors: Joshua Achiam, David Held, Aviv Tamar, Pieter Abbeel.
        - URL: https://arxiv.org/abs/2007.03964
    """

    def __init__(self, env_id: str, cfgs: NamedTuple) -> None:
        """Initialize CPPOPid.

        CPPOPid is a simple combination of :class:`PolicyGradient` and :class:`PIDLagrangian`.

        Args:
            env_id (str): The environment id.
            cfgs (NamedTuple): The configuration of the algorithm.
        """
        PolicyGradient.__init__(
            self,
            env_id=env_id,
            cfgs=cfgs,
        )
        PIDLagrangian.__init__(self, **namedtuple2dict(self.cfgs.PID_cfgs))

        self.clip = self.cfgs.clip
        self.cost_limit = self.cfgs.PID_cfgs.cost_limit

    def algorithm_specific_logs(self) -> None:
        """Log the CPPOPid specific information.

        .. list-table::

            *   -   Things to log
                -   Description
            *   -   Metrics/LagrangeMultiplier
                -   The Lagrange multiplier value in current epoch.
            *   -   PID/pid_Kp
                -   The Kp value in current epoch.
            *   -   PID/pid_Ki
                -   The Ki value in current epoch.
            *   -   PID/pid_Kd
                -   The Kd value in current epoch.
        """
        super().algorithm_specific_logs()
        self.logger.log_tabular('Metrics/LagrangeMultiplier', self.cost_penalty)
        self.logger.log_tabular('PID/pid_Kp', self.pid_kp)
        self.logger.log_tabular('PID/pid_Ki', self.pid_ki)
        self.logger.log_tabular('PID/pid_Kd', self.pid_kd)

    # pylint: disable=too-many-arguments,too-many-locals
    def compute_loss_pi(
        self,
        obs: torch.Tensor,
        act: torch.Tensor,
        log_p: torch.Tensor,
        adv: torch.Tensor,
        cost_adv: torch.Tensor,
    ) -> tuple((torch.Tensor, dict)):
        r"""
        Computing pi/actor loss.
        In CPPOPid, the loss is defined as:

        .. math::
            L^{CLIP} = \mathbb{E}_{s_t \sim \rho_{\pi}}
            \left[ \min(r_t (A^{R}_t - \lambda A^{C}_t), \text{clip}(r_t, 1-\epsilon, 1+\epsilon) (A^{R}_t -
            \lambda A^{C}_t)) \right]

        where :math:`r_t = \frac{\pi_\theta(a_t|s_t)}{\pi_\theta^{old}(a_t|s_t)}`,
        :math:`\epsilon` is the clip parameter, :math:`A^{R}_t` is the reward advantage,
        :math:`A^{C}_t` is the cost advantage, and :math:`\lambda` is the Lagrange multiplier.

        Args:
            obs (torch.Tensor): ``observation`` stored in buffer.
            act (torch.Tensor): ``action`` stored in buffer.
            log_p (torch.Tensor): ``log probability`` of action stored in buffer.
            adv (torch.Tensor): ``advantage`` stored in buffer.
            cost_adv (torch.Tensor): ``cost advantage`` stored in buffer.
        """
        dist, _log_p = self.actor_critic.actor(obs, act)
        ratio = torch.exp(_log_p - log_p)
        ratio_clip = torch.clamp(ratio, 1 - self.clip, 1 + self.clip)

        surr_adv = (torch.min(ratio * adv, ratio_clip * adv)).mean()
        surr_cadv = (torch.max(ratio * cost_adv, ratio_clip * cost_adv)).mean()

        loss_pi = -surr_adv
        loss_pi -= self.cfgs.entropy_coef * dist.entropy().mean()

        penalty = self.cost_penalty
        loss_pi += penalty * surr_cadv
        loss_pi /= 1 + penalty

        # Useful extra info
        approx_kl = 0.5 * (log_p - _log_p).mean().item()
        ent = dist.entropy().mean().item()
        pi_info = dict(kl=approx_kl, ent=ent, ratio=ratio.mean().item())

        return loss_pi, pi_info

    def update(self) -> tuple((dict, dict)):
        r"""Update actor, critic, running statistics as we used in the :class:`PPO` algorithm.

        Additionally, we update the Lagrange multiplier parameter,
        by calling the :meth:`update_lagrange_multiplier` method.
        """
        # Note that logger already uses MPI statistics across all processes..
        ep_costs = self.logger.get_stats('Metrics/EpCost')[0]
        # First update Lagrange multiplier parameter
        self.pid_update(ep_costs)
        # now update policy and value network
        raw_data, data = self.buf.pre_process_data()
        obs, act, target_v, target_c, log_p, adv, cost_adv = (
            data['obs'],
            data['act'],
            data['target_v'],
            data['target_c'],
            data['log_p'],
            data['adv'],
            data['cost_adv'],
        )
        # Update critic
        self.update_value_net(obs=obs, target_v=target_v)
        self.update_cost_net(obs=obs, target_c=target_c)
        # Update actor
        self.update_policy_net(obs=obs, act=act, log_p=log_p, adv=adv, cost_adv=cost_adv)
        return raw_data, data
