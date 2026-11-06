"""
Continuous updates for people profiles. Runs after every news refresh
(scheduler.py) and from the CLI (`flask people-refresh`).

Each run:
  1. scans newly ingested articles for people (linker.scan_pending), so new
     articles mentioning existing profiles are associated with the right
     person and new public figures are identified;
  2. refreshes Latest Developments for people mentioned recently whose news
     is older than 6 hours (deduplicated: items already captured are skipped);
  3. rebuilds a few stale profiles (older than 7 days, or never built) for
     the most-mentioned people, which also re-checks their positions on
     Wikidata: a position that has ended is marked historical and the
     headline changes to "Former ...", with the date the change was seen.

Work per run is capped so one refresh never hammers Wikidata/Google or
blocks the scheduler for long.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models.person import Person
from app.services.people.linker import scan_pending
from app.services.people.developments import refresh_developments
from app.services.people.profile_builder import build_profile, needs_rebuild, DEVELOPMENTS_MAX_AGE


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def run_people_update(scan_limit: int = 150, lookup_limit: int = 25, news_limit: int = 10,
                      rebuild_limit: int = 3) -> dict:
    out = {'scan': scan_pending(limit=scan_limit, lookup_limit=lookup_limit)}

    recent = _now() - timedelta(days=3)
    stale_news = _now() - DEVELOPMENTS_MAX_AGE
    people = (Person.query.filter(Person.last_mentioned_at >= recent)
              .filter((Person.developments_updated_at.is_(None)) | (Person.developments_updated_at < stale_news))
              .order_by(Person.mention_count.desc()).limit(news_limit).all())
    added = 0
    for p in people:
        try:
            added += refresh_developments(p)['added']
        except Exception as e:
            db.session.rollback()
            print(f'[people.updater] news refresh failed for {p.full_name}: {e}')
    out['developments_added'] = added
    out['news_refreshed'] = len(people)

    rebuilt = 0
    candidates = (Person.query.filter(Person.mention_count > 0)
                  .order_by(Person.last_mentioned_at.desc().nullslast(), Person.mention_count.desc())
                  .limit(rebuild_limit * 10).all())
    for p in candidates:
        if rebuilt >= rebuild_limit:
            break
        if needs_rebuild(p):
            try:
                build_profile(p, refresh_news=False)
                rebuilt += 1
            except Exception as e:
                db.session.rollback()
                print(f'[people.updater] profile rebuild failed for {p.full_name}: {e}')
    out['profiles_rebuilt'] = rebuilt
    return out
