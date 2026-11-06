"""
Zambia-first bootstrap: pre-loads Zambian public figures from Wikidata so
they are recognised in articles from day one, including MPs, ministers,
mayors, judges and sports stars who rarely appear in international news.

One SPARQL query selects people with Zambian citizenship who either
  - held a position whose jurisdiction is Zambia (President, Vice President,
    ministers, members of the National Assembly, judges, mayors...), or
  - are notable enough to have articles in several Wikipedia languages
    (business leaders, athletes, musicians, academics, journalists...).
Only identities and aliases are stored here; full profiles are built when
someone opens them, or by the background updater for people in the news.
"""
from __future__ import annotations

from app.extensions import db
from app.models.person import Person
from app.services.people import sources as src
from app.services.people.registry import person_from_entity

QUERY = """
SELECT ?p ?sl WHERE {
  {
    ?p wdt:P31 wd:Q5; wdt:P27 wd:%(zm)s; p:P39/ps:P39 ?pos.
    ?pos wdt:P1001 wd:%(zm)s.
  } UNION {
    ?p wdt:P31 wd:Q5; wdt:P27 wd:%(zm)s; wikibase:sitelinks ?n.
    FILTER(?n >= %(min_sitelinks)d)
  }
  ?p wikibase:sitelinks ?sl.
  FILTER NOT EXISTS { ?p wdt:P570 ?died . FILTER(YEAR(?died) < %(died_after)d) }
}
GROUP BY ?p ?sl
ORDER BY DESC(?sl)
LIMIT %(limit)d
"""


def bootstrap_zambia(limit: int = 800, min_sitelinks: int = 3, died_after: int = 1990, progress=print) -> dict:
    # Confirm Zambia's Wikidata id rather than trusting a constant blindly.
    zm = src.ZAMBIA_QID
    try:
        ent = src.wikidata_entities([zm], props='labels').get(zm)
        if not ent or src.label(ent) != 'Zambia':
            hits = src.wikidata_search('Zambia', limit=3)
            zm = hits[0] if hits else zm
    except src.SourceError:
        pass

    rows = src.wikidata_sparql(QUERY % {'zm': zm, 'min_sitelinks': min_sitelinks, 'limit': limit,
                                        'died_after': died_after})
    qids = []
    for r in rows:
        uri = r.get('p', {}).get('value', '')
        qid = uri.rsplit('/', 1)[-1]
        if qid.startswith('Q') and qid not in qids:
            qids.append(qid)
    progress(f'Wikidata returned {len(qids)} Zambian public figures; loading names and aliases...')

    created = existing = 0
    for i in range(0, len(qids), 50):
        chunk = qids[i:i + 50]
        known = {p.wikidata_id for p in Person.query.filter(Person.wikidata_id.in_(chunk)).all()}
        todo = [q for q in chunk if q not in known]
        existing += len(chunk) - len(todo)
        if not todo:
            continue
        ents = src.wikidata_entities(todo, props='labels|descriptions|aliases|claims|sitelinks')
        for qid in todo:
            e = ents.get(qid)
            if not e or not src.label(e):
                continue
            person_from_entity(qid, e)
            created += 1
        db.session.commit()
        progress(f'  {min(i + 50, len(qids))}/{len(qids)}')
    return {'found': len(qids), 'created': created, 'already_known': existing}
