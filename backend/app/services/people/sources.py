"""
Information retrieval for people profiles.

Profiles are written FROM these sources, never from an AI model's memory:

  Wikidata   structured, dated, referenced facts: positions held (with start
             and end dates), party, education, awards, date/place of birth,
             citizenship, the official photo on Wikimedia Commons. Also the
             identity anchor (QID) that prevents duplicate profiles.
  Wikipedia  the narrative biography, split into its sections (early life,
             career, presidency, controversies, ...).
  News       the latest developments: Google News search (Zambia edition for
             Zambian figures; no API key) plus the app's own ingested
             articles from BBC, Al Jazeera, CNN and the Zambian outlets.

Every document gets a credibility tier, following the priority order:
  1 official Zambian government websites (*.gov.zm, State House)
  2 Parliament of Zambia
  3 Electoral Commission of Zambia
  4 official institutional publications (Bank of Zambia, judiciary, UNZA, ...)
  5 reputable Zambian media
  6 international news organisations (and Wikipedia/Wikidata as references)
  7 anything else
Lower = more authoritative. Tiers order the Latest Developments list and
tell the AI which source wins when two disagree.

All requests send a descriptive User-Agent (required by Wikimedia) and use
short timeouts; any failure returns empty results so a profile can still be
built from whatever did respond.
"""
from __future__ import annotations
import calendar
import html
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote, urlparse

import requests

USER_AGENT = 'NewsRecommendationSystem-PeopleProfiles/1.0 (academic news recommender prototype; Python requests)'
TIMEOUT = 15
WIKIDATA_API = 'https://www.wikidata.org/w/api.php'
WIKIDATA_SPARQL = 'https://query.wikidata.org/sparql'
WIKIPEDIA_API = 'https://en.wikipedia.org/w/api.php'
GOOGLE_NEWS_RSS = 'https://news.google.com/rss/search'
ZAMBIA_QID = 'Q953'
HUMAN_QID = 'Q5'

_session = requests.Session()
_session.headers.update({'User-Agent': USER_AGENT, 'Accept': 'application/json'})


class SourceError(Exception):
    pass


def _get_json(url: str, params: dict, timeout: int = TIMEOUT) -> dict:
    last = None
    for attempt in range(2):
        try:
            r = _session.get(url, params=params, timeout=timeout)
            if r.status_code == 429:  # Wikimedia rate limit: wait and retry once
                time.sleep(2 + attempt * 3)
                last = SourceError('rate limited')
                continue
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            last = e
    raise SourceError(str(last))


# --------------------------------------------------------------------------
# Credibility tiers
# --------------------------------------------------------------------------
ZAMBIAN_MEDIA = {
    'znbc.co.zm', 'times.co.zm', 'daily-mail.co.zm', 'lusakatimes.com', 'diggers.news', 'zambiamonitor.com',
    'mwebantu.com', 'thecontinent.org', 'zambiadailynation.com', 'lusakavoice.com', 'zambianeye.com',
    'newsdiggers.co.zm', 'theglobeonline.co.zm', 'phoenixfm.co.zm', 'hotfmzambia.com', 'muvitv.com',
    'zambia.co.zm', 'thefalconzambia.com', 'zambiareports.com', 'zambian-observer.com', 'kalemba.news',
    'prime.co.zm', 'diamondtv.co.zm', 'mwebantu.news', 'zambiaonline.co.zm',
}
INSTITUTIONAL = {
    'boz.zm', 'unza.zm', 'zambiahumanrights.org', 'acc.gov.zm', 'zra.org.zm', 'zamstats.gov.zm', 'judiciary.gov.zm',
    'lazambia.com', 'zccm-ih.com.zm', 'cbu.ac.zm', 'zesco.co.zm', 'faz.co.zm', 'nocz.co.zm', 'zicta.zm',
    'cec.org.zm', 'loz.co.zm', 'lsk.or.ke', 'au.int', 'un.org', 'imf.org', 'worldbank.org', 'sadc.int',
    'comesa.int',
}
INTERNATIONAL = {
    'bbc.co.uk', 'bbc.com', 'reuters.com', 'apnews.com', 'aljazeera.com', 'cnn.com', 'theguardian.com',
    'ft.com', 'bloomberg.com', 'economist.com', 'nytimes.com', 'washingtonpost.com', 'africanews.com',
    'theafricareport.com', 'allafrica.com', 'news24.com', 'dw.com', 'france24.com', 'voanews.com',
    'theeastafrican.co.ke', 'businessday.ng', 'iol.co.za', 'dailymaverick.co.za', 'semafor.com',
    'wikipedia.org', 'wikidata.org', 'npr.org', 'cnbc.com', 'skysports.com', 'espn.com', 'fifa.com',
    'cafonline.com', 'olympics.com',
}


