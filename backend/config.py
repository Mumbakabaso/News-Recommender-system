import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _database_url():
    url = os.environ.get('DATABASE_URL', 'postgresql://newsrec:newsrec@localhost:5432/newsrec')
    # Pin the psycopg2 driver (it's what requirements.txt installs). Newer
    # SQLAlchemy versions default plain 'postgresql://' to psycopg v3, and
    # some hosts hand out the old 'postgres://' scheme.
    for prefix in ('postgres://', 'postgresql://'):
        if url.startswith(prefix):
            return 'postgresql+psycopg2://' + url[len(prefix):]
    return url


class Config:
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'dev-secret-change-me')
    JWT_ACCESS_TOKEN_EXPIRES = 60 * 60 * 24 * 7  # 7 days, fine for a prototype

    NEWSAPI_KEY = os.environ.get('NEWSAPI_KEY', '').strip()
    NEWS_CATEGORIES = [
        c.strip()
        for c in os.environ.get(
            'NEWS_CATEGORIES', 'politics,economics,technology,global-affairs,sports,health'
        ).split(',')
        if c.strip()
    ]

    # --- Live news ingestion (see app/services/news_sources.py) ---
    # Background refresh while the API is running (python run.py).
    NEWS_AUTO_REFRESH = os.environ.get('NEWS_AUTO_REFRESH', 'true').lower() in ('1', 'true', 'yes')
    NEWS_REFRESH_MINUTES = int(os.environ.get('NEWS_REFRESH_MINUTES', '30'))
    # Skip feed items older than this many days.
    NEWS_MAX_AGE_DAYS = int(os.environ.get('NEWS_MAX_AGE_DAYS', '7'))
    # For feeds without thumbnails (Al Jazeera, most Zambian sites), how many
    # new articles per source per run get their og:image looked up.
    NEWS_IMAGE_LOOKUPS_PER_SOURCE = int(os.environ.get('NEWS_IMAGE_LOOKUPS_PER_SOURCE', '8'))
    # Comma-separated source keys to switch off, e.g. "znbc,cnn".
    NEWS_DISABLED_SOURCES = [
        s.strip() for s in os.environ.get('NEWS_DISABLED_SOURCES', '').split(',') if s.strip()
    ]

    # --- Smart summaries (see app/services/summarizer.py) ---
    # With a Gemini key, summaries are written by Google's Gemini; without
    # one (or if it fails) the built-in offline summariser is used.
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '').strip()
    GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-3.5-flash').strip()
    # After each news refresh, write summaries for the top N trending
    # stories in advance so they open instantly (0 = off).
    SUMMARY_PREWARM_TRENDING = int(os.environ.get('SUMMARY_PREWARM_TRENDING', '5'))

    # --- AI People Profiles (see app/services/people/) ---
    # After each news refresh: find people in new articles, refresh their
    # latest news and rebuild stale profiles.
    PEOPLE_AUTO_UPDATE = os.environ.get('PEOPLE_AUTO_UPDATE', 'true').lower() in ('1', 'true', 'yes')

    # Allowed frontend origins for the API ('*' is fine for local use).
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*')

    RL_MODEL_PATH = os.environ.get('RL_MODEL_PATH', os.path.join(BASE_DIR, 'rl', 'artifacts', 'bandit_policy.zip'))
