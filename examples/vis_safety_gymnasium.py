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
"""Example of using Safety Gymnasium environments."""

import argparse

import safety_gymnasium


def run_random(env_name):
    """Run a random agent in the environment."""
    env = safety_gymnasium.make(env_name, render_mode='rgb_array')
    # env.seed(0)
    obs, _ = env.reset()
    terminated = False
    ep_ret = 0
    ep_cost = 0
    while True:
        print('rgb_array', env.render())
        if terminated:
            print(f'Episode Return: {ep_ret} \t Episode Cost: {ep_cost}')
            ep_ret, ep_cost = 0, 0
            obs, _ = env.reset()
        assert env.observation_space.contains(obs)
        act = env.action_space.sample()
        assert env.action_space.contains(act)
        # Use the environment's built_in max_episode_steps
        obs, reward, cost, terminated, truncated, info = env.step(
            act
        )  # pylint: disable=unused-variable
        ep_ret += reward
        ep_cost += cost


if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('--env', default='SafetyPointGoal2-v0')
    args = parser.parse_args()
    run_random(args.env)
