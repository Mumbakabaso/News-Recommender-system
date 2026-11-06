"""
Registry of the live news sources the ingestion pipeline pulls from.

Two kinds of source:
  - 'rss'     : a public RSS/Atom feed. Free, no API key, and what most
                publishers (BBC, Al Jazeera, every Zambian outlet below)
                officially offer for syndication.
  - 'newsapi' : NewsAPI.org's /v2/top-headlines?sources=<id>. Used for CNN,
                which stopped updating its public RSS feeds in 2023-24, so
                there is no feed left to read. Needs NEWSAPI_KEY (the free
                developer key is fine for running the project locally).

Each source has:
  key              unique id, used in the API (?source=bbc-world) and in the DB
  name             display name shown on article cards
  region           'international' or 'zambia' — drives the region filter
  kind             'rss' | 'newsapi'
  url / newsapi_id where to fetch from
  category         fixed topic for single-topic feeds (e.g. BBC Technology);
                   None means "work it out per article" via categoriser.py
  default_category what a general feed falls back to when no topic keyword
                   matches

Only headline, summary, link, image and date are stored — the article card
links out to the publisher for the full story, which is how feed readers and
aggregators are expected to use these feeds.

To add a source, append a dict here. To switch one off without editing
code, list its key in NEWS_DISABLED_SOURCES in backend/.env.
"""

