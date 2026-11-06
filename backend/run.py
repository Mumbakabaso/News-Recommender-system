import os

from app import create_app
from app.services.scheduler import start_news_scheduler

app = create_app()

if __name__ == '__main__':
    debug = os.environ.get('FLASK_DEBUG', '1') == '1'
    # With the debug reloader on, Flask runs this file twice (a watcher
    # process + the real server); only start the news refresher in the real
    # server so feeds aren't fetched twice.
    if not debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        start_news_scheduler(app)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=debug)
