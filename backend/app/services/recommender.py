"""
Bridges the trained bandit (rl/policy.py) to real articles in Postgres.

Flow for GET /api/recommendations:
  1. Build this user's (or anon visitor's) per-category context from their
     Interaction history + population-level stats -> rl.features.build_context
     (for logged-in users, interests picked at onboarding are folded in as
     pseudo-observations — see INTEREST_PSEUDO_* below)
  2. Ask the bandit to score each category                -> rl.policy.score_categories
     then blend in the user's stated interests as a prior whose weight
     decays as real engagement accumulates             -> _blend_interest_prior
  3. Within each category, rank candidate articles by freshness +
     popularity - "already shown to you" fatigue; articles the reader has
     already clicked/read or disliked are never served again
  4. Slots a category can't fill (common with ?region=zambia) go to the
     reader's interest categories first, then the categories are
     interleaved down the feed in proportion to their score
  5. Log every surfaced article as a RecommendationLog row + an
     'impression' Interaction, which is what closes the feedback loop the
     next time this same user is scored.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy import func, case

from app.extensions import db
from app.models.article import Article
from app.models.interaction import Interaction
from app.models.recommendation_log import RecommendationLog
from rl.features import build_context
from rl.policy import score_categories
from app.services.feedback import per_category_counts, disliked_article_ids

# The trained policy converges toward near-deterministic category
# preference for any two users who present the *same* context (a real
# risk for cold-start users, who all start from an identical all-zero
# context) — without a exploration floor, that collapses the whole feed
# to one category and a brand-new visitor never even samples the others
# to build a real preference signal. Blending in a uniform floor is the
# standard epsilon-greedy fix for this in the bandit literature; it's
# applied only at serving time so training/evaluation (rl/train.py,
# rl/evaluate.py) still measure the raw policy.
EXPLORATION_EPSILON = 0.15

# --- Explicit-interest cold start (onboarding) ------------------------------
# A brand-new account has no interaction history, so the bandit only sees the
# shared all-zero cold-start context. Interests the user picked at onboarding
# are used two ways to fix that:
#
#  (a) Pseudo-observations in the context vector: each chosen category starts
#      as if the user had already been shown it INTEREST_PSEUDO_IMPRESSIONS
#      times and clicked INTEREST_PSEUDO_CLICKS of them. It's the same idea as
#      an informative Beta prior in Thompson sampling. The policy itself then
#      sees a personalised context on round one, without retraining or
#      changing the feature schema. Real impressions add to the denominator, so
#      the pseudo-counts get diluted naturally.
#
#  (b) A serving-time prior blend: score = w * interest_prior + (1 - w) * policy,
#      where interest_prior is uniform over the chosen categories and
#      w = K / (K + n), with n = the user's real engagement events (clicks +
#      reads). On day one (n = 0) the feed is driven by stated interests. As
#      the user clicks and reads, w -> 0 and the learned bandit takes over, so
#      behaviour can override what the user said they wanted.
#
#  DISCOVERY_SLOTS keeps a couple of non-interest categories in every feed so
#  the bandit still gets signal on them (otherwise a stated interest list
#  becomes a filter bubble the system can never learn its way out of).
INTEREST_PSEUDO_IMPRESSIONS = 2
INTEREST_PSEUDO_CLICKS = 1
INTEREST_PSEUDO_REWARD = 1.0
INTEREST_PRIOR_STRENGTH = 10  # K: engagement events until the prior weight halves
# The prior never fades below this: stated interests keep steering the feed
# even after lots of clicks, so a policy that has drifted onto one category
# (e.g. Zambian politics, because that's most of what local outlets publish)
# can't override what the reader asked for. Editing interests is how a
# reader changes this.
INTEREST_PRIOR_FLOOR = 0.4
# At least this share of a signed-in reader's feed comes from the topics they
# chose (when there are stories for them); the rest is discovery.
INTEREST_MIN_SHARE = 0.65
DISCOVERY_SLOTS = 2

# --- Article selection within a category ------------------------------------
DEFAULT_WINDOW_DAYS = 14
REGION_WINDOW_DAYS = 45      # local outlets publish few non-politics stories
FRESHNESS_HALF_LIFE_HOURS = 36
POPULARITY_WEIGHT = 0.5
FATIGUE_PENALTY = 0.35       # per previous showing to this reader...
FATIGUE_WINDOW_HOURS = 72    # ...counted over the last 3 days

# --- Explicit likes / dislikes ----------------------------------------------
# A thumbs up/down is a clearer signal than a click, so each one counts for
# more than a single implicit event when it's folded into the bandit context:
#   like    -> as if the reader was shown the category LIKE_WEIGHT times and
#              clicked every time, with LIKE_REWARD reward per like
#   dislike -> as if shown DISLIKE_WEIGHT times with no click, and
#              DISLIKE_PENALTY subtracted from the category's reward sum
# This moves the same four context features the policy was trained on (CTR,
# average reward...), so explicit feedback steers the trained policy without
# retraining or changing the feature schema. Disliked articles are also
# never served to that reader again.
LIKE_WEIGHT = 2
LIKE_REWARD = 1.0
DISLIKE_WEIGHT = 2
DISLIKE_PENALTY = 1.0


def _global_ctr_by_category(categories: list[str]) -> dict:
    rows = (
        db.session.query(
            Article.category,
            func.coalesce(func.sum(Article.clicks), 0),
            func.coalesce(func.sum(Article.impressions), 0),
        )
        .group_by(Article.category)
        .all()
    )
    stats = {c: (0, 0) for c in categories}
    for category, clicks, impressions in rows:
        stats[category] = (clicks, impressions)

    result = {}
    for c in categories:
        clicks, impressions = stats.get(c, (0, 0))
        result[c] = (clicks + 0.2) / (impressions + 2.0)  # Laplace-smoothed prior
    return result


def _user_context(identity_filter, categories: list[str], interests: list[str] | None = None,
                  feedback: dict | None = None) -> np.ndarray:
    global_ctrs = _global_ctr_by_category(categories)

    rows = (
        db.session.query(
            Article.category,
            func.count(Interaction.id),
            func.sum(case((Interaction.event_type == 'click', 1), else_=0)),
            func.coalesce(func.sum(Interaction.reward), 0.0),
        )
        .join(Article, Article.id == Interaction.article_id)
        .filter(identity_filter)
        .group_by(Article.category)
        .all()
    )
    per_cat = {c: {'impressions': 0, 'clicks': 0, 'reward_sum': 0.0} for c in categories}
    for category, n, clicks, reward_sum in rows:
        if category in per_cat:
            per_cat[category] = {
                'impressions': n or 0,
                'clicks': clicks or 0,
                'reward_sum': float(reward_sum or 0.0),
            }

    recent = (
        db.session.query(Article.category)
        .join(Interaction, Interaction.article_id == Article.id)
        .filter(identity_filter)
        .order_by(Interaction.created_at.desc())
        .limit(10)
        .all()
    )
    recent_categories = [r[0] for r in recent]

    interests = [c for c in (interests or []) if c in per_cat]
    for c in interests:
        per_cat[c]['impressions'] += INTEREST_PSEUDO_IMPRESSIONS
        per_cat[c]['clicks'] += INTEREST_PSEUDO_CLICKS
        per_cat[c]['reward_sum'] += INTEREST_PSEUDO_REWARD
    if not recent_categories and interests:
        # No real history yet: let the stated interests stand in for "what
        # this user has been reading recently".
        recent_categories = list(interests)

    for c, fb in (feedback or {}).items():
        if c not in per_cat:
            continue
        likes, dislikes = fb.get('likes', 0), fb.get('dislikes', 0)
        per_cat[c]['impressions'] += LIKE_WEIGHT * likes + DISLIKE_WEIGHT * dislikes
        per_cat[c]['clicks'] += LIKE_WEIGHT * likes
        per_cat[c]['reward_sum'] += LIKE_REWARD * likes - DISLIKE_PENALTY * dislikes

    stats = []
    for c in categories:
        s = per_cat[c]
        recency_frac = (recent_categories.count(c) / len(recent_categories)) if recent_categories else 0.0
        stats.append({
            'user_clicks': s['clicks'],
            'user_impressions': s['impressions'],
            'user_reward_sum': s['reward_sum'],
            'user_interactions': s['impressions'],
            'global_ctr': global_ctrs.get(c, 0.05),
            'recency_frac': recency_frac,
        })
    return build_context(stats)


def _engagement_count(identity_filter) -> int:
    return (
        db.session.query(func.count(Interaction.id))
        .filter(identity_filter, Interaction.event_type.in_(['click', 'read']))
        .scalar()
        or 0
    )


def _blend_interest_prior(policy_scores: np.ndarray, categories: list[str], interests: list[str], n_engaged: int):
    """Returns (blended_scores, prior_weight). See (b) in the comment at the top."""
    if not interests:
        return policy_scores, 0.0
    prior = np.array([1.0 if c in interests else 0.0 for c in categories])
    prior /= prior.sum()
    w = max(INTEREST_PRIOR_FLOOR, INTEREST_PRIOR_STRENGTH / (INTEREST_PRIOR_STRENGTH + n_engaged))
    return w * prior + (1 - w) * policy_scores, w


def _share(weights: np.ndarray, n: int, floor_each: int = 0) -> np.ndarray:
    """Split n slots by weight (largest-remainder), giving each entry floor_each first when n allows."""
    k = len(weights)
    out = np.zeros(k, dtype=int)
    if k == 0 or n <= 0:
        return out
    if floor_each and n >= floor_each * k:
        out[:] = floor_each
    remaining = n - int(out.sum())
    w = np.asarray(weights, dtype=float)
    w = w / w.sum() if w.sum() > 0 else np.ones(k) / k
    raw = w * remaining
    out += np.floor(raw).astype(int)
    leftover = n - int(out.sum())
    if leftover > 0:
        out[np.argsort(-(raw - np.floor(raw)))[:leftover]] += 1
    return out


def _allocate_slots(category_scores: np.ndarray, categories: list[str], count: int, interests: list[str]) -> np.ndarray:
    """
    How many feed slots each category gets.

      - No interests (anonymous visitor): 1 slot per category, the rest in
        proportion to category_scores. A dominant policy score can't blank
        every other category out of the feed, and the bandit keeps getting
        signal on the categories it's unsure about.
      - With interests: the feed is split into an "interests" part and a
        "discovery" part. The interests part is the interest categories'
        share of the score, but never less than INTEREST_MIN_SHARE of the
        feed and never so much that fewer than DISCOVERY_SLOTS are left for
        other topics. Inside each part slots go by score, so the bandit
        still decides *which* of your interests (and which other topics)
        get more room, based on what you actually click, read and like.
    """
    num_categories = len(categories)
    interest_idx = [i for i, c in enumerate(categories) if c in interests]
    other_idx = [i for i in range(num_categories) if i not in interest_idx]

    if not interest_idx:
        return _share(category_scores, count, floor_each=1 if count >= num_categories else 0)

    # tiny feeds (count < 6) give every slot to interests
    n_discovery_min = min(DISCOVERY_SLOTS, len(other_idx), count // 3)
    interest_mass = float(category_scores[interest_idx].sum())
    n_interest = max(int(round(count * interest_mass)), int(np.ceil(count * INTEREST_MIN_SHARE)))
    n_interest = min(n_interest, count - n_discovery_min)

    slots = np.zeros(num_categories, dtype=int)
    slots[interest_idx] = _share(category_scores[interest_idx], n_interest, floor_each=1)
    if other_idx:
        # discovery: the best-scoring other topics get the slots first
        order = sorted(other_idx, key=lambda i: -category_scores[i])
        disc = _share(category_scores[order], count - n_interest)
        if n_discovery_min and (disc > 0).sum() < n_discovery_min:
            disc = _share(np.ones(len(order)), 0)
            disc[:n_discovery_min] = 1
            rest = count - n_interest - n_discovery_min
            disc += _share(category_scores[order], rest)
        slots[order] = disc
    return slots


def _seen_by_user(identity_filter, since: datetime) -> tuple[set[int], dict[int, int]]:
    """
    (engaged, shown):
      engaged = articles this reader already clicked or read (never re-served:
                a news feed shouldn't hand you a story you've just finished)
      shown   = {article_id: times it was put in front of them since `since`}
                (used as a "fatigue" penalty so a refresh rotates in new
                stories instead of serving the same twelve again)
    """
    engaged = {
        a for (a,) in db.session.query(Interaction.article_id)
        .filter(identity_filter, Interaction.event_type.in_(['click', 'read']))
        .distinct().all()
    }
    shown = dict(
        db.session.query(Interaction.article_id, func.count(Interaction.id))
        .filter(identity_filter, Interaction.event_type == 'impression', Interaction.created_at >= since)
        .group_by(Interaction.article_id)
        .all()
    )
    return engaged, shown


def _article_rank(article: Article, now: datetime, shown: dict[int, int]) -> float:
    """
    Order of articles *within* a category (the bandit picks the category
    mix; this picks which stories fill those slots):
      freshness  half-life of FRESHNESS_HALF_LIFE_HOURS — news is perishable
      popularity smoothed CTR, so a story others clicked gets a nudge
      fatigue    minus FATIGUE_PENALTY per time this reader was already shown it
    """
    published = article.published_at
    if published is not None and published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    age_h = max((now - published).total_seconds() / 3600.0, 0.0) if published else 24.0 * 7
    freshness = 0.5 ** (age_h / FRESHNESS_HALF_LIFE_HOURS)
    popularity = ((article.clicks or 0) + 0.1) / ((article.impressions or 0) + 5.0)
    fatigue = FATIGUE_PENALTY * min(shown.get(article.id, 0), 4)
    return freshness + POPULARITY_WEIGHT * popularity - fatigue


def _interleave(picked: dict[str, list], score_of: dict[str, float]) -> list:
    """
    Mix categories through the feed in proportion to their score (a smooth
    weighted round-robin) instead of showing them in blocks: the top story
    comes from the highest-scoring category, and every category's stories
    are spread down the page.
    """
    queues = {c: list(items) for c, items in picked.items() if items}
    taken = {c: 0 for c in queues}
    out = []
    while queues:
        c = max(queues, key=lambda k: score_of.get(k, 0.0) / (1 + taken[k]))
        out.append((queues[c].pop(0), score_of.get(c, 0.0)))
        taken[c] += 1
        if not queues[c]:
            del queues[c]
    return out


def get_recommendations(categories: list[str], model_path: str, user_id=None, anon_id=None, count: int = 10,
                        interests: list[str] | None = None, region: str | None = None):
    if user_id is not None:
        identity_filter = Interaction.user_id == user_id
    elif anon_id:
        identity_filter = Interaction.anon_id == anon_id
    else:
        identity_filter = Interaction.id.is_(None)  # matches nothing -> cold-start context

    interests = [c for c in (interests or []) if c in categories]

    feedback = per_category_counts(user_id) if user_id is not None else {}
    n_explicit = sum(f['likes'] + f['dislikes'] for f in feedback.values())

    context = _user_context(identity_filter, categories, interests, feedback)
    policy_scores = score_categories(context, model_path)
    blended, _prior_weight = _blend_interest_prior(
        policy_scores, categories, interests,
        (_engagement_count(identity_filter) + n_explicit) if interests else 0
    )
    uniform = np.ones_like(blended) / len(blended)
    category_scores = (1 - EXPLORATION_EPSILON) * blended + EXPLORATION_EPSILON * uniform
    score_of = {c: float(category_scores[i]) for i, c in enumerate(categories)}

    slots = _allocate_slots(category_scores, categories, count, interests)

    now = datetime.now(timezone.utc)
    engaged, shown = _seen_by_user(identity_filter, now - timedelta(hours=FATIGUE_WINDOW_HOURS))
    excluded = set(engaged)
    if user_id is not None:
        excluded |= disliked_article_ids(user_id)

    # Local (Zambian) outlets publish far fewer sports / health / tech
    # stories than international ones, so a 14-day window can leave a
    # reader's interest categories empty and their slots get handed to
    # whatever is newest (nearly always politics). With a region filter the
    # window is wider; the freshness term in _article_rank still puts
    # today's news first.
    window_days = REGION_WINDOW_DAYS if region else DEFAULT_WINDOW_DAYS
    base_query = Article.query.filter(Article.published_at >= now - timedelta(days=window_days))
    if region:
        base_query = base_query.filter(Article.region == region)
    if excluded:
        base_query = base_query.filter(~Article.id.in_(excluded))

    # Candidate pool per category, best-first.
    pools = {}
    for idx, category in enumerate(categories):
        want = max(int(slots[idx]), 0)
        cands = (
            base_query.filter(Article.category == category)
            .order_by(Article.published_at.desc())
            .limit(max(want, 2) * 4 + 8)
            .all()
        )
        cands.sort(key=lambda a: _article_rank(a, now, shown), reverse=True)
        pools[category] = cands

    # 1) each category takes up to its allocated slots
    picked = {c: [] for c in categories}
    for idx, c in enumerate(categories):
        n = int(slots[idx])
        picked[c], pools[c] = pools[c][:n], pools[c][n:]

    # 2) slots a category couldn't fill (too few stories in this region)
    #    go to the reader's interest categories first, then the rest, both
    #    in bandit-score order — not simply to the newest stories overall.
    shortfall = count - sum(len(v) for v in picked.values())
    refill_order = sorted(categories, key=lambda c: (c in interests, score_of[c]), reverse=True)
    while shortfall > 0 and any(pools[c] for c in refill_order):
        for c in refill_order:
            if shortfall <= 0:
                break
            if pools[c]:
                picked[c].append(pools[c].pop(0))
                shortfall -= 1

    selected = _interleave(picked, score_of)

    # Log each surfaced article as both a recommendation-log row and an
    # implicit 'impression' interaction (zero reward unless later clicked).
    results = []
    for position, (article, score) in enumerate(selected[:count]):
        article.impressions = (article.impressions or 0) + 1
        db.session.add(RecommendationLog(
            user_id=user_id, anon_id=anon_id, article_id=article.id,
            category=article.category, score=score, position=position,
        ))
        db.session.add(Interaction(
            user_id=user_id, anon_id=anon_id, article_id=article.id,
            event_type='impression', position=position, reward=0.0,
        ))
        results.append(article.to_dict(score=score))
    db.session.commit()
    return results
