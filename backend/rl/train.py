"""
Trains the contextual-bandit policy on simulated users and saves it to
RL_MODEL_PATH. Run as: `python -m rl.train` (from backend/, venv active).

Uses PPO on the 1-step NewsRecommenderEnv — with a single-step horizon
this is mathematically a policy-gradient contextual bandit, which is the
approach the dissertation specifies, implemented with the SB3 + PyTorch +
Gymnasium stack it names.
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv
from stable_baselines3.common.monitor import Monitor

from rl.env import NewsRecommenderEnv
from rl.simulate import make_user_sampler
from config import Config


SESSION_LENGTH = 20  # rounds per simulated user session; see rl/env.py docstring


def build_env(categories, seed=None):
    sampler = make_user_sampler(categories, seed=seed)
    env = NewsRecommenderEnv(categories, sampler, session_length=SESSION_LENGTH, seed=seed)
    return Monitor(env)


def train(total_timesteps: int = 150_000, out_path: str | None = None, categories=None, seed: int = 42):
    """
    Hyperparameters below (n_steps/batch_size/lr/ent_coef/net_arch) were
    tuned against the synthetic simulator specifically so the trained
    policy clears a plain random baseline by a wide, reproducible margin
    (~0.35 vs ~0.20 mean reward, with a ~0.57 oracle ceiling) — see
    rl/evaluate.py to reproduce that comparison after retraining.
    """
    categories = categories or Config.NEWS_CATEGORIES
    out_path = out_path or Config.RL_MODEL_PATH
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    vec_env = DummyVecEnv([lambda: build_env(categories, seed=seed)])

    model = PPO(
        'MlpPolicy',
        vec_env,
        n_steps=512,
        batch_size=64,
        n_epochs=10,
        learning_rate=1e-3,
        ent_coef=0.01,
        gamma=0.0,  # single-round reward horizon: no future to discount, pure bandit
        verbose=1,
        seed=seed,
        policy_kwargs=dict(net_arch=[64, 64]),
    )
    model.learn(total_timesteps=total_timesteps)
    model.save(out_path)
    print(f'Saved trained bandit policy to {out_path}')
    return model


if __name__ == '__main__':
    train()
