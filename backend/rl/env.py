"""
Contextual-bandit environment for news recommendation.

Framing: this follows the dissertation's chosen approach of a contextual
bandit (rather than a multi-step MDP like DQN/PPO-for-control) — at every
round the agent observes a context, picks ONE category ("arm") to serve,
and gets an immediate reward that depends only on that round's context and
action, not on any longer-horizon state transition. Running this through
Stable-Baselines3 (PPO) rather than a hand-rolled bandit algorithm is a
deliberate choice to stay inside the SB3 + PyTorch + Gymnasium stack the
dissertation names, while `gamma=0` in rl/train.py makes PPO optimize each
round's immediate reward independently, i.e. true bandit behaviour.

Each Gym "episode" corresponds to one simulated user's browsing SESSION of
several rounds (not one round), because a single cold-start round carries
no informative context (a brand-new user's per-category stats are all
zero) — there is nothing for the policy to condition on. Across a session,
the user's own accumulating click/reward history *within that session*
becomes the informative context, which is exactly the "personalize as we
observe more of this user's behaviour" signal a contextual bandit is
supposed to exploit. The trained policy generalizes across users because
it learns the *mapping* from context shape to good actions, not anything
user-specific.

`user_sampler()` returns a fresh "session" object exposing:
  - session.observe() -> np.ndarray context, shape (num_categories, FEATURES_PER_ARM)
  - session.pull(action_idx) -> float reward
"""
from __future__ import annotations

import numpy as np
import gymnasium as gym
from gymnasium import spaces

FEATURES_PER_ARM = 4
DEFAULT_SESSION_LENGTH = 20


class NewsRecommenderEnv(gym.Env):
    metadata = {'render_modes': []}

    def __init__(self, categories, user_sampler, session_length=DEFAULT_SESSION_LENGTH, seed=None):
        super().__init__()
        self.categories = list(categories)
        self.num_categories = len(self.categories)
        self.user_sampler = user_sampler
        self.session_length = session_length

        self.observation_space = spaces.Box(
            low=0.0, high=1.0, shape=(self.num_categories * FEATURES_PER_ARM,), dtype=np.float32
        )
        self.action_space = spaces.Discrete(self.num_categories)

        self._session = None
        self._step_count = 0

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self._session = self.user_sampler()
        self._step_count = 0
        obs = self._session.observe().astype(np.float32).flatten()
        return obs, {}

    def step(self, action):
        reward = float(self._session.pull(int(action)))
        self._step_count += 1
        terminated = self._step_count >= self.session_length
        truncated = False
        obs = self._session.observe().astype(np.float32).flatten()
        info = {'category': self.categories[int(action)]}
        return obs, reward, terminated, truncated, info
