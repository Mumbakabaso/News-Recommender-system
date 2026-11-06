"""
Shared feature schema between training (simulated users) and serving (real
users from Postgres) — training a policy on one feature layout and serving
it with a different one would silently break the bandit, so both
rl/simulate.py and app/services/recommender.py build their context vectors
through this module.
"""
from __future__ import annotations
import numpy as np

FEATURES_PER_ARM = 4  # keep in sync with rl/env.py


def laplace_ctr(clicks: float, impressions: float, prior: float = 0.1, prior_weight: float = 2.0) -> float:
    """Smoothed CTR so a category with 0 impressions doesn't read as CTR=0."""
    return (clicks + prior * prior_weight) / (impressions + prior_weight)


def build_context(per_category_stats: list[dict]) -> np.ndarray:
    """
    per_category_stats: one dict per category, in the SAME order as the
    categories list used everywhere else, each with keys:
      user_clicks, user_impressions, user_reward_sum, user_interactions,
      global_ctr, recency_frac
    Returns shape (num_categories, FEATURES_PER_ARM) float32 array, each
    row in [0, 1]-ish range (bandit training is far more stable on
    normalized features).
    """
    rows = []
    for s in per_category_stats:
        user_ctr = laplace_ctr(s.get('user_clicks', 0), s.get('user_impressions', 0))
        interactions = max(s.get('user_interactions', 0), 1)
        # Clamped to [0, 1]: dislikes can push a category's reward sum below
        # zero at serving time, but the policy was trained on [0, 1] values.
        avg_reward = min(max(s.get('user_reward_sum', 0.0) / interactions, 0.0), 1.0)
        global_ctr = min(max(s.get('global_ctr', 0.05), 0.0), 1.0)
        recency = min(max(s.get('recency_frac', 0.0), 0.0), 1.0)
        rows.append([user_ctr, avg_reward, global_ctr, recency])
    return np.array(rows, dtype=np.float32)