SOURCES = [
    # --- International -----------------------------------------------------
    {
        'key': 'bbc-world', 'name': 'BBC News', 'region': 'international', 'kind': 'rss',
        'url': 'https://feeds.bbci.co.uk/news/world/rss.xml',
        'category': None, 'default_category': 'global-affairs',
    },
    {
        'key': 'bbc-africa', 'name': 'BBC News Africa', 'region': 'international', 'kind': 'rss',
        'url': 'https://feeds.bbci.co.uk/news/world/africa/rss.xml',
        'category': None, 'default_category': 'global-affairs',
    },
    {
        'key': 'bbc-business', 'name': 'BBC News', 'region': 'international', 'kind': 'rss',
        'url': 'https://feeds.bbci.co.uk/news/business/rss.xml',
        'category': 'economics', 'default_category': 'economics',
    },
    {
        'key': 'bbc-technology', 'name': 'BBC News', 'region': 'international', 'kind': 'rss',
        'url': 'https://feeds.bbci.co.uk/news/technology/rss.xml',
        'category': 'technology', 'default_category': 'technology',
    },
    {
        'key': 'bbc-health', 'name': 'BBC News', 'region': 'international', 'kind': 'rss',
        'url': 'https://feeds.bbci.co.uk/news/health/rss.xml',
        'category': 'health', 'default_category': 'health',
    },
    {
        'key': 'bbc-politics', 'name': 'BBC News', 'region': 'international', 'kind': 'rss',
        'url': 'https://feeds.bbci.co.uk/news/politics/rss.xml',
        'category': 'politics', 'default_category': 'politics',
    },
    {
        'key': 'bbc-sport', 'name': 'BBC Sport', 'region': 'international', 'kind': 'rss',
        'url': 'https://feeds.bbci.co.uk/sport/rss.xml',
        'category': 'sports', 'default_category': 'sports',
    },
    {
        'key': 'aljazeera', 'name': 'Al Jazeera', 'region': 'international', 'kind': 'rss',
        'url': 'https://www.aljazeera.com/xml/rss/all.xml',
        'category': None, 'default_category': 'global-affairs',
    },
    {
        'key': 'cnn', 'name': 'CNN', 'region': 'international', 'kind': 'newsapi',
        'newsapi_id': 'cnn',
        'category': None, 'default_category': 'global-affairs',
    },
    {
        'key': 'guardian-world', 'name': 'The Guardian', 'region': 'international', 'kind': 'rss',
        'url': 'https://www.theguardian.com/world/rss',
        'category': None, 'default_category': 'global-affairs',
    },
    {
        'key': 'guardian-technology', 'name': 'The Guardian', 'region': 'international', 'kind': 'rss',
        'url': 'https://www.theguardian.com/technology/rss',
        'category': 'technology', 'default_category': 'technology',
    },
    {
        'key': 'guardian-business', 'name': 'The Guardian', 'region': 'international', 'kind': 'rss',
        'url': 'https://www.theguardian.com/business/rss',
        'category': 'economics', 'default_category': 'economics',
    },
    {
        'key': 'guardian-sport', 'name': 'The Guardian', 'region': 'international', 'kind': 'rss',
        'url': 'https://www.theguardian.com/sport/rss',
        'category': 'sports', 'default_category': 'sports',
    },
    {
        'key': 'dw', 'name': 'DW News', 'region': 'international', 'kind': 'rss',
        'url': 'https://rss.dw.com/rdf/rss-en-all',
        'category': None, 'default_category': 'global-affairs',
    },
    {
        'key': 'france24', 'name': 'France 24', 'region': 'international', 'kind': 'rss',
        'url': 'https://www.france24.com/en/rss',
        'category': None, 'default_category': 'global-affairs',
    },
    {
        'key': 'sky-news', 'name': 'Sky News', 'region': 'international', 'kind': 'rss',
        'url': 'https://feeds.skynews.com/feeds/rss/world.xml',
        'category': None, 'default_category': 'global-affairs',
    },
    {
        'key': 'npr', 'name': 'NPR', 'region': 'international', 'kind': 'rss',
        'url': 'https://feeds.npr.org/1001/rss.xml',
        'category': None, 'default_category': 'global-affairs',
    },
    {
        'key': 'un-news', 'name': 'UN News', 'region': 'international', 'kind': 'rss',
        'url': 'https://news.un.org/feed/subscribe/en/news/all/rss.xml',
        'category': None, 'default_category': 'global-affairs',
    },
    {
        'key': 'who', 'name': 'World Health Organization', 'region': 'international', 'kind': 'rss',
        'url': 'https://www.who.int/rss-feeds/news-english.xml',
        'category': 'health', 'default_category': 'health',
    },
    {
        'key': 'techcrunch', 'name': 'TechCrunch', 'region': 'international', 'kind': 'rss',
        'url': 'https://techcrunch.com/feed/',
        'category': 'technology', 'default_category': 'technology',
    },
    {
        'key': 'the-verge', 'name': 'The Verge', 'region': 'international', 'kind': 'rss',
        'url': 'https://www.theverge.com/rss/index.xml',
        'category': 'technology', 'default_category': 'technology',
    },
    {
        'key': 'espn', 'name': 'ESPN', 'region': 'international', 'kind': 'rss',
        'url': 'https://www.espn.com/espn/rss/news',
        'category': 'sports', 'default_category': 'sports',
    },

    # --- Africa (stories about Zambia are still tagged 'zambia' automatically) ---
    {
        'key': 'africanews', 'name': 'Africanews', 'region': 'international', 'kind': 'rss',
        'url': 'https://www.africanews.com/feeds/rss',
        'category': None, 'default_category': 'global-affairs',
    },
    {
        'key': 'techcabal', 'name': 'TechCabal', 'region': 'international', 'kind': 'rss',
        'url': 'https://techcabal.com/feed/',
        'category': 'technology', 'default_category': 'technology',
    },

    # --- Zambia ------------------------------------------------------------
    {
        'key': 'lusaka-times', 'name': 'Lusaka Times', 'region': 'zambia', 'kind': 'rss',
        'url': 'https://www.lusakatimes.com/feed/',
        'category': None, 'default_category': 'politics',
    },
    {
        'key': 'zambia-daily-mail', 'name': 'Zambia Daily Mail', 'region': 'zambia', 'kind': 'rss',
        'url': 'https://www.daily-mail.co.zm/feed/',
        'category': None, 'default_category': 'politics',
    },
    {
        'key': 'times-of-zambia', 'name': 'Times of Zambia', 'region': 'zambia', 'kind': 'rss',
        'url': 'https://www.times.co.zm/?feed=rss2',
        'category': None, 'default_category': 'politics',
    },
    {
        'key': 'zambia-monitor', 'name': 'Zambia Monitor', 'region': 'zambia', 'kind': 'rss',
        'url': 'https://www.zambiamonitor.com/feed/',
        'category': None, 'default_category': 'economics',
    },
    {
        'key': 'znbc', 'name': 'ZNBC', 'region': 'zambia', 'kind': 'rss',
        'url': 'https://www.znbc.co.zm/news/feed/',
        'category': None, 'default_category': 'politics',
    },
    {
        'key': 'allafrica-zambia', 'name': 'allAfrica', 'region': 'zambia', 'kind': 'rss',
        'url': 'https://allafrica.com/tools/headlines/rdf/zambia/headlines.rdf',
        'category': None, 'default_category': 'politics',
    },
    {
        'key': 'news-diggers', 'name': 'News Diggers', 'region': 'zambia', 'kind': 'rss',
        'url': 'https://diggers.news/feed/',
        'category': None, 'default_category': 'politics',
    },
    {
        'key': 'mwebantu', 'name': 'Mwebantu', 'region': 'zambia', 'kind': 'rss',
        'url': 'https://www.mwebantu.com/feed/',
        'category': None, 'default_category': 'politics',
    },
    {
        'key': 'zambian-observer', 'name': 'Zambian Observer', 'region': 'zambia', 'kind': 'rss',
        'url': 'https://www.zambianobserver.com/feed/',
        'category': None, 'default_category': 'politics',
    },
    {
        'key': 'daily-nation-zambia', 'name': 'Daily Nation Zambia', 'region': 'zambia', 'kind': 'rss',
        'url': 'https://dailynationzambia.com/feed/',
        'category': None, 'default_category': 'politics',
    },
]

REGIONS = ('international', 'zambia')

SOURCES_BY_KEY = {s['key']: s for s in SOURCES}


def enabled_sources(disabled_keys: list[str] | None = None) -> list[dict]:
    disabled = set(disabled_keys or [])
    return [s for s in SOURCES if s['key'] not in disabled]
