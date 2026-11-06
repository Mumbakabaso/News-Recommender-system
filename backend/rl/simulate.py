"""
Synthetic interaction / user simulator.

The dissertation's own methodology chapter flags that real-time,
large-scale interaction data isn't available for this project, so a
simulated population of users is used to bootstrap and train the bandit
(and to smoke-test the whole pipeline before any real user has clicked
anything). Each simulated user has a hidden Dirichlet-sampled affinity
over categories; click probability for a served category is driven by
that affinity, and reward blends the click with a simulated dwell time.

This module is used two ways:
  1. rl/train.py imports `make_user_sampler` to drive the Gym env
     during training.
  2. scripts/seed_synthetic_data.py imports `simulate_session` directly to
     write believable rows into the real Postgres `interactions` table,
     so the analytics dashboard and the API have something to show before
     real traffic exists.
"""
from __future__ import annotations
import numpy as np
from rl.features import build_context, FEATURES_PER_ARM


class SyntheticUser:
    def __init__(self, categories, rng):
        self.categories = categories
        self.rng = rng
        # Hidden ground-truth preference the bandit is trying to learn.
        self.affinity = rng.dirichlet(np.ones(len(categories)) * 0.6)
        self.impressions = np.zeros(len(categories))
        self.clicks = np.zeros(len(categories))
        self.reward_sum = np.zeros(len(categories))
        self.history = []  # list of category indices, most recent last

    def click_probability(self, action_idx):
        base = self.affinity[action_idx]
        # Scale into a realistic CTR range (~2%-35%) instead of a raw
        # simplex weight, and add a little observation noise.
        p = 0.02 + base * 0.9
        return float(np.clip(p + self.rng.normal(0, 0.03), 0.0, 0.95))

    def observe_context(self, global_ctrs):
        stats = []
        for i, _ in enumerate(self.categories):
            recent = self.history[-10:]
            recency_frac = (recent.count(i) / len(recent)) if recent else 0.0
            stats.append({
                'user_clicks': self.clicks[i],
                'user_impressions': self.impressions[i],
                'user_reward_sum': self.reward_sum[i],
                'user_interactions': self.impressions[i],
                'global_ctr': global_ctrs[i],
                'recency_frac': recency_frac,
            })
        return build_context(stats)

    def pull(self, action_idx):
        p_click = self.click_probability(action_idx)
        clicked = self.rng.random() < p_click
        dwell = float(self.rng.gamma(2.0, 30.0)) if clicked else 0.0  # seconds
        reward = (1.0 if clicked else 0.0) + min(dwell / 120.0, 1.0) * 0.5

        self.impressions[action_idx] += 1
        if clicked:
            self.clicks[action_idx] += 1
        self.reward_sum[action_idx] += reward
        self.history.append(action_idx)
        return reward, clicked, dwell


class _Session:
    """Adapts a SyntheticUser to the env's observe()/pull() session contract,
    tracking one simulated user across a whole multi-round browsing session."""

    def __init__(self, categories, rng, global_ctrs):
        self.user = SyntheticUser(categories, rng)
        self.global_ctrs = global_ctrs

    def observe(self):
        return self.user.observe_context(self.global_ctrs)

    def pull(self, action_idx):
        reward, _clicked, _dwell = self.user.pull(action_idx)
        return reward


def make_user_sampler(categories, seed=None, global_ctrs=None):
    """Returns a zero-arg callable suitable for NewsRecommenderEnv(user_sampler=...).
    Each call produces a fresh simulated user whose hidden affinity persists
    for the whole session (multiple env steps) that follows."""
    rng = np.random.default_rng(seed)
    if global_ctrs is None:
        global_ctrs = [0.08] * len(categories)

    def sampler():
        return _Session(categories, rng, global_ctrs)

    return sampler


def simulate_session(categories, rng, global_ctrs, n_impressions=15):
    """
    Simulates one synthetic user's whole browsing session (used for
    seeding the real database, not for training). Returns a list of dict
    events: {category_idx, clicked, dwell_seconds, reward}.
    """
    user = SyntheticUser(categories, rng)
    events = []
    for _ in range(n_impressions):
        # Session-seeding uses a simple popularity+affinity mix rather than
        # the trained policy, so it doesn't just reproduce whatever the
        # model already believes.
        weights = 0.5 * user.affinity + 0.5 * np.array(global_ctrs) / sum(global_ctrs)
        action_idx = rng.choice(len(categories), p=weights / weights.sum())
        reward, clicked, dwell = user.pull(action_idx)
        events.append({
            'category_idx': int(action_idx),
            'clicked': clicked,
            'dwell_seconds': dwell,
            'reward': reward,
        })
    return events
