"""
Named Entity Recognition for people.

Two complementary detectors run over an article's text:

1. Gazetteer matching (see resolver.py): every alias of every person
   already in the database (full names, "President Hichilema", "HH", ...)
   is compiled into one regular expression, so known people are found
   exactly and quickly, in any of their name forms.

2. This module: a rule-based detector for names we have NOT seen before.
   It looks for runs of capitalised words (with initials and particles
   like "van" or "bin") and keeps those that behave like a person's name
   in news writing:
     - preceded by a title or honorific ("Hon.", "Minister", "Mayor",
       "Dr", "Chief", ...)                                    -> strong cue
     - followed by a speech verb ("... said", "... told")      -> medium cue
     - followed by an apposition (", the Minister of ...")     -> medium cue
     - preceded by "according to"                              -> medium cue
     - full name used once, then the surname alone later
       (standard journalistic style)                           -> medium cue
   Organisations and places are filtered out with a stop-list.

   If spaCy and an English model are installed, its PERSON entities are
   added as another medium-strength cue. spaCy is optional: the system
   works without it (useful on new Python versions without spaCy wheels).

Only candidates with at least two name words are sent on to be identified
(resolver.py); a single word is never linked on its own unless it is the
surname of someone already identified in the same article.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field

from app.services.people.text import (TITLES, NON_NAME_WORDS, PARTICLES, strip_title, normalize,
                                      is_title_word)

_NAME_TOKEN = r"(?:[A-Z]['’][A-Z][a-z]+|[A-Z][a-z]+(?:[-'’][A-Z][a-z]+|-[a-z]+)*|[A-Z]\.|[A-Z]{2,4}(?=\s+[A-Z][a-z])|Mc[A-Z][a-z]+|Mac[A-Z][a-z]+)"
_TITLE_ALT = '|'.join(re.escape(t) for t in TITLES)
_RUN_RE = re.compile(
    rf"(?<![\w’'])((?:(?:{_TITLE_ALT})\s+)*{_NAME_TOKEN}(?:\s+(?:(?:{'|'.join(PARTICLES)})\s+)?{_NAME_TOKEN})*)(?:['’]s)?"
)
_SPEECH_AFTER_RE = re.compile(
    r"^(?:['’]s\b)?\s*(?:,\s*(?:who|the|a|an|former|deputy|acting|chief)\b|\s+(?:has\s+|had\s+|will\s+|would\s+)?"
    r"(?:said|says|told|added|stated|noted|explained|announced|urged|warned|argued|insisted|revealed|claimed|"
    r"wrote|tweeted|posted|declared|described|appealed|called|confirmed|denied|charged|directed|emphasised|"
    r"emphasized|disclosed|observed|lamented|pledged|assured)\b)")
_ACCORDING_BEFORE_RE = re.compile(r"(?:according to|said|by|congratulated|met|thanked|appointed|fired|dismissed)\s+$", re.I)

_ROLE_BEFORE_RE = re.compile(
    r"\b(?:spokesperson|spokesman|spokeswoman|minister|mayor|president|secretary|chairperson|chairman|director|"
    r"leader|lawmaker|legislator|mp|chief|coach|striker|captain|lawyer|advocate|judge|ceo|founder|manager|"
    r"governor|ambassador|commissioner|official|activist|analyst|economist|candidate|councillor|pastor|"
    r"bishop|singer|musician|artist|player|midfielder|defender|goalkeeper|forward|boxer|athlete)\s+$", re.I)

_spacy_nlp = None
_spacy_checked = False


@dataclass
class NameCandidate:
    name: str                 # the name without titles, e.g. "Chilando Chitangala"
    surface: str              # exactly as it appeared, e.g. "Mayor Chilando Chitangala"
    start: int
    end: int
    title: str | None = None  # "Mayor"
    cues: set = field(default_factory=set)

    @property
    def strength(self) -> str:
        if 'title' in self.cues:
            return 'strong'
        if self.cues & {'speech', 'apposition', 'according', 'surname_repeat', 'spacy'}:
            return 'medium'
        return 'weak'


def _get_spacy():
    """spaCy is optional. Returns a loaded pipeline or None."""
    global _spacy_nlp, _spacy_checked
    if _spacy_checked:
        return _spacy_nlp
    _spacy_checked = True
    try:  # pragma: no cover - depends on the local install
        import spacy  # type: ignore
        for model in ('en_core_web_sm', 'en_core_web_md', 'en_core_web_lg'):
            try:
                _spacy_nlp = spacy.load(model, disable=['lemmatizer', 'textcat'])
                print(f'[people.ner] using spaCy model {model} as an extra detector')
                break
            except OSError:
                continue
    except Exception:
        _spacy_nlp = None
    return _spacy_nlp


def _is_title_case_heading(text: str) -> bool:
    """Headlines in Title Case capitalise every word, so capitalisation says
    nothing about names there; the detector skips them (known people in
    headlines are still found by the gazetteer)."""
    words = re.findall(r"[A-Za-z][\w'’-]*", text)
    if len(words) < 4:
        return False
    caps = sum(1 for w in words if w[0].isupper())
    return caps / len(words) > 0.6


def _split_run(run: str) -> list[tuple[int, str]]:
    """Split a capitalised run at words that can't be part of a name
    ("Lusaka Mayor Chilando Chitangala" -> keeps "Mayor Chilando Chitangala")."""
    pieces, current, offset, cur_start = [], [], 0, 0
    for m in re.finditer(r'\S+', run):
        w = m.group(0)
        bare = w.rstrip('.,').lower()
        if bare in NON_NAME_WORDS and not is_title_word(w):
            if current:
                pieces.append((cur_start, run[cur_start:offset].strip()))
            current = []
            cur_start = m.end() + 1
        else:
            if not current:
                cur_start = m.start()
            current.append(w)
        offset = m.end()
    if current:
        pieces.append((cur_start, run[cur_start:offset].strip()))
    return pieces


def _strip_leading_role(piece: str) -> tuple[str, str | None, int]:
    """
    'Finance Minister Situmbeko Musokotwane' -> ('Situmbeko Musokotwane', 'Finance Minister', offset)
    'President Hakainde Hichilema'          -> ('Hakainde Hichilema', 'President', offset)
    The title is the last title word(s) in the run; anything before it
    ("Finance", "Copperbelt Province") describes the office.
    """
    name, title = strip_title(piece)
    if title:
        return name, title, 0
    best = None
    for t in TITLES:
        for m in re.finditer(rf"(?<=\s){re.escape(t)}\s+", piece):
            if best is None or m.end() > best[1]:
                best = (m.start(), m.end(), t)
    if best is None:
        return piece, None, 0
    rest = piece[best[1]:]
    rest_name, extra = strip_title(rest)
    title = piece[:best[1]].strip()
    return rest_name, (title + (' ' + extra if extra else '')), 0


def extract_candidates(text: str) -> list[NameCandidate]:
    """Unknown-name candidates in one block of text (a paragraph, a summary, ...)."""
    if not text or _is_title_case_heading(text):
        return []
    out: list[NameCandidate] = []
    for m in _RUN_RE.finditer(text):
        run_start = m.start(1)
        for rel, piece in _split_run(m.group(1)):
            name, title, rel_shift = _strip_leading_role(piece)
            tokens = name.split()
            # Drop trailing/leading title words that slipped through ("Banda Minister").
            while tokens and is_title_word(tokens[-1]) and len(tokens) > 1:
                tokens.pop()
            name = ' '.join(tokens)
            real_words = [t for t in tokens if len(t.rstrip('.')) > 1 and t.lower() not in PARTICLES]
            if len(real_words) < 2 or len(tokens) > 5:
                continue
            if any(t.rstrip('.').lower() in NON_NAME_WORDS for t in tokens):
                continue
            start = run_start + rel
            end = start + len(piece)
            c = NameCandidate(name=name, surface=piece[rel_shift:], start=start + rel_shift, end=end, title=title)
            if title:
                c.cues.add('title')
            after = text[end:end + 60]
            if _SPEECH_AFTER_RE.match(after):
                c.cues.add('apposition' if after.lstrip().startswith(',') else 'speech')
            before = text[max(0, start - 30):start]
            if _ACCORDING_BEFORE_RE.search(before):
                c.cues.add('according')
            if not title and _ROLE_BEFORE_RE.search(before):
                c.cues.add('apposition')
            out.append(c)
    return out


def extract_from_document(blocks: list[str]) -> list[NameCandidate]:
    """
    Candidates across a whole article (title, teaser, body, summary...).
    Adds the document-level "surname repeated" cue and spaCy's PERSON
    entities when available. Returns one candidate per distinct name, with
    the cues merged.
    """
    by_name: dict[str, NameCandidate] = {}
    full_text = '\n'.join(b for b in blocks if b)
    for block in blocks:
        for c in extract_candidates(block or ''):
            key = normalize(c.name)
            if key in by_name:
                by_name[key].cues |= c.cues
                if c.title and not by_name[key].title:
                    by_name[key].title = c.title
            else:
                by_name[key] = c

    nlp = _get_spacy()
    if nlp is not None:  # pragma: no cover - optional
        try:
            doc = nlp(full_text[:100_000])
            for ent in doc.ents:
                if ent.label_ != 'PERSON':
                    continue
                name, title = strip_title(ent.text.strip())
                if len(name.split()) < 2:
                    continue
                key = normalize(name)
                if key in by_name:
                    by_name[key].cues.add('spacy')
                else:
                    by_name[key] = NameCandidate(name=name, surface=ent.text, start=ent.start_char,
                                                 end=ent.end_char, title=title, cues={'spacy'})
        except Exception as e:
            print(f'[people.ner] spaCy failed, continuing without it: {e}')

    # Journalistic convention: "Chilando Chitangala ... Ms Chitangala said".
    for key, c in by_name.items():
        surname = c.name.split()[-1]
        if len(surname) > 2 and len(re.findall(rf"(?<![\w-]){re.escape(surname)}(?![\w-])", full_text)) >= 2:
            c.cues.add('surname_repeat')
    return list(by_name.values())
