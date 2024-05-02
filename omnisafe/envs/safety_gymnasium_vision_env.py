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
"""Environments in the Vision-Based Safety-Gymnasium."""

from __future__ import annotations

import os
from typing import Any, ClassVar

import numpy as np
import safety_gymnasium
import torch

from omnisafe.envs.core import CMDP, env_register
from omnisafe.typing import DEVICE_CPU, Box


@env_register
class SafetyGymnasiumVisionEnv(CMDP):
    need_auto_reset_wrapper: bool = False
    need_time_limit_wrapper: bool = False

    _support_envs: ClassVar[list[str]] = [
        'SafetyCarGoal1Vision-v0',
        'SafetyPointGoal1Vision-v0',
        'SafetyPointButton1Vision-v0',
        'SafetyPointPush1Vision-v0',
        'SafetyPointGoal2Vision-v0',
        'SafetyPointButton2Vision-v0',
        'SafetyPointPush2Vision-v0',
    ]

    def __init__(
        self,
        env_id: str,
        num_envs: int = 1,
        device: torch.device = DEVICE_CPU,
        **kwargs: Any,
    ) -> None:
        """Initialize an instance of :class:`SafetyGymnasiumVisionEnv`."""
        super().__init__(env_id)
        self._num_envs = num_envs
        self._device = torch.device(device)
        if 'MUJOCO_GL' not in os.environ:
            os.environ['MUJOCO_GL'] = 'osmesa'
        self.need_time_limit_wrapper = True
        self.need_auto_reset_wrapper = True
        self._env = safety_gymnasium.make(
            id=env_id,
            autoreset=True,
            render_mode='rgb_array',
            camera_name='vision',
            width=64,
            height=64,
            **kwargs,
        )

        self._observation_space = Box(shape=(3, 64, 64), low=0, high=255, dtype=np.uint8)
        self._action_space = self._env.action_space

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
        obs, reward, cost, terminated, truncated, info = self._env.step(
            action.detach().cpu().numpy(),
        )

        reward, cost, terminated, truncated = (
            torch.as_tensor(x, dtype=torch.float32, device=self._device)
            for x in (reward, cost, terminated, truncated)
        )
        obs = (
            torch.as_tensor(obs['vision'].copy(), dtype=torch.uint8, device=self._device)
            .float()
            .div_(255.0)
            .transpose(0, -1)
        )
        if 'final_observation' in info:
            info['final_observation'] = np.array(
                [
                    array if array is not None else np.zeros(obs.shape[-1])
                    for array in info['final_observation']['vision'].copy()
                ],
            )
            info['final_observation'] = (
                torch.as_tensor(
                    info['final_observation'],
                    dtype=torch.int8,
                    device=self._device,
                )
                .float()
                .div_(255.0)
                .transpose(0, -1)
            )

        return obs, reward, cost, terminated, truncated, info

    def reset(
        self,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[torch.Tensor, dict[str, Any]]:
        """Reset the environment.

        Args:
            seed (int, optional): The random seed. Defaults to None.
            options (dict[str, Any], optional): The options for the environment. Defaults to None.

        Returns:
            observation: Agent's observation of the current environment.
            info: Some information logged by the environment.
        """
        obs, info = self._env.reset(seed=seed, options=options)
        return (
            torch.as_tensor(obs['vision'].copy(), dtype=torch.uint8, device=self._device)
            .float()
            .div_(255.0)
            .transpose(0, -1),
            info,
        )

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
