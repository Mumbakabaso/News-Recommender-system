"""Shared text helpers for the people pipeline: name normalisation and titles."""
from __future__ import annotations
import hashlib
import re
import unicodedata

# Titles and honorifics that commonly precede a name in Zambian and
# international reporting. Longest first so "Vice President" wins over
# "President". Matching is case-sensitive on the first letter (a title in a
# headline or before a name is capitalised).
TITLES = sorted({
    'President', 'Vice President', 'Vice-President', 'Former President', 'Ex-President', 'Acting President',
    'Republican President', 'Prime Minister', 'Deputy Minister', 'Minister', 'Deputy Speaker', 'Speaker',
    'First Deputy Speaker', 'Chief Justice', 'Deputy Chief Justice', 'Justice', 'Judge', 'Magistrate',
    'Attorney General', 'Solicitor General', 'Secretary General', 'Secretary-General', 'Permanent Secretary',
    'Provincial Minister', 'Mayor', 'Deputy Mayor', 'Lord Mayor', 'Council Chairperson', 'Town Clerk',
    'Governor', 'Senator', 'Ambassador', 'High Commissioner', 'Commissioner', 'Inspector General',
    'Inspector-General', 'Police Spokesperson', 'Spokesperson', 'Chairperson', 'Chairman', 'Chairwoman',
    'Director', 'Director General', 'Director-General', 'Managing Director', 'Chief Executive', 'CEO',
    'Chief', 'Senior Chief', 'Paramount Chief', 'Senior Chieftainess', 'Chieftainess', 'Chitimukulu',
    'Litunga', 'King', 'Queen', 'Prince', 'Princess', 'Bishop', 'Archbishop', 'Pastor', 'Reverend', 'Rev.',
    'Father', 'Sheikh', 'Pope', 'Professor', 'Prof.', 'Prof', 'Dr.', 'Dr', 'Hon.', 'Hon', 'Honourable',
    'Mr.', 'Mr', 'Mrs.', 'Mrs', 'Ms.', 'Ms', 'Madam', 'Sir', 'Dame', 'Lady', 'Lord', 'General', 'Gen.',
    'Lieutenant General', 'Major General', 'Brigadier General', 'Colonel', 'Col.', 'Major', 'Captain',
    'Commander', 'Lt.', 'Coach', 'Captain', 'Striker', 'Midfielder', 'Defender', 'Goalkeeper',
    'Opposition Leader', 'Party President', 'Party Leader', 'MP', 'Senator', 'Councillor', 'Cllr',
    'Mwami', 'Mpezeni', 'Kazembe',
}, key=len, reverse=True)

# Titles that indicate a public office (used to give more weight to a match).
OFFICE_TITLES = {
    'President', 'Vice President', 'Vice-President', 'Former President', 'Prime Minister', 'Minister',
    'Deputy Minister', 'Speaker', 'Chief Justice', 'Justice', 'Judge', 'Attorney General', 'Mayor',
    'Governor', 'Ambassador', 'High Commissioner', 'Inspector General', 'Hon.', 'Hon', 'Honourable',
    'Provincial Minister', 'Permanent Secretary', 'MP', 'Councillor', 'Senator', 'Secretary General',
    'Opposition Leader', 'Party President', 'Chief', 'Senior Chief', 'Paramount Chief',
}

_TITLE_WORDS = {w.rstrip('.').lower() for t in TITLES for w in t.split()}

# Capitalised words that are never (part of) a person's name. Keeps the
# rule-based detector from treating organisations and places as people.
NON_NAME_WORDS = set("""
the a an and of for in on at to by with from as this that these those it its his her their our we you they
monday tuesday wednesday thursday friday saturday sunday january february march april may june july august
september october november december today yesterday tomorrow
zambia zambian zambians lusaka ndola kitwe kabwe livingstone chipata kasama solwezi mongu mansa chingola
mufulira luanshya kafue chililabombwe copperbelt luapula muchinga northern southern eastern western central
north-western northwestern province provincial district africa african south north east west america american
europe european china chinese britain british uk us usa un eu au sadc comesa imf world bank
government ministry ministries department council court courts party parliament national assembly assembly
house senate republic state states city town university college school hospital clinic church police service
services commission authority agency board company corporation limited ltd plc inc group fund union
association federation league club fc united network news times daily mail post radio tv television
congress front alliance movement forum foundation trust institute centre center office cabinet
president minister ministers presidential constitution constitutional supreme high magistrates electoral
covid coronavirus kwacha dollar dollars budget economy election elections bill act
breaking update live watch read video photos photo exclusive opinion analysis editorial
english new old great royal grand saint st
""".split())

