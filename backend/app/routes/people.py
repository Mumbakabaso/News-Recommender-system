"""
AI People Profiles API.

  GET  /api/articles/<id>/people          people mentioned in an article + the exact
                                          strings to hyperlink (account required, like the article)
  GET  /api/people?q=&zambian=1&category= directory / search of known people
  GET  /api/people/<id or slug>           full profile (built on first request; latest
                                          developments refreshed if older than 6 hours)
  GET  /api/people/<id>/developments      paginated latest developments
  GET  /api/people/<id>/articles          articles in this app that mention the person
  POST /api/people/<id>/refresh           admin: rebuild facts, biography and news now
  GET  /api/admin/people/candidates       admin: names that could not be identified
  POST /api/admin/people/candidates/<id>  admin: {"action": "reject"} or {"action": "link", "wikidata_id": "Q.."}
  POST /api/admin/people/<id>/aliases     admin: {"alias": "HH", "ambiguous": true}
"""
import threading

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import or_

from app.extensions import db
from app.models.article import Article
from app.models.person import Person, PersonAlias, ArticleMention, PersonCandidate
from app.models.user import User
from app.services.people import sources as src
from app.services.people.linker import scan_article, link_forms
from app.services.people.profile_builder import build_profile, needs_rebuild, needs_news, serialize
from app.services.people.developments import list_developments, refresh_developments
from app.services.people.registry import add_alias, person_from_entity
from app.services.people.text import normalize

bp = Blueprint('people', __name__, url_prefix='/api')

_bg_running: set[int] = set()
_bg_guard = threading.Lock()


def _require_admin():
    user = User.query.get(int(get_jwt_identity()))
    return user if user and user.is_admin else None


def _find_person(key: str) -> Person | None:
    if key.isdigit():
        return Person.query.get(int(key))
    return Person.query.filter_by(slug=key).first()


def _in_background(person_id: int, fn_name: str):
    """Refresh news (or rebuild) after responding, so the reader isn't kept waiting."""
    with _bg_guard:
        if person_id in _bg_running:
            return
        _bg_running.add(person_id)
    app = current_app._get_current_object()

    def run():
        try:
            with app.app_context():
                p = Person.query.get(person_id)
                if not p:
                    return
                if fn_name == 'news':
                    refresh_developments(p)
                else:
                    build_profile(p)
        except Exception as e:
            print(f'[people] background {fn_name} failed for person {person_id}: {e}')
        finally:
            with _bg_guard:
                _bg_running.discard(person_id)

    threading.Thread(target=run, daemon=True).start()


@bp.get('/articles/<int:article_id>/people')
@jwt_required()
def article_people(article_id):
    article = Article.query.get(article_id)
    if not article:
        return jsonify({'error': 'Article not found.'}), 404
    if article.people_scanned_at is None or request.args.get('rescan') == '1':
        try:
            scan_article(article, allow_lookups=True, lookup_budget=[6])
        except Exception as e:
            db.session.rollback()
            print(f'[people] scan failed for article {article_id}: {e}')
    mentions = (ArticleMention.query.filter_by(article_id=article_id)
                .order_by(ArticleMention.mention_count.desc()).all())
    forms = link_forms(mentions)
    people = []
    for m in mentions:
        if not m.person:
            continue
        people.append({**m.person.card(), 'link_forms': forms.get(m.person_id, []),
                       'mention_count': m.mention_count, 'confidence': round(m.confidence, 2)})
    return jsonify({'article_id': article_id, 'people': people})


@bp.get('/people')
def list_people():
    q = (request.args.get('q') or '').strip()
    page = max(int(request.args.get('page', 1)), 1)
    page_size = min(max(int(request.args.get('page_size', 24)), 1), 100)
    query = Person.query
    if q:
        norm = f'%{normalize(q)}%'
        query = query.filter(or_(Person.full_name.ilike(f'%{q}%'), Person.display_name.ilike(f'%{q}%'),
                                 Person.id.in_(db.session.query(PersonAlias.person_id)
                                               .filter(PersonAlias.normalized.like(norm)))))
    if request.args.get('zambian') == '1':
        query = query.filter(Person.is_zambian.is_(True))
    if request.args.get('category'):
        query = query.filter(Person.category == request.args['category'])
    if request.args.get('in_news') == '1':
        query = query.filter(Person.mention_count > 0)
    query = query.order_by(Person.mention_count.desc(), Person.last_mentioned_at.desc().nullslast(),
                           Person.display_name.asc())
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return jsonify({'people': [p.card() for p in items], 'total': total, 'page': page, 'page_size': page_size})


