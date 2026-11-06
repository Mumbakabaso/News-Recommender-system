import click
from flask import Flask, jsonify

from config import Config
from app.extensions import db, migrate, jwt, cors


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    origins = app.config.get('CORS_ORIGINS', '*')
    cors.init_app(app, resources={r'/api/*': {'origins': origins if origins == '*' else origins.split(',')}})

    # Import models so SQLAlchemy's metadata knows about every table before
    # any `flask db migrate` autogeneration or `db.create_all()` runs.
    from app import models  # noqa: F401

    from app.routes import auth, users, categories, articles, interactions, recommendations, admin, sources, discover, people
    app.register_blueprint(auth.bp)
    app.register_blueprint(users.bp)
    app.register_blueprint(categories.bp)
    app.register_blueprint(articles.bp)
    app.register_blueprint(interactions.bp)
    app.register_blueprint(recommendations.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(sources.bp)
    app.register_blueprint(discover.bp)
    app.register_blueprint(people.bp)

    # Consistent JSON errors when a login is required, so the frontend can
    # tell "not logged in" apart from other failures and send people to sign up.
    @jwt.unauthorized_loader
    def _missing_token(reason):
        return jsonify({'error': 'Create a free account or log in to continue.', 'code': 'auth_required'}), 401

    @jwt.expired_token_loader
    def _expired_token(header, payload):
        return jsonify({'error': 'Your session has expired. Please log in again.', 'code': 'auth_required'}), 401

    @jwt.invalid_token_loader
    def _invalid_token(reason):
        return jsonify({'error': 'Please log in again.', 'code': 'auth_required'}), 401

    @app.get('/api/health')
    def health():
        return jsonify({'status': 'ok'})

    register_cli(app)
    return app


def register_cli(app):
    @app.cli.command('seed-categories')
    def seed_categories():
        """Insert the configured NEWS_CATEGORIES into the categories table."""
        from app.models.category import Category
        for slug in app.config['NEWS_CATEGORIES']:
            if not Category.query.filter_by(slug=slug).first():
                db.session.add(Category(slug=slug, name=slug.replace('-', ' ').title()))
        db.session.commit()
        print('Categories seeded.')

    @app.cli.command('ingest-news')
    def ingest_news():
        """Fetch live news from every source (BBC, Al Jazeera, CNN, Zambian outlets)."""
        from app.services.news_ingestion import run_ingestion
        result = run_ingestion(app.config)
        if result.get('skipped'):
            print(result['reason'])
            return
        for key, s in result['sources'].items():
            line = f"  {'OK  ' if s['ok'] else 'FAIL'} {key:<20} saved {s['saved']:>3} / fetched {s['fetched']:>3}"
            if s['error']:
                line += f"   ({s['error']})"
            print(line)
        print(f"Total saved: {result['total_saved']}" + ('  -> no live source worked, loaded mock data' if result['used_mock'] else ''))

    @app.cli.command('summarize-article')
    @click.argument('article_id', type=int)
    @click.option('--single', is_flag=True, help="Don't combine other outlets' coverage.")
    def summarize_article_cmd(article_id, single):
        """Print the smart summary for one article (handy for testing): flask summarize-article 12"""
        from app.models.article import Article
        from app.services.summarizer import summarise_article
        article = Article.query.get(article_id)
        if not article:
            print('No such article.')
            return
        s = summarise_article(article, include_related=not single)
        print(f"\n{s['title']}\n[{s['engine']}{' / ' + s['model'] if s.get('model') else ''}; "
              f"{len(s['sources'])} article(s) from {s['source_count']} source(s); "
              f"full text for {s['full_text_count']}]\n")
        for p in s['paragraphs']:
            print(p + '\n')
        for k in s['key_points']:
            print(' - ' + k)
        if s.get('why_it_matters'):
            print('\nWhy it matters: ' + s['why_it_matters'])
        print('\nSources: ' + ', '.join(f"{x['source_name']} (#{x['id']})" for x in s['sources']))

    @app.cli.command('clear-summaries')
    def clear_summaries():
        """Delete all cached summaries so they are written again (e.g. after adding a Gemini key)."""
        from app.models.summary import Summary
        n = Summary.query.delete()
        db.session.commit()
        print(f'Deleted {n} cached summaries.')

    @app.cli.command('list-sources')
    def list_sources():
        """Show the configured news sources."""
        from app.services.news_sources import SOURCES
        disabled = set(app.config.get('NEWS_DISABLED_SOURCES', []))
        for s in SOURCES:
            where = s.get('url') or f"NewsAPI sources={s.get('newsapi_id')}"
            flag = 'off' if s['key'] in disabled else 'on '
            print(f"  [{flag}] {s['key']:<20} {s['region']:<14} {where}")

    @app.cli.command('recategorise-articles')
    @click.option('--region', default='zambia', show_default=True,
                  help="Only re-label this region's articles ('all' for every region).")
    @click.option('--dry-run', is_flag=True, help='Show what would change without saving.')
    def recategorise_articles(region, dry_run):
        """Re-run the topic categoriser over stored articles from general (mixed-topic) feeds."""
        from collections import Counter
        from app.models.article import Article
        from app.services.categoriser import categorise
        from app.services.news_sources import SOURCES_BY_KEY
        categories = app.config['NEWS_CATEGORIES']
        query = Article.query
        if region != 'all':
            query = query.filter(Article.region == region)
        moves, checked = Counter(), 0
        for a in query.yield_per(500):
            src = SOURCES_BY_KEY.get(a.source_key or '')
            if src is None or src.get('category'):
                continue  # single-topic feed (e.g. BBC Sport) or mock data: keep its label
            checked += 1
            new = categorise(a.title, a.description or '', [], categories, src['default_category'])
            if new in categories and new != a.category:
                moves[(a.category, new)] += 1
                if not dry_run:
                    a.category = new
        if not dry_run:
            db.session.commit()
        print(f"Checked {checked} articles; {sum(moves.values())} {'would move' if dry_run else 'moved'}.")
        for (old, new), n in moves.most_common():
            print(f'  {old:>15} -> {new:<15} {n}')

    @app.cli.command('purge-mock-articles')
    def purge_mock_articles():
        """Delete the bundled sample articles (and their logged interactions) once live news is flowing."""
        from app.models.article import Article
        from app.models.interaction import Interaction
        from app.models.recommendation_log import RecommendationLog
        ids = [a.id for a in Article.query.filter(Article.url.startswith('https://example.com/mock/')).all()]
        if not ids:
            print('No mock articles found.')
            return
        Interaction.query.filter(Interaction.article_id.in_(ids)).delete(synchronize_session=False)
        RecommendationLog.query.filter(RecommendationLog.article_id.in_(ids)).delete(synchronize_session=False)
        Article.query.filter(Article.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
        print(f'Deleted {len(ids)} mock articles and their interaction history.')

    @app.cli.command('seed-synthetic-interactions')
    def seed_synthetic_interactions():
        """Populate believable interaction history using the RL simulator, for demoing analytics before real traffic exists."""
        from scripts.seed_synthetic_data import run
        run(app)

    # --- AI People Profiles -------------------------------------------------
    @app.cli.command('people-bootstrap')
    @click.option('--limit', default=800, help='Maximum number of people to load.')
    @click.option('--min-sitelinks', default=3, help='Notability threshold for people without a Zambian office.')
    def people_bootstrap(limit, min_sitelinks):
        """Pre-load Zambian public figures (office holders + notable people) from Wikidata."""
        from app.services.people.bootstrap import bootstrap_zambia
        r = bootstrap_zambia(limit=limit, min_sitelinks=min_sitelinks)
        print(f"Found {r['found']}, added {r['created']}, already known {r['already_known']}.")

    @app.cli.command('people-scan')
    @click.option('--all', 'rescan_all', is_flag=True, help='Rescan every article, not just new ones.')
    @click.option('--limit', default=500)
    @click.option('--lookups', default=40, help='Maximum Wikidata lookups for unknown names.')
    def people_scan(rescan_all, limit, lookups):
        """Find people in articles and link them to profiles."""
        from app.models.article import Article
        from app.services.people.linker import scan_pending
        if rescan_all:
            Article.query.update({Article.people_scanned_at: None}, synchronize_session=False)
            db.session.commit()
        r = scan_pending(limit=limit, lookup_limit=lookups)
        print(f"Scanned {r['articles']} articles, {r['mentions']} people mentions, {r['lookups_used']} Wikidata lookups.")

    @app.cli.command('people-refresh')
    def people_refresh():
        """Run one update cycle: scan new articles, refresh latest news, rebuild stale profiles."""
        from app.services.people.updater import run_people_update
        print(run_people_update())

    @app.cli.command('people-profile')
    @click.argument('name')
    def people_profile(name):
        """Build and print one profile, e.g.: flask people-profile "Hakainde Hichilema"."""
        from app.models.person import Person, PersonAlias
        from app.services.people.text import normalize
        from app.services.people.profile_builder import build_profile
        p = (Person.query.join(PersonAlias).filter(PersonAlias.normalized == normalize(name)).first()
             or Person.query.filter_by(slug=name).first())
        if not p:
            from app.services.people.ner import NameCandidate
            from app.services.people.resolver import lookup_wikidata
            from app.services.people.registry import person_from_entity
            found = lookup_wikidata(NameCandidate(name=name, surface=name, start=0, end=0, cues={'title'}),
                                    zambian_ctx=True, category='politics')
            if not found:
                print('No confident match on Wikidata.')
                return
            p = person_from_entity(found[0], found[1])
            db.session.commit()
        build_profile(p)
        prof = p.profile or {}
        print(f"\n{p.full_name}  [{p.wikidata_id or 'news only'}]\n{p.headline_position or ''}\n")
        if prof.get('summary'):
            print(prof['summary']['text'] + '\n')
        for key in prof.get('section_order', []):
            items = prof['sections'].get(key) or []
            if items:
                print(prof['section_titles'][key].upper())
                for it in items:
                    print(f"  - {it['text']}  [{it.get('status')}] {it.get('legal_status') or ''}")
        for d in prof.get('disagreements', []):
            print('DISAGREEMENT: ' + d['details'])
        print(f"\nengine: {prof.get('engine')}  notes: {prof.get('notes')}")

    @app.cli.command('create-admin')
    @click.argument('email')
    @click.argument('name')
    @click.argument('password')
    def create_admin(email, name, password):
        """Create (or promote) an admin user: flask create-admin <email> <name> <password>."""
        from app.models.user import User
        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(name=name, email=email)
            user.set_password(password)
            db.session.add(user)
        user.is_admin = True
        db.session.commit()
        print(f'Admin user ready: {email}')
