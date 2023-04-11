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
"""Environments in the Safety Gymnasium."""


from typing import Any, Optional, Union

import gymnasium
import numpy as np
import safety_gymnasium
import torch

from omnisafe.envs.core import CMDP, env_register


@env_register
class SafetyGymnasiumModelBased(CMDP):  # pylint: disable=too-many-instance-attributes
    """Safety Gymnasium environment for Model based algorithms."""

    _support_envs = [
        'SafetyPointGoal0-v0-modelbased',
        'SafetyPointGoal1-v0-modelbased',
        'SafetyCarGoal0-v0-modelbased',
        'SafetyCarGoal1-v0-modelbased',
        'SafetyAntGoal0-v0-modelbased',
        'SafetyAntGoal1-v0-modelbased',
    ]
    need_auto_reset_wrapper = False
    need_time_limit_wrapper = False

    def __init__(
        self,
        env_id: str,
        num_envs: int = 1,
        device: torch.device = 'cpu',
        **kwargs,
    ) -> None:
        super().__init__(env_id)
        if num_envs == 1:
            self._env = safety_gymnasium.make(
                id=env_id.replace('-modelbased', ''),
                autoreset=False,
                **kwargs,
            )
            self._action_space = self._env.action_space
            self._observation_space = self._env.observation_space
        else:
            raise NotImplementedError

        self._device = torch.device(device)

        self._num_envs = num_envs
        self._metadata = self._env.metadata
        if env_id in [
            'SafetyPointGoal1-v0-modelbased',
            'SafetyCarGoal1-v0-modelbased',
            'SafetyAntGoal1-v0-modelbased',
        ]:
            self._constraints = ['hazards']  #'gremlins', 'buttons'],
            self._xyz_sensors = ['velocimeter', 'accelerometer']
            self._angle_sensors = ['gyro', 'magnetometer']
            self._flatten_order = (
                self._xyz_sensors
                + self._angle_sensors
                + ['goal']
                + self._constraints
                + ['robot_m']
                + ['robot']
            )
            self._base_state = self._xyz_sensors + self._angle_sensors
            self._task = 'Goal'
            self._env.reset()
            self.goal_position = self._env.task.goal.pos
            self.robot_position = self._env.task.agent.pos
            self.hazards_position = self._env.task.hazards.pos
            self.goal_distance = self._dist_xy(self.robot_position, self.goal_position)

            coordinate_sensor_obs = self._get_coordinate_sensor()
            self._coordinate_obs_size = sum(
                np.prod(i.shape) for i in list(coordinate_sensor_obs.values())
            )
            offset = 0
            self.key_to_slice = {}
            self.key_to_slice_tensor = {}

            for k in self._flatten_order:
                k_size = np.prod(coordinate_sensor_obs[k].shape)
                self.key_to_slice[k] = slice(offset, offset + k_size)
                self.key_to_slice_tensor[k] = torch.arange(offset, offset + k_size)

                offset += k_size
            self._base_state_size = sum(
                np.prod(coordinate_sensor_obs[k].shape) for k in list(self._base_state)
            )
            self.key_to_slice['base_state'] = slice(0, self._base_state_size)
            self.key_to_slice_tensor['base_state'] = torch.arange(0, self._base_state_size)

            self._num_lidar_bin = 16
            self._max_lidar_dist = 3
            self.hazards_size = 0.2
            self.goal_size = 0.3
            self.original_observation_space = self.observation_space
            self.coordinate_observation_space = gymnasium.spaces.Box(
                -np.inf,
                np.inf,
                (self._coordinate_obs_size,),
                dtype=np.float32,
            )
            flat_coordinate_obs = self._get_flat_coordinate(coordinate_sensor_obs)
            self.lidar_observation_space = gymnasium.spaces.Box(
                -np.inf,
                np.inf,
                (self.get_lidar_from_coordinate(flat_coordinate_obs).shape[0],),
                dtype=np.float32,
            )

        else:
            self._task = None
            raise NotImplementedError

    @property
    def task(self):
        """Get task name"""
        return self._task

    def get_cost_from_obs_tensor(self, obs, is_binary=True):
        """Get batch cost from batch observation"""
        assert torch.is_tensor(obs), 'obs must be tensor'
        hazards_key = self.key_to_slice_tensor['hazards']
        if len(obs.shape) == 2:
            batch_size = obs.shape[0]
            hazard_obs = obs[:, hazards_key].reshape(batch_size, -1, 2)
        elif len(obs.shape) == 3:
            batch_size = obs.shape[0] * obs.shape[1]
            hazard_obs = obs[:, :, hazards_key].reshape(batch_size, -1, 2)
        hazards_dist = torch.sqrt(torch.sum(torch.square(hazard_obs), dim=2)).reshape(
            batch_size,
            -1,
        )
        if is_binary:
            cost = torch.where(hazards_dist <= self.hazards_size, 1.0, 0.0)
            cost = cost.sum(1)
            cost = torch.where(cost >= 1, 1.0, 0.0)
        else:
            cost = ((hazards_dist < self.hazards_size) * (self.hazards_size - hazards_dist)).sum(
                1,
            ) * 10
        if len(obs.shape) == 2:
            cost = cost.reshape(obs.shape[0], 1)
        elif len(obs.shape) == 3:
            cost = cost.reshape(obs.shape[0], obs.shape[1], 1)
        return cost

    def get_goal_flag_from_obs_tensor(self, obs):
        """Get batch cost from batch observation"""
        assert torch.is_tensor(obs), 'obs must be tensor'
        goal_key = self.key_to_slice_tensor['goal']
        if len(obs.shape) == 2:
            batch_size = obs.shape[0]
            goal_obs = obs[:, goal_key].reshape(batch_size, -1, 2)
        elif len(obs.shape) == 3:
            batch_size = obs.shape[0] * obs.shape[1]
            goal_obs = obs[:, :, goal_key].reshape(batch_size, -1, 2)
        goal_dist = torch.sqrt(torch.sum(torch.square(goal_obs), dim=2)).reshape(batch_size, -1)
        goal_flat = goal_dist <= self.goal_size

        if len(obs.shape) == 2:
            goal_flat = goal_flat.reshape(obs.shape[0], 1)
        elif len(obs.shape) == 3:
            goal_flat = goal_flat.reshape(obs.shape[0], obs.shape[1], 1)
        return goal_flat

    def get_cost_from_obs(self, obs, is_binary, use_lidar):
        """Get batch cost from batch observation"""
        assert not torch.is_tensor(obs), 'obs should be numpy array'
        if not use_lidar:
            batch_size = obs.shape[0]
            hazards_key = self.key_to_slice['hazards']
            hazard_obs = obs[:, hazards_key].reshape(batch_size, -1, 2)
            hazards_dist = np.sqrt(np.sum(np.square(hazard_obs), axis=2)).reshape(batch_size, -1)
            if is_binary:
                cost = np.where(hazards_dist <= self.hazards_size, 1.0, 0.0)
                cost = cost.sum(1)
                cost = np.where(cost >= 1, 1.0, 0.0)
            else:
                cost = (
                    (hazards_dist < self.hazards_size) * (self.hazards_size - hazards_dist)
                ).sum(
                    1,
                ) * 10
        else:
            batch_size = obs.shape[0]
            hazards_key = self.key_to_slice['hazards_lidar']
            hazard_obs = obs[:, hazards_key].reshape(batch_size, self._env.task.lidar_conf.num_bins)
            lidar_hazards_threshold = (
                max(0, self._env.task.lidar_conf.max_dist - self._env.task.hazards.size)
                / self._env.task.lidar_conf.max_dist
            )
            cost = np.where(hazard_obs >= lidar_hazards_threshold, 1.0, 0.0)
            cost = cost.sum(1)
            cost = np.where(cost >= 1, 1.0, 0.0)
        return cost

    def get_lidar_from_coordinate(self, obs):
        """Get lidar observation"""
        robot_matrix_x_y = obs[self.key_to_slice['robot_m']]
        robot_matrix_x = robot_matrix_x_y[0]
        robot_matrix_y = robot_matrix_x_y[1]
        first_row = [robot_matrix_x, robot_matrix_y, 0]
        second_row = [-robot_matrix_y, robot_matrix_x, 0]
        third_row = [0, 0, 1]
        robot_matrix = [first_row, second_row, third_row]
        robot_pos = obs[self.key_to_slice['robot']]
        hazards_lidar_vec = self._obs_lidar_pseudo(robot_matrix, robot_pos, self.hazards_position)

        goal_lidar_vec = self._obs_lidar_pseudo(robot_matrix, robot_pos, [self.goal_position])
        base_state_vec = obs[self.key_to_slice['base_state']]

        obs_vec = list(base_state_vec) + list(hazards_lidar_vec) + list(goal_lidar_vec)

        # obs_vec = self.make_observation(obs, lidar_vec)
        obs_vec = np.array(obs_vec)
        obs_vec = torch.as_tensor(obs_vec, dtype=torch.float32, device=self._device).unsqueeze(0)
        return obs_vec

    def _ego_xy(self, robot_matrix, robot_pos, pos):
        """Return the egocentric XY vector to a position from the robot"""
        assert pos.shape == (2,), f'Bad pos {pos}'
        robot_3vec = robot_pos
        robot_mat = robot_matrix

        pos_3vec = np.concatenate([pos, [0]])  # Add a zero z-coordinate
        robot_3vec = np.concatenate([robot_3vec, [0]])
        world_3vec = pos_3vec - robot_3vec
        return np.matmul(world_3vec, robot_mat)[:2]

    def _obs_lidar_pseudo(
        self,
        robot_matrix,
        robot_pos,
        positions,
    ):  # pylint: disable=too-many-locals
        '''
        Return a robot-centric lidar observation of a list of positions.

        Lidar is a set of bins around the robot (divided evenly in a circle).
        The detection directions are exclusive and exhaustive for a full 360 view.
        Each bin reads 0 if there are no objects in that direction.
        If there are multiple objects, the distance to the closest one is used.
        Otherwise the bin reads the fraction of the distance towards the robot.

        E.g. if the object is 90% of lidar_max_dist away, the bin will read 0.1,
        and if the object is 10% of lidar_max_dist away, the bin will read 0.9.
        (The reading can be thought of as "closeness" or inverse distance)

        This encoding has some desirable properties:
            - bins read 0 when empty
            - bins smoothly increase as objects get close
            - maximum reading is 1.0 (where the object overlaps the robot)
            - close objects occlude far objects
            - constant size observation with variable numbers of objects
        '''
        obs = np.zeros(self._num_lidar_bin)
        lidar_exp_gain = 1.0
        lidar_alias = True
        for pos in positions:
            pos = np.asarray(pos)
            if pos.shape == (3,):
                pos = pos[:2]  # Truncate Z coordinate
            position_z = np.complex(
                *self._ego_xy(robot_matrix, robot_pos, pos),
            )  # X, Y as real, imaginary components
            dist = np.abs(position_z)
            angle = np.angle(position_z) % (np.pi * 2)
            bin_size = (np.pi * 2) / self._num_lidar_bin
            sensor_bin = int(angle / bin_size)
            bin_angle = bin_size * sensor_bin
            if self._max_lidar_dist is None:
                sensor = np.exp(-lidar_exp_gain * dist)
            else:
                sensor = max(0, self._max_lidar_dist - dist) / self._max_lidar_dist
            obs[sensor_bin] = max(obs[sensor_bin], sensor)
            # Aliasing
            if lidar_alias:
                alias = (angle - bin_angle) / bin_size
                assert (
                    0 <= alias <= 1
                ), f'bad alias {alias}, dist {dist}, angle {angle}, bin {sensor_bin}'
                bin_plus = (sensor_bin + 1) % self._num_lidar_bin
                bin_minus = (sensor_bin - 1) % self._num_lidar_bin
                obs[bin_plus] = max(obs[bin_plus], alias * sensor)
                obs[bin_minus] = max(obs[bin_minus], (1 - alias) * sensor)
        return obs

    def _get_flat_coordinate(self, coordinate_obs) -> np.ndarray:
        """get the flattened obs."""
        flat_obs = np.zeros(self.coordinate_observation_space.shape[0])
        for k in self._flatten_order:
            idx = self.key_to_slice[k]
            flat_obs[idx] = coordinate_obs[k].flat
        return flat_obs

    def _get_coordinate_sensor(self) -> dict:
        """
        We will ignore the z-axis coordinates in every poses.
        The returned obs coordinates are all in the robot coordinates.
        """
        obs = {}
        robot_matrix = self._env.task.agent.mat
        obs['robot_m'] = np.array(robot_matrix[0][:2])

        robot_pos = self._env.task.agent.pos
        goal_pos = self._env.task.goal.pos
        # vases_pos_list = self._env.task.vases.pos  # list of shape (3,) ndarray
        hazards_pos_list = self._env.task.hazards.pos  # list of shape (3,) ndarray
        # ego_goal_pos = self._env.task._ego_xy(goal_pos[:2])
        # [self._env.task._ego_xy(pos[:2]) for pos in vases_pos_list]  # list of shape (2,) ndarray
        # ego_hazards_pos_list = [
        #     self._env.task._ego_xy(pos[:2]) for pos in hazards_pos_list
        # ]  # list of shape (2,) ndarray

        ego_goal_pos = self._ego_xy(robot_matrix, robot_pos, goal_pos[:2])
        ego_hazards_pos_list = [
            self._ego_xy(robot_matrix, robot_pos, pos[:2]) for pos in hazards_pos_list
        ]  # list of shape (2,) ndarray

        # append obs to the dict
        for sensor in self._xyz_sensors:  # Explicitly listed sensors
            if sensor == 'accelerometer':
                obs[sensor] = self._env.task.agent.get_sensor(sensor)[:1]  # only x axis matters
            elif sensor == 'ballquat_rear':
                obs[sensor] = self._env.task.agent.get_sensor(sensor)
            else:
                obs[sensor] = self._env.task.agent.get_sensor(sensor)[:2]  # only x,y axis matters

        for sensor in self._angle_sensors:
            if sensor == 'gyro':
                obs[sensor] = self._env.task.agent.get_sensor(sensor)[
                    2:
                ]  # [2:] # only z axis matters
                # pass # gyro does not help
            else:
                obs[sensor] = self._env.task.agent.get_sensor(sensor)
        # --------modification-----------------
        obs['robot'] = np.array(robot_pos[:2])
        obs['hazards'] = np.array(ego_hazards_pos_list)  # (hazard_num, 2)
        obs['goal'] = ego_goal_pos  # (2,)
        # obs['vases'] = np.array(ego_vases_pos_list)  # (vase_num, 2)
        return obs

    def _dist_xy(
        self,
        pos1: Union[np.ndarray, list],
        pos2: Union[np.ndarray, list],
    ) -> float:
        """Return the distance from the robot to an XY position."""
        pos1 = np.asarray(pos1)
        pos2 = np.asarray(pos2)
        if pos1.shape == (3,):
            pos1 = pos1[:2]
        if pos2.shape == (3,):
            pos2 = pos2[:2]
        return np.sqrt(np.sum(np.square(pos1 - pos2)))

    def step(
        self,
        action: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, dict]:
        obs_original, reward, cost, terminated, truncated, info = self._env.step(
            action.detach().cpu().numpy(),
        )

        if self._task == 'Goal':
            info['old_goal_distance'] = self.goal_distance
            self.robot_position = self._env.task.agent.pos
            self.goal_distance = self._dist_xy(self.robot_position, self.goal_position)
            info['goal_distance'] = self.goal_distance
            coordinate_sensor_obs = self._get_coordinate_sensor()
            obs = self._get_flat_coordinate(coordinate_sensor_obs)

            obs = torch.as_tensor(obs, dtype=torch.float32, device=self._device)

            info['obs_original'] = obs_original
            goal_met = 'goal_met' in info  # reach the goal
            info['goal_met'] = goal_met

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

    def reset(self, seed: Optional[int] = None) -> tuple[torch.Tensor, dict]:
        obs_original, info = self._env.reset(seed=seed)
        if self._task == 'Goal':
            self.goal_position = self._env.task.goal.pos
            self.robot_position = self._env.task.agent.pos
            self.hazards_position = self._env.task.hazards.pos
            self.goal_distance = self._dist_xy(self.robot_position, self.goal_position)
            coordinate_sensor_obs = self._get_coordinate_sensor()
            flat_coordinate_obs = self._get_flat_coordinate(coordinate_sensor_obs)
            self.get_lidar_from_coordinate(flat_coordinate_obs)
            info['obs_original'] = obs_original
            info['goal_met'] = False

            obs = torch.as_tensor(flat_coordinate_obs, dtype=torch.float32, device=self._device)
        return obs, info

    def set_seed(self, seed: int) -> None:
        self.reset(seed=seed)

    def sample_action(self) -> torch.Tensor:
        """Sample a random action.

        Returns:
            torch.Tensor: A random action.
        """
        return torch.as_tensor(
            self._env.action_space.sample(),
            dtype=torch.float32,
            device=self._device,
        )

    def render(self) -> Any:
        """Render the environment.

        Returns:
            Any: Rendered environment.
        """
        return self._env.render()

    def close(self) -> None:
        self._env.close()
