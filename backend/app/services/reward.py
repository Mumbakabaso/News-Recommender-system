"""
Turns a raw logged event (click / read+dwell) into the scalar reward the
bandit is trained to maximize. Kept identical in shape to the reward used
in rl/simulate.py's SyntheticUser.pull so real and simulated rewards are
on the same scale: 1.0 for a click, plus up to +0.5 more for dwell time,
capped at 2 minutes of reading.
"""
from __future__ import annotations


def compute_reward(event_type: str, dwell_seconds: int = 0) -> float:
    if event_type == 'click':
        return 1.0
    if event_type == 'read':
        return min(dwell_seconds / 120.0, 1.0) * 0.5
    return 0.0  # 'impression' carries no reward on its own
