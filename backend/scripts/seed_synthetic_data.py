"""
Populates the real Postgres `interactions` (and `recommendation_logs`)
tables with believable synthetic sessions, using the same SyntheticUser
model rl/train.py trains against. This exists so the admin analytics
dashboard and the recommendation feed have realistic-looking history
before any real visitor has used the site — expected, per the
dissertation, given real interaction data at this scale isn't available.

Run via `flask seed-synthetic-interactions` (registered in app/__init__.py)
or `python -m scripts.seed_synthetic_data` directly.
"""
from __future__ import annotations
import random
import numpy as np
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models.article import Article
from app.models.interaction import Interaction
from app.models.recommendation_log import RecommendationLog
from rl.simulate import simulate_session


def run(app, n_synthetic_users: int = 40, seed: int = 2024):
    with app.app_context():
        categories = app.config['NEWS_CATEGORIES']
        rng = np.random.default_rng(seed)

        articles_by_category = {
            c: Article.query.filter_by(category=c).all() for c in categories
        }
        missing = [c for c, a in articles_by_category.items() if not a]
        if missing:
            print(f'No articles found for categories {missing} — run `flask ingest-news` first.')
            return

        global_ctrs = [0.08] * len(categories)
        now = datetime.now(timezone.utc)

        total_events = 0
        for u in range(n_synthetic_users):
            events = simulate_session(categories, rng, global_ctrs, n_impressions=rng.integers(8, 25))
            session_time = now - timedelta(days=int(rng.integers(0, 13)), hours=int(rng.integers(0, 23)))
            anon_id = f'synthetic_{seed}_{u}'

            for i, event in enumerate(events):
                category = categories[event['category_idx']]
                article = random.choice(articles_by_category[category])
                event_time = session_time + timedelta(seconds=i * 15)

                article.impressions = (article.impressions or 0) + 1
                db.session.add(RecommendationLog(
                    anon_id=anon_id, article_id=article.id, category=category,
                    score=0.5, position=i, created_at=event_time,
                ))
                db.session.add(Interaction(
                    anon_id=anon_id, article_id=article.id, event_type='impression',
                    position=i, reward=0.0, created_at=event_time,
                ))
                total_events += 1

                if event['clicked']:
                    article.clicks = (article.clicks or 0) + 1
                    db.session.add(Interaction(
                        anon_id=anon_id, article_id=article.id, event_type='click',
                        position=i, reward=1.0, created_at=event_time + timedelta(seconds=1),
                    ))
                    total_events += 1
                    if event['dwell_seconds'] > 0:
                        article.total_dwell_seconds = (article.total_dwell_seconds or 0) + int(event['dwell_seconds'])
                        db.session.add(Interaction(
                            anon_id=anon_id, article_id=article.id, event_type='read',
                            dwell_seconds=int(event['dwell_seconds']), position=i,
                            reward=min(event['dwell_seconds'] / 120.0, 1.0) * 0.5,
                            created_at=event_time + timedelta(seconds=int(event['dwell_seconds']) + 1),
                        ))
                        total_events += 1

        db.session.commit()
        print(f'Seeded {n_synthetic_users} synthetic sessions ({total_events} interaction rows).')


if __name__ == '__main__':
    from app import create_app
    run(create_app())
