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
"""Environments in the Safety-Gymnasium."""

from __future__ import annotations

import logging
from typing import Any, ClassVar

import numpy as np
import torch
from metadrive import SafeMetaDriveEnv

from omnisafe.envs.core import CMDP, env_register
from omnisafe.typing import DEVICE_CPU


@env_register
class SafetyMetaDriveEnv(CMDP):
    """Safe MetaDrive Environment.

    More information about MetaDrive environment is provided in https://github.com/metadriverse/metadrive.

    Args:
        env_id (str): Environment id.
        num_envs (int, optional): Number of environments. Defaults to 1.
        device (torch.device, optional): Device to store the data. Defaults to
            ``torch.device('cpu')``.

    Keyword Args:
        render_mode (str, optional): The render mode ranges from 'human' to 'rgb_array' and 'rgb_array_list'.
            Defaults to 'rgb_array'.
        camera_name (str, optional): The camera name.
        camera_id (int, optional): The camera id.
        width (int, optional): The width of the rendered image. Defaults to 256.
        height (int, optional): The height of the rendered image. Defaults to 256.

    Attributes:
        need_auto_reset_wrapper (bool): Whether to use auto reset wrapper.
        need_time_limit_wrapper (bool): Whether to use time limit wrapper.
    """

    need_auto_reset_wrapper: bool = False
    need_time_limit_wrapper: bool = False

    _support_envs: ClassVar[list[str]] = [
        'SafeMetaDrive',
    ]

    def __init__(
        self,
        env_id: str,
        num_envs: int = 1,
        device: torch.device = DEVICE_CPU,
        **kwargs: Any,  # pylint: disable=unused-argument
    ) -> None:
        """Initialize an instance of :class:`SafetyGymnasiumEnv`."""
        super().__init__(env_id)
        self._num_envs = num_envs
        self._device = torch.device(device)

        self._env = SafeMetaDriveEnv()
        self._env.logger.setLevel(logging.FATAL)
        self._action_space = self._env.action_space
        self._observation_space = self._env.observation_space
        self._metadata = self._env.metadata

    def step(
        self,
        action: torch.Tensor,
    ) -> tuple[
        torch.Tensor,
        torch.Tensor,
        torch.Tensor,
        torch.Tensor,
        torch.Tensor,
        dict[str, Any],
    ]:
        """Step the environment.

        .. note::
            OmniSafe uses auto reset wrapper to reset the environment when the episode is
            terminated. So the ``obs`` will be the first observation of the next episode. And the
            true ``final_observation`` in ``info`` will be stored in the ``final_observation`` key
            of ``info``.

        Args:
            action (torch.Tensor): Action to take.

        Returns:
            observation: The agent's observation of the current environment.
            reward: The amount of reward returned after previous action.
            cost: The amount of cost returned after previous action.
            terminated: Whether the episode has ended.
            truncated: Whether the episode has been truncated due to a time limit.
            info: Some information logged by the environment.
        """
        obs, reward, terminated, truncated, info = self._env.step(
            action.detach().cpu().numpy(),
        )
        cost = info['cost']
        obs, reward, cost, terminated, truncated = (
            torch.as_tensor(x, dtype=torch.float32, device=self._device)
            for x in (obs, reward, cost, terminated, truncated)
        )
        if 'final_observation' in info:
            info['final_observation'] = np.array(
                [
                    array if array is not None else np.zeros(obs.shape[-1])
                    for array in info['final_observation']
                ],
            )
            info['final_observation'] = torch.as_tensor(
                info['final_observation'],
                dtype=torch.float32,
                device=self._device,
            )

        return obs, reward, cost, terminated, truncated, info

    def reset(self, seed: int | None = None) -> tuple[torch.Tensor, dict[str, Any]]:
        """Reset the environment.

        Args:
            seed (int or None, optional): Seed to reset the environment.
                Defaults to None.

        Returns:
            observation: Agent's observation of the current environment.
            info: Some information logged by the environment.
        """
        obs, info = self._env.reset(seed=seed)
        return torch.as_tensor(obs, dtype=torch.float32, device=self._device), info

    def set_seed(self, seed: int) -> None:
        """Set the seed for the environment.

        Args:
            seed (int): Seed to set.
        """
        self.reset(seed=seed)

    def sample_action(self) -> torch.Tensor:
        """Sample a random action.

        Returns:
            A random action.
        """
        return torch.as_tensor(
            self._env.action_space.sample(),
            dtype=torch.float32,
            device=self._device,
        )

    def render(self) -> Any:
        """Compute the render frames as specified by :attr:`render_mode` during the initialization of the environment.

        Returns:
            The render frames: we recommend to use `np.ndarray`
                which could construct video by moviepy.
        """
        return self._env.render()

    def close(self) -> None:
        """Close the environment."""
        self._env.close()