@bp.get('/people/<key>')
def get_person(key):
    person = _find_person(key)
    if not person:
        return jsonify({'error': 'Person not found.'}), 404
    refreshing = False
    if needs_rebuild(person):
        if person.status == 'ready' and person.profile:
            # A week-old profile is still useful: show it and rebuild in the background.
            _in_background(person.id, 'rebuild')
            refreshing = True
        else:
            try:
                build_profile(person)
            except Exception as e:
                db.session.rollback()
                person.status = 'failed'
                person.last_error = str(e)[:500]
                db.session.commit()
    elif needs_news(person):
        _in_background(person.id, 'news')
        refreshing = True
    data = serialize(person)
    data['refreshing'] = refreshing
    return jsonify(data)


@bp.get('/people/<int:person_id>/developments')
def person_developments(person_id):
    person = Person.query.get(person_id)
    if not person:
        return jsonify({'error': 'Person not found.'}), 404
    page = max(int(request.args.get('page', 1)), 1)
    page_size = min(max(int(request.args.get('page_size', 10)), 1), 50)
    return jsonify({'developments': list_developments(person, limit=page_size, offset=(page - 1) * page_size),
                    'page': page, 'updated_at': person.developments_updated_at.isoformat()
                    if person.developments_updated_at else None})


@bp.get('/people/<int:person_id>/articles')
def person_articles(person_id):
    if not Person.query.get(person_id):
        return jsonify({'error': 'Person not found.'}), 404
    limit = min(max(int(request.args.get('limit', 12)), 1), 50)
    rows = (Article.query.join(ArticleMention, ArticleMention.article_id == Article.id)
            .filter(ArticleMention.person_id == person_id)
            .order_by(Article.published_at.desc().nullslast()).limit(limit).all())
    return jsonify({'articles': [a.to_dict() for a in rows]})


@bp.post('/people/<int:person_id>/refresh')
@jwt_required()
def refresh_person(person_id):
    if not _require_admin():
        return jsonify({'error': 'Admin access required.'}), 403
    person = Person.query.get(person_id)
    if not person:
        return jsonify({'error': 'Person not found.'}), 404
    person.developments_updated_at = None
    build_profile(person)
    return jsonify(serialize(person))


# --- admin: review unresolved names and curate aliases ------------------------------
@bp.get('/admin/people/candidates')
@jwt_required()
def list_candidates():
    if not _require_admin():
        return jsonify({'error': 'Admin access required.'}), 403
    status = request.args.get('status', 'unresolved')
    rows = (PersonCandidate.query.filter_by(status=status)
            .order_by(PersonCandidate.mention_count.desc()).limit(100).all())
    return jsonify({'candidates': [c.to_dict() for c in rows]})


@bp.post('/admin/people/candidates/<int:cand_id>')
@jwt_required()
def act_on_candidate(cand_id):
    if not _require_admin():
        return jsonify({'error': 'Admin access required.'}), 403
    c = PersonCandidate.query.get(cand_id)
    if not c:
        return jsonify({'error': 'Candidate not found.'}), 404
    body = request.get_json(silent=True) or {}
    if body.get('action') == 'reject':
        c.status = 'rejected'
        db.session.commit()
        return jsonify(c.to_dict())
    if body.get('action') == 'link' and str(body.get('wikidata_id', '')).startswith('Q'):
        qid = body['wikidata_id']
        try:
            ent = src.wikidata_entities([qid]).get(qid)
        except src.SourceError as e:
            return jsonify({'error': f'Wikidata unavailable: {e}'}), 502
        if not ent:
            return jsonify({'error': 'Wikidata item not found.'}), 404
        person = person_from_entity(qid, ent)
        add_alias(person, c.name, None, 'admin')
        c.status, c.person_id = 'resolved', person.id
        # Rescan the articles that mentioned this name.
        Article.query.filter(Article.id.in_(c.article_ids or [])).update(
            {Article.people_scanned_at: None}, synchronize_session=False)
        db.session.commit()
        return jsonify({'candidate': c.to_dict(), 'person': person.card()})
    return jsonify({'error': 'action must be "reject" or "link" (with wikidata_id).'}), 400


@bp.post('/admin/people/<int:person_id>/aliases')
@jwt_required()
def add_person_alias(person_id):
    if not _require_admin():
        return jsonify({'error': 'Admin access required.'}), 403
    person = Person.query.get(person_id)
    if not person:
        return jsonify({'error': 'Person not found.'}), 404
    body = request.get_json(silent=True) or {}
    alias = (body.get('alias') or '').strip()
    if not alias:
        return jsonify({'error': 'alias is required.'}), 400
    a = add_alias(person, alias, body.get('kind'), 'admin',
                  body.get('ambiguous') if isinstance(body.get('ambiguous'), bool) else None)
    # Articles must be rescanned to pick up the new name form.
    Article.query.update({Article.people_scanned_at: None}, synchronize_session=False)
    db.session.commit()
    return jsonify({'alias': a.alias if a else None, 'kind': a.kind if a else None,
                    'ambiguous': a.is_ambiguous if a else None})
