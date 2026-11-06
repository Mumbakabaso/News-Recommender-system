"""
Keeps the news fresh while the API is running: a daemon thread that runs the
ingestion pipeline once at startup and then every NEWS_REFRESH_MINUTES.

A plain thread rather than Celery/APScheduler on purpose — for a single
local server it does the job with zero extra infrastructure. (If the app is
ever run with several gunicorn workers, set NEWS_AUTO_REFRESH=false and run
`flask ingest-news` from a cron job / scheduled task instead, so the feeds
aren't fetched once per worker.)
"""
from __future__ import annotations
import os
import sys
import threading
import time

_started = False


def launched_with_flask_run() -> bool:
    """
    True when this process is the real web server started by `flask run`
    (or `python -m flask run`).

    `flask run` never executes run.py's `if __name__ == '__main__'` block, so
    without this the refresher silently never started and the feed only got
    new articles when `flask ingest-news` was run by hand. Other CLI commands
    (`flask db upgrade`, `flask ingest-news`, ...) must NOT start it.
    """
    argv = sys.argv
    if len(argv) < 2 or argv[1] != 'run' or 'flask' not in os.path.basename(argv[0]).lower() + argv[0].lower():
        return False
    # With the debug reloader, Flask runs a watcher process plus the real
    # server (which has WERKZEUG_RUN_MAIN=true). Only start in the real one.
    reloader = ('--debug' in argv or '--reload' in argv
                or os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes')) \
        and '--no-reload' not in argv
    return (not reloader) or os.environ.get('WERKZEUG_RUN_MAIN') == 'true'


def start_news_scheduler(app):
    global _started
    if _started or not app.config.get('NEWS_AUTO_REFRESH', True):
        return
    _started = True
    interval = max(int(app.config.get('NEWS_REFRESH_MINUTES', 30)), 5) * 60

    def loop():
        from app.services.news_ingestion import run_ingestion
        while True:
            with app.app_context():
                try:
                    result = run_ingestion(app.config)
                    if not result.get('skipped'):
                        ok = sum(1 for s in result['sources'].values() if s['ok'])
                        print(f"[news_scheduler] refreshed: {result['total_saved']} articles from "
                              f"{ok}/{len(result['sources'])} sources"
                              + (' (mock fallback)' if result['used_mock'] else ''))
                    if app.config.get('PEOPLE_AUTO_UPDATE', True):
                        try:
                            from app.services.people.updater import run_people_update
                            r = run_people_update()
                            print(f"[news_scheduler] people: {r['scan']['articles']} articles scanned, "
                                  f"{r['scan']['mentions']} mentions, {r['developments_added']} new developments, "
                                  f"{r['profiles_rebuilt']} profiles rebuilt")
                        except Exception as e:
                            from app.extensions import db
                            db.session.rollback()
                            print(f'[news_scheduler] people update failed: {e}')
                    top = int(app.config.get('SUMMARY_PREWARM_TRENDING', 0) or 0)
                    if top > 0:
                        from app.services.summarizer import prewarm_trending
                        n = prewarm_trending(app, top)
                        if n:
                            print(f'[news_scheduler] summaries ready for {n} trending stories')
                except Exception as e:
                    print(f'[news_scheduler] refresh failed: {e}')
            time.sleep(interval)

    threading.Thread(target=loop, name='news-scheduler', daemon=True).start()
    print(f'[news_scheduler] auto-refresh on: every {interval // 60} min')
