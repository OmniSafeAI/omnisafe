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
"""Implementation of the DDPGPID (PID version of DDPGLag) algorithm."""


import torch

from omnisafe.algorithms import registry
from omnisafe.algorithms.off_policy.ddpg import DDPG
from omnisafe.common.pid_lagrange import PIDLagrangian


@registry.register
# pylint: disable-next=too-many-instance-attributes, too-few-public-methods
class DDPGPID(DDPG):
    """The DDPGPID (PID version of DDPGLag) algorithm.

    References:
        - Title: Responsive Safety in Reinforcement Learning by PID Lagrangian Methods
        - Authors: Adam Stooke, Joshua Achiam, Pieter Abbeel.
        - URL: `DDPGPID <https://arxiv.org/abs/2007.03964>`_
    """

    def _init(self) -> None:
        """The initialization of the DDPGPID algorithm.

        The DDPGPID algorithm uses a PID-Lagrange multiplier to balance the cost and reward.
        """
        super()._init()
        self._lagrange: PIDLagrangian = PIDLagrangian(**self._cfgs.lagrange_cfgs)

    def _init_log(self) -> None:
        """Log the DDPGPID specific information.

        +----------------------------+------------------------------+
        | Things to log              | Description                  |
        +============================+==============================+
        | Metrics/LagrangeMultiplier | The PID-Lagrange multiplier. |
        +----------------------------+------------------------------+
        """
        super()._init_log()
        self._logger.register_key('Metrics/LagrangeMultiplier')

    def _update(self) -> None:
        """Update actor, critic, as we used in the :class:`PolicyGradient` algorithm.

        Additionally, we update the Lagrange multiplier parameter by calling the
        :meth:`pid_update` method.
        """
        super()._update()
        Jc = self._logger.get_stats('Metrics/EpCost')[0]
        if self._epoch>self._cfgs.algo_cfgs.warmup_epochs:
            self._lagrange.pid_update(Jc)
        self._logger.store(
            {
                'Metrics/LagrangeMultiplier': self._lagrange.lagrangian_multiplier,
            },
        )

    def _loss_pi(
        self,
        obs: torch.Tensor,
    ) -> torch.Tensor:
        r"""Computing ``pi/actor`` loss.

        The loss function in DDPGPID is defined as:

        .. math::

            L = -Q^V (s, \pi (s)) + \lambda Q^C (s, \pi (s))

        where :math:`Q^V` is the value of reward critic network output,
        and :math:`\pi` is the policy network.

        Args:
            obs (torch.Tensor): The ``observation`` sampled from buffer.

        Returns:
            The loss of pi/actor.
        """
        action = self._actor_critic.actor.predict(obs, deterministic=True)
        loss_r = -self._actor_critic.reward_critic(obs, action)[0]
        loss_c = (
            self._lagrange.lagrangian_multiplier
            * self._actor_critic.cost_critic(obs, action)[0]
        )
        return (loss_r + loss_c).mean() / (1 + self._lagrange.lagrangian_multiplier)

    def _log_when_not_update(self) -> None:
        """Log default value when not update."""
        super()._log_when_not_update()
        self._logger.store(
            {
                'Metrics/LagrangeMultiplier': self._lagrange.lagrangian_multiplier,
            },
        )