PARTICLES = {'van', 'von', 'de', 'da', 'del', 'der', 'du', 'la', 'le', 'bin', 'ibn', 'al', 'el', 'dos', 'di', 'mac'}

# Words in a person's Wikidata description / occupation that tell us which
# kind of news they appear in. Used to judge whether a candidate fits the
# article it was found in.
DOMAIN_WORDS = {
    'politics': {'politician', 'president', 'minister', 'diplomat', 'lawyer', 'parliament', 'member', 'judge',
                 'activist', 'monarch', 'chief', 'king', 'queen', 'governor', 'mayor', 'senator', 'leader',
                 'statesman', 'official', 'civil', 'servant', 'jurist', 'advocate', 'trade', 'unionist',
                 'military', 'officer', 'general', 'ambassador', 'councillor', 'prime'},
    'economics': {'businessperson', 'businessman', 'businesswoman', 'economist', 'banker', 'entrepreneur',
                  'executive', 'investor', 'accountant', 'industrialist', 'financier', 'politician',
                  'president', 'minister', 'governor'},
    'technology': {'engineer', 'computer', 'scientist', 'entrepreneur', 'businessperson', 'businessman',
                   'programmer', 'inventor', 'executive', 'researcher'},
    'sports': {'footballer', 'football', 'association', 'athlete', 'boxer', 'cricketer', 'coach', 'runner',
               'player', 'sportsperson', 'sprinter', 'swimmer', 'golfer', 'tennis', 'rugby', 'basketball',
               'manager', 'cyclist', 'referee', 'olympic', 'marathon', 'chess'},
    'health': {'physician', 'doctor', 'scientist', 'nurse', 'epidemiologist', 'surgeon', 'researcher',
               'virologist', 'pharmacologist', 'minister', 'politician', 'medical'},
}
DOMAIN_WORDS['global-affairs'] = DOMAIN_WORDS['politics'] | {'businessperson', 'economist'}


def strip_accents(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))


def normalize(name: str) -> str:
    """'Hakainde  Hichilema' / 'HAKAINDE HICHILEMA' / 'Hakaindé Hichilema' -> 'hakainde hichilema'."""
    s = strip_accents(name or '').lower()
    s = s.replace('’', "'").replace('‘', "'")
    s = re.sub(r"[^a-z0-9' \-]", ' ', s)
    s = re.sub(r'\s*-\s*', '-', s)
    return re.sub(r'\s+', ' ', s).strip(" '-")


def strip_title(name: str) -> tuple[str, str | None]:
    """'President Hakainde Hichilema' -> ('Hakainde Hichilema', 'President')."""
    name = name.strip()
    for t in TITLES:
        if name.startswith(t + ' ') and len(name) > len(t) + 1:
            rest, title = name[len(t):].strip(), t
            # "Hon. Dr. X": strip a second title too
            rest2, t2 = strip_title(rest)
            return rest2, (title if not t2 else f'{title} {t2}')
    return name, None


def surname_of(full_name: str) -> str | None:
    parts = [p for p in strip_title(full_name)[0].split() if p.strip('.')]
    if len(parts) < 2:
        return None
    last = parts[-1]
    if last.lower().rstrip('.') in {'jr', 'sr', 'ii', 'iii', 'iv'} and len(parts) >= 3:
        last = parts[-2]
    if len(last.rstrip('.')) <= 1:
        return None
    return last


def initials_of(full_name: str) -> str | None:
    parts = [p for p in strip_title(full_name)[0].split() if p[:1].isalpha()]
    if len(parts) < 2:
        return None
    return ''.join(p[0].upper() for p in parts)


def url_hash(url: str) -> str:
    return hashlib.sha256((url or '').strip().encode('utf-8')).hexdigest()


def slugify(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', normalize(name)).strip('-')[:140] or 'person'


def is_title_word(word: str) -> bool:
    return word.rstrip('.').lower() in _TITLE_WORDS
