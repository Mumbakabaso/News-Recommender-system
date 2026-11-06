"""
Reproduces the trained-vs-random-vs-oracle comparison used to validate the
bandit during development (see rl/train.py's docstring for the numbers
this should roughly reproduce). Useful as-is for the dissertation's
evaluation/results chapter — run as `python -m rl.evaluate` from backend/.
"""
from __future__ import annotations
import numpy as np
from stable_baselines3 import PPO

from rl.env import NewsRecommenderEnv
from rl.simulate import make_user_sampler
from rl.train import SESSION_LENGTH
from config import Config


def eval_policy(categories, action_fn, seed, n_sessions=300, session_length=SESSION_LENGTH):
    sampler = make_user_sampler(categories, seed=seed)
    env = NewsRecommenderEnv(categories, sampler, session_length=session_length, seed=seed)
    rewards = []
    for _ in range(n_sessions):
        obs, _ = env.reset()
        done = False
        while not done:
            action = action_fn(env, obs)
            obs, reward, terminated, truncated, _ = env.step(action)
            rewards.append(reward)
            done = terminated or truncated
    return float(np.mean(rewards))


def main(model_path=None, seed=123, n_sessions=300):
    categories = Config.NEWS_CATEGORIES
    model_path = model_path or Config.RL_MODEL_PATH
    model = PPO.load(model_path)

    trained_avg = eval_policy(
        categories, lambda env, obs: int(model.predict(obs, deterministic=True)[0]), seed, n_sessions
    )

    rng = np.random.default_rng(0)
    random_avg = eval_policy(
        categories, lambda env, obs: int(rng.integers(0, len(categories))), seed, n_sessions
    )

    oracle_avg = eval_policy(
        categories, lambda env, obs: int(np.argmax(env._session.user.affinity)), seed, n_sessions
    )

    print(f'{"Policy":<20}{"Mean reward":>15}')
    print(f'{"Random baseline":<20}{random_avg:>15.4f}')
    print(f'{"Trained bandit":<20}{trained_avg:>15.4f}')
    print(f'{"Oracle (upper bound)":<20}{oracle_avg:>15.4f}')
    lift = (trained_avg - random_avg) / (oracle_avg - random_avg) * 100 if oracle_avg != random_avg else 0
    print(f'\nBandit captures {lift:.1f}% of the achievable gain over random.')


if __name__ == '__main__':
    main()