def domain_of(url: str) -> str:
    try:
        host = (urlparse(url).hostname or '').lower()
    except ValueError:
        return ''
    return host[4:] if host.startswith('www.') else host


def _matches(host: str, domains: set[str]) -> bool:
    return any(host == d or host.endswith('.' + d) for d in domains)


def credibility_tier(url: str) -> int:
    host = domain_of(url)
    if not host:
        return 7
    if host == 'parliament.gov.zm' or host.endswith('.parliament.gov.zm'):
        return 2
    if host in ('elections.org.zm', 'www.elections.org.zm') or host.endswith('.elections.org.zm'):
        return 3
    if host.endswith('.gov.zm') or host == 'gov.zm' or host in ('statehouse.gov.zm', 'zambia.gov.zm'):
        return 1
    if _matches(host, INSTITUTIONAL):
        return 4
    if _matches(host, ZAMBIAN_MEDIA) or host.endswith('.zm'):
        return 5
    if _matches(host, INTERNATIONAL):
        return 6
    return 7


TIER_LABELS = {1: 'Official (Government of Zambia)', 2: 'Parliament of Zambia', 3: 'Electoral Commission of Zambia',
               4: 'Official institution', 5: 'Zambian media', 6: 'International media / reference', 7: 'Other'}


# --------------------------------------------------------------------------
# Wikidata
# --------------------------------------------------------------------------
def wikidata_search(name: str, limit: int = 7) -> list[str]:
    """QIDs whose label or alias matches the name (best first)."""
    data = _get_json(WIKIDATA_API, {
        'action': 'wbsearchentities', 'search': name, 'language': 'en', 'uselang': 'en',
        'type': 'item', 'limit': limit, 'format': 'json',
    })
    return [r['id'] for r in data.get('search', []) if r.get('id', '').startswith('Q')]


def wikidata_entities(qids: list[str], props: str = 'labels|descriptions|aliases|claims|sitelinks') -> dict:
    out = {}
    for i in range(0, len(qids), 50):
        chunk = qids[i:i + 50]
        if not chunk:
            continue
        data = _get_json(WIKIDATA_API, {
            'action': 'wbgetentities', 'ids': '|'.join(chunk), 'props': props,
            'languages': 'en', 'sitefilter': 'enwiki', 'format': 'json',
        })
        for qid, ent in (data.get('entities') or {}).items():
            if 'missing' not in ent:
                out[qid] = ent
    return out


def wikidata_labels(qids: list[str]) -> dict[str, str]:
    qids = sorted({q for q in qids if q and q.startswith('Q')})
    ents = wikidata_entities(qids, props='labels') if qids else {}
    return {q: (e.get('labels', {}).get('en') or {}).get('value') for q, e in ents.items()
            if (e.get('labels', {}).get('en') or {}).get('value')}


def wikidata_sparql(query: str) -> list[dict]:
    data = _get_json(WIKIDATA_SPARQL, {'query': query, 'format': 'json'}, timeout=60)
    return data.get('results', {}).get('bindings', [])


def label(ent: dict) -> str | None:
    return (ent.get('labels', {}).get('en') or {}).get('value')


def description(ent: dict) -> str | None:
    return (ent.get('descriptions', {}).get('en') or {}).get('value')


def aliases(ent: dict) -> list[str]:
    return [a['value'] for a in ent.get('aliases', {}).get('en', []) if a.get('value')]


def claims(ent: dict, prop: str) -> list[dict]:
    """Claims for a property, excluding deprecated ones, preferred rank first."""
    cs = [c for c in ent.get('claims', {}).get(prop, []) if c.get('rank') != 'deprecated']
    return sorted(cs, key=lambda c: 0 if c.get('rank') == 'preferred' else 1)


def snak_value(snak: dict):
    """Plain Python value of a Wikidata snak: QID str, time dict, string, ..."""
    if not snak or snak.get('snaktype') != 'value':
        return None
    dv = snak.get('datavalue', {})
    v = dv.get('value')
    t = dv.get('type')
    if t == 'wikibase-entityid':
        return v.get('id')
    if t == 'time':
        return {'time': v.get('time'), 'precision': v.get('precision')}
    if t == 'monolingualtext':
        return v.get('text')
    return v


def claim_value(c: dict):
    return snak_value(c.get('mainsnak', {}))


def qualifier(c: dict, prop: str):
    qs = c.get('qualifiers', {}).get(prop) or []
    return snak_value(qs[0]) if qs else None


