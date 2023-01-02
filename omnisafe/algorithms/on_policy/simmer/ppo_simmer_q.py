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
"""Implementation of the Q Simmer algorithm using PPO."""

from typing import NamedTuple

from omnisafe.algorithms import registry
from omnisafe.algorithms.on_policy.base.ppo import PPO


@registry.register
class PPOSimmerQ(PPO):
    """The Q Simmer algorithm implemented with PPO.

    References:
        - Title: Effects of Safety State Augmentation on Safe Exploration
        - Authors: Aivar Sootla, Alexander I. Cowen-Rivers, Jun Wang, Haitham Bou Ammar.
        - URL: https://arxiv.org/abs/2206.02675
    """

    def __init__(self, env_id: str, cfgs: NamedTuple) -> None:
        """Initialize PPOSimmerQ.

        PPOSimmerQ is a combination of :class:`PPO` and :class:`Simmer` environment wrapper.

        Args:
            env_id (str): The environment id.
            cfgs (NamedTuple): The configuration of the algorithm.
        """
        super().__init__(env_id=env_id, cfgs=cfgs)

    def algorithm_specific_logs(self):
        """Log the Saute specific information.

        .. list-table::

            *   -   Things to log
                -   Description
            *   -   Metrics/EpBudget
                -   The budget of the episode.
            *   -   Metrics/SafetyBudget
                -   The safety budget of the episode.
        """
        super().algorithm_specific_logs()
        self.logger.log_tabular('Metrics/EpBudget')
        self.logger.log_tabular('Metrics/SafetyBudget')
