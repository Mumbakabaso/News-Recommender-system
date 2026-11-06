# Restarting the Project (Quick Reference)

This is the "everything's already set up, I just shut my computer down"
version — not the first-time install. You already have the venv, the
database, the migrations, and the trained model in place, so you're just
turning things back on, in order.

---

## 1. Start PostgreSQL

If Postgres runs as a Windows service, it likely started automatically on
boot — you can skip to Step 2. Check by opening **Services** (Win+R →
`services.msc`) and confirming "postgresql-x64-..." shows as Running.

If you're running it in Docker instead:

```powershell
docker start newsrec-db
```

## 2. Start the backend

Open a terminal (PowerShell) in the `backend` folder:

```powershell
cd path\to\news-frontend\backend
venv\Scripts\activate
flask run --port 5000
```

Leave this terminal open and running. You should see it print that it's
serving on `http://127.0.0.1:5000`.

Quick sanity check in a browser or second terminal:

```powershell
curl http://localhost:5000/api/health
```

A response back means the database connection and the app are both fine.
If this fails, Postgres probably isn't actually running — go back to
Step 1.

## 3. Start the frontend

Open a **second** terminal in the project root (not `backend`):

```powershell
cd path\to\news-frontend
npm run dev
```

Vite will print a local URL — usually `http://localhost:5173`. Open that
in your browser.

## 4. You're back up

Two terminals now need to stay open the whole time you're using it: one
running Flask (Step 2), one running Vite (Step 3). Closing either one
stops that half of the app.

Nothing else needs to be redone — the database tables, seeded articles,
your admin account, and the trained RL model (`bandit_policy.zip`) all
persist on disk between shutdowns. You will not need to re-run
`flask db upgrade`, `seed-categories`, `ingest-news`, or `rl.train` unless
you specifically want to reset or refresh that data.

---

## If something doesn't come back cleanly

- **`flask run` errors immediately on startup** → Postgres isn't actually
  running yet, or the venv wasn't activated in that terminal (you'd see
  `flask` reported as an unknown command if so).
- **Frontend loads but shows no articles / login fails** → check the
  Flask terminal for errors; also confirm `VITE_API_BASE_URL` in the
  frontend's `.env.local` still points at `http://127.0.0.1:5000/api`.
- **Port already in use** → something from a previous session didn't
  fully close. Find and close the old terminal/process, or restart your
  computer, then try again.
