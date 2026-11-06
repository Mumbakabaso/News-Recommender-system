# Getting the RL News Recommender Running (Windows)

This walks through standing up what's already built: a Flask API, a Postgres-backed
data model, and a contextual-bandit RL engine that already has a trained model file
at `backend/rl/artifacts/bandit_policy.zip`. You're not building the system from
scratch — you're wiring up infrastructure and running it.

Fix the one known bug (Step 3) before you get to `flask db upgrade`, or it will fail.

---

## 0. Prerequisites

- Python 3.10+ on PATH (`python --version`)
- PostgreSQL installed and running (or Docker, if you'd rather run Postgres in a
  container)
- Node.js 18+ for the frontend (`node --version`)

---

## 1. Backend virtual environment

Open PowerShell in the `backend` folder:

```powershell
cd path\to\news-frontend\backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

---

## 2. PostgreSQL: create the database and user

If Postgres is already installed, open `psql` (or pgAdmin) and run:

```sql
CREATE USER newsrec WITH PASSWORD 'newsrec';
CREATE DATABASE newsrec OWNER newsrec;
```

If you'd rather use Docker instead of a local install:

```powershell
docker run --name newsrec-db -e POSTGRES_USER=newsrec -e POSTGRES_PASSWORD=newsrec -e POSTGRES_DB=newsrec -p 5432:5432 -d postgres
```

---

## 3. Configure `.env` — fix the driver mismatch here

Copy the example file if you haven't already:

```powershell
copy .env.example .env
```

**Known bug to fix:** your current `.env` has

```
DATABASE_URL=postgresql+pg8000://newsrec:newsrec@localhost:5432/newsrec
```

but `requirements.txt` only installs `psycopg2-binary`, not `pg8000`. SQLAlchemy
won't find the `pg8000` dialect driver and the connection will fail. Change that
line to:

```
DATABASE_URL=postgresql://newsrec:newsrec@localhost:5432/newsrec
```

(plain `postgresql://` uses psycopg2, which is already in requirements.txt — no
extra install needed).

While you're in `.env`, also worth doing before this goes anywhere near production:

- `JWT_SECRET_KEY` is still the placeholder `change-me-to-a-long-random-string` —
  fine for local dev, change it before deploying anywhere real.
- `NEWSAPI_KEY` can stay blank. Without it, article ingestion automatically falls
  back to a bundled mock dataset, so the rest of the system still works end-to-end.
  Add a real key later if you want live news.

---

## 4. Create the database tables

```powershell
flask db upgrade
```

This is the step that will fail immediately if Step 3 wasn't fixed.

---

## 5. Seed categories and pull in articles

```powershell
flask seed-categories
flask ingest-news
```

`ingest-news` uses NewsAPI if `NEWSAPI_KEY` is set, otherwise pulls from the bundled
mock article set — either way, you'll have articles in the database afterward.

---

## 6. The RL model

A trained policy already exists at `backend/rl/artifacts/bandit_policy.zip`, so you
can skip straight to Step 7. Retrain only if you want a fresh model (e.g. after
changing the reward function or feature schema):

```powershell
python -m rl.train
```

This trains for 150,000 timesteps against a simulated-user environment and takes a
few minutes on CPU. To confirm it actually beats a random baseline afterward:

```powershell
python -m rl.evaluate
```

---

## 7. Optional but recommended: seed interaction history + an admin user

Without any interaction history, every new user starts from an identical cold-start
context. Seeding synthetic interactions gives the feed something to personalize
against right away:

```powershell
flask seed-synthetic-interactions
flask create-admin you@example.com "Your Name" your-password
```

The admin account lets you log into the `/admin` analytics page in the frontend.

---

## 8. Run it

Two terminals, both from `backend/` and the frontend folder respectively:

```powershell
# terminal 1 (backend/, venv active)
flask run --port 5000
```

```powershell
# terminal 2 (frontend project root)
npm install
npm run dev
```

Make sure the frontend's `.env.local` (or `.env`) points at the real backend:

```
VITE_API_BASE_URL=http://127.0.0.1:5000/api
```

Open the Vite dev URL it prints (usually `http://localhost:5173`). The feed should
now be pulling live recommendations from the actual bandit policy, not mock data.

---

## 9. Verify it's really live, not mock

```powershell
curl http://localhost:5000/api/health
```

should return a 200. Then in the browser, open dev tools → Network tab, reload the
feed, and confirm requests are going to `127.0.0.1:5000/api/recommendations` and
returning real article IDs from your database (not the fixed 12-article mock set).
Click a couple of articles, refresh the feed, and you should start seeing the mix of
categories shift slightly — that's the exploration/exploitation blend in
`recommender.py` responding to logged interactions.

---

## Troubleshooting

- **`flask db upgrade` fails with a driver/dialect error** → you're still on the
  `pg8000` connection string from Step 3.
- **Connection refused on port 5432** → Postgres isn't running, or Docker container
  isn't started (`docker start newsrec-db`).
- **`flask` command not found** → the venv isn't activated in that terminal
  (`venv\Scripts\activate`).
- **Recommendations endpoint 500s** → check the Flask console output; `rl/policy.py`
  is written to fall back to a CTR baseline rather than crash if the model file is
  missing or corrupt, so a 500 here usually means a DB issue, not a model issue.
- **Frontend shows nothing / network errors** → confirm `VITE_API_BASE_URL` in the
  frontend's env file matches where Flask is actually running, and that CORS is
  enabled (it is, by default, in `app/__init__.py`).