def wd_time_to_str(v) -> str | None:
    """'+1962-06-04T00:00:00Z' (precision 11) -> '1962-06-04'; precision 9 -> '1962'; 10 -> '1962-06'."""
    if not v or not isinstance(v, dict) or not v.get('time'):
        return None
    m = re.match(r'([+-])(\d+)-(\d\d)-(\d\d)', v['time'])
    if not m:
        return None
    sign, y, mo, d = m.groups()
    y = str(int(y))
    if sign == '-':
        y = '-' + y
    p = v.get('precision') or 11
    if p >= 11 and d != '00':
        return f'{y}-{mo}-{d}'
    if p >= 10 and mo != '00':
        return f'{y}-{mo}'
    return y


def sitelink_count(ent: dict) -> int:
    return len(ent.get('sitelinks', {}) or {})


def enwiki_title(ent: dict) -> str | None:
    return (ent.get('sitelinks', {}).get('enwiki') or {}).get('title')


def commons_image(filename: str, width: int = 480) -> tuple[str, str]:
    f = filename.replace(' ', '_')
    return (f'https://commons.wikimedia.org/wiki/Special:FilePath/{quote(f)}?width={width}',
            f'https://commons.wikimedia.org/wiki/File:{quote(f)}')


def wikidata_url(qid: str) -> str:
    return f'https://www.wikidata.org/wiki/{qid}'


# --------------------------------------------------------------------------
# Wikipedia
# --------------------------------------------------------------------------
def wikipedia_article(title: str) -> dict | None:
    """
    {'title', 'url', 'sections': [{'heading', 'text'}], 'lead'} from the
    plain-text extract. Section 0 is the lead.
    """
    data = _get_json(WIKIPEDIA_API, {
        'action': 'query', 'prop': 'extracts|info', 'explaintext': 1, 'exsectionformat': 'wiki',
        'inprop': 'url', 'redirects': 1, 'titles': title, 'format': 'json', 'formatversion': 2,
    })
    pages = data.get('query', {}).get('pages') or []
    if not pages or pages[0].get('missing'):
        return None
    page = pages[0]
    text = page.get('extract') or ''
    sections, heading, buf = [], 'Lead', []
    for line in text.split('\n'):
        m = re.match(r'^(=+)\s*(.+?)\s*\1$', line.strip())
        if m:
            if buf:
                sections.append({'heading': heading, 'level': 1, 'text': '\n'.join(buf).strip()})
            heading, buf = m.group(2), []
        else:
            buf.append(line)
    if buf:
        sections.append({'heading': heading, 'text': '\n'.join(buf).strip()})
    sections = [s for s in sections if s['text']]
    return {
        'title': page.get('title') or title,
        'url': page.get('fullurl') or f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}",
        'lead': sections[0]['text'] if sections and sections[0]['heading'] == 'Lead' else '',
        'sections': sections,
    }


# --------------------------------------------------------------------------
# News search
# --------------------------------------------------------------------------
def _parse_date(entry) -> datetime | None:
    for key in ('published_parsed', 'updated_parsed'):
        t = entry.get(key)
        if t:
            return datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc).replace(tzinfo=None)
    return None


def google_news(query: str, zambia: bool = True, limit: int = 25) -> list[dict]:
    """
    Recent news for a query from Google News RSS (no key). Returns
    [{'title', 'url', 'publisher', 'publisher_url', 'published_at', 'summary'}].
    """
    import feedparser
    params = {'q': query}
    params.update({'hl': 'en-ZM', 'gl': 'ZM', 'ceid': 'ZM:en'} if zambia else
                  {'hl': 'en-GB', 'gl': 'GB', 'ceid': 'GB:en'})
    try:
        r = _session.get(GOOGLE_NEWS_RSS, params=params, timeout=TIMEOUT,
                         headers={'Accept': 'application/rss+xml, application/xml;q=0.9, */*;q=0.5'})
        r.raise_for_status()
    except requests.RequestException as e:
        raise SourceError(str(e))
    feed = feedparser.parse(r.content)
    out = []
    for e in feed.entries[:limit]:
        title = html.unescape(e.get('title') or '').strip()
        src = e.get('source') or {}
        publisher = (src.get('title') if isinstance(src, dict) else None) or ''
        publisher_url = (src.get('href') if isinstance(src, dict) else None) or ''
        # Google appends " - Publisher" to every title.
        if publisher and title.endswith(' - ' + publisher):
            title = title[: -len(publisher) - 3].strip()
        summary = re.sub(r'<[^>]+>', ' ', html.unescape(e.get('summary') or ''))
        summary = re.sub(r'\s+', ' ', summary).strip()
        if summary.startswith(title):
            summary = ''
        out.append({
            'title': title,
            'url': e.get('link'),
            'publisher': publisher or domain_of(publisher_url),
            'publisher_url': publisher_url,
            'published_at': _parse_date(e),
            'summary': summary[:400] or None,
        })
    return out
