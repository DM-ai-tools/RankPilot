# Deploying RankPilot on Railway

This guide walks through deploying the full RankPilot stack on [Railway](https://railway.com) using the GitHub repository.

---

## Architecture on Railway

| Service | Root Directory | Notes |
|---------|---------------|-------|
| **backend** | `backend/` | FastAPI + APScheduler, Python 3.12 |
| **frontend** | `frontend/` | React + Vite, served as static files |
| **Postgres** | Railway plugin | PostgreSQL 16 with pgvector |
| **Redis** | Railway plugin | Redis 7 (for APScheduler job queue) |

### Critical: Railpack / Metal — “could not determine how to build the app”

If the service builds from the **repository root** with **Root Directory empty**, **Railpack** only sees folders `backend/` and `frontend/` and **no** `package.json` or `pyproject.toml` at the root, so it exits with *Railpack could not determine how to build the app*. Nested `frontend/railway.toml` is **skipped** in that mode (Railway only accepts a config file rooted at the repo root unless you set paths in the UI).

You can fix this in either way:

1. **Root Directory (recommended)**  
   Set **Settings → Source → Root Directory** to **`backend`** for the API service and **`frontend`** for the SPA. Each service then only sees one stack (Python vs Node), which avoids Railpack confusion and avoids the SPA accidentally building as Python.

2. **Dockerfile at repo root (API only)**  
   The **root `Dockerfile`** builds the **API** from `backend/` + `infra/sql/` when Root Directory is empty. Use that **only** for the backend service. Do **not** point the SPA service at the root Dockerfile.

**SPA service build:** Set **Root Directory** = **`frontend`**, **Dockerfile path** = **`Dockerfile`** (the file inside `frontend/`). The SPA image is Node + `serve` only — if deploy logs show **SQLAlchemy / asyncpg / uvicorn**, the wrong service root or Dockerfile is selected (you are running the API on the “front-end” service).

You do **not** need a local Postgres machine; use Railway’s **PostgreSQL** plugin only. The app reads `DATABASE_URL` from Railway automatically.

### One GitHub repo, two Railway services (recommended)

Railway shows **one line to GitHub per service** you create — that is normal. The **same** repo can power **multiple** services:

| Service name (example) | Role | How to create |
|------------------------|------|----------------|
| **RankPilot** (existing) | API | **Root Directory** = **`backend`**, or empty root + root **`Dockerfile`** (see above). |
| **RankPilot-Web** (new) | SPA | **+ New** → same repo → **Root Directory** = **`frontend`** → **Dockerfile path** = **`Dockerfile`**. Clear any **Custom start command** that runs `uvicorn`. |

Build logs that show **Python / Postgres** on a service named “front-end” mean that service is **not** building from `frontend/` — fix Root Directory and Dockerfile as in the table.

---

## Step 1 — Create a New Railway Project

1. Go to [railway.com](https://railway.com) → **New Project**
2. Choose **Deploy from GitHub repo** → select `DM-ai-tools/RankPilot`

---

## Step 2 — Add PostgreSQL and Redis Plugins

In your project dashboard:
1. Click **+ New** → **Database** → **Add PostgreSQL**
2. Click **+ New** → **Database** → **Add Redis**

Railway will auto-inject `DATABASE_URL` and `REDIS_URL` into services that share the same project.

---

## Step 3 — Configure the Backend Service

1. In the project, click **+ New** → **GitHub Repo** → select `DM-ai-tools/RankPilot`
2. Set **Root Directory** to `backend`
3. Railway will auto-detect Python via `pyproject.toml` and use `backend/railway.toml`

### Environment Variables (Backend)

Add these in **Settings → Variables** for the backend service:

```
# Auto-provided by Railway plugins (no need to set manually):
DATABASE_URL       ← from PostgreSQL plugin
REDIS_URL          ← from Redis plugin

# Required — set these yourself:
JWT_SECRET_KEY     = <generate with: openssl rand -hex 32>
CORS_ORIGINS       = https://your-frontend.up.railway.app

# API keys (add whichever you use):
DATAFORSEO_LOGIN         = your_dataforseo_email
DATAFORSEO_PASSWORD      = your_dataforseo_password
GOOGLE_PLACES_API_KEY    = AIza...
ANTHROPIC_API_KEY        = sk-ant-...
OPENAI_API_KEY           = sk-...
FIRECRAWL_API_KEY        = fc-...
GOOGLE_REDIRECT_BASE_URL = https://your-backend.up.railway.app

# Optional:
SENDGRID_API_KEY         = SG...
TWILIO_ACCOUNT_SID       = AC...
TWILIO_AUTH_TOKEN        = ...
TWILIO_FROM              = +1...
STRIPE_SECRET_KEY        = sk_live_...
```

> **Tip:** Railway auto-links `DATABASE_URL` and `REDIS_URL` from the plugins. You just need to reference them with `${{Postgres.DATABASE_URL}}` and `${{Redis.REDIS_URL}}` in the variable editor.

---

## Step 4 — Configure the Frontend Service

1. Click **+ New** → **GitHub Repo** → select `DM-ai-tools/RankPilot`
2. Set **Root Directory** to `frontend`
3. Railway will auto-detect Node.js via `package.json` and use `frontend/railway.toml`

### Environment Variables (Frontend)

```
VITE_API_BASE_URL = https://your-backend.up.railway.app
```

> **Important:** Replace `your-backend.up.railway.app` with the actual Railway domain of your backend service (found in the backend service's **Settings → Networking → Public Domain**).

---

## Step 5 — Run Database Migrations

After both services are deployed and the Postgres plugin is running:

1. Open the **backend** service in Railway
2. Go to **Settings → Deploy** → click **New Deploy** (or open the Railway shell)
3. Or use the Railway CLI:

```bash
railway run --service backend python scripts/apply_migrations.py
```

This applies all SQL files in `infra/sql/` in order.

---

## Step 6 — Seed the Admin User

SSH into the backend service shell (Railway → service → **Shell** tab) and run:

```bash
python scripts/mint_jwt.py
```

Then insert the admin user into Postgres via the Railway Postgres plugin shell:

```sql
INSERT INTO rp_clients (id, business_name, username, hashed_password, email)
VALUES (
  gen_random_uuid(),
  'Traffic Radius',
  'admin',
  -- generate with: python -c "from passlib.hash import bcrypt; print(bcrypt.hash('yourpassword'))"
  '$2b$12$...',
  'admin@trafficradius.com.au'
);
```

---

## Step 7 — Set Custom Domains (Optional)

In each service → **Settings → Networking**:
- Generate a Railway domain (free `*.up.railway.app`) or add your own domain

Make sure to update:
- `VITE_API_BASE_URL` in the frontend service to the backend's domain
- `CORS_ORIGINS` in the backend service to the frontend's domain
- `GOOGLE_REDIRECT_BASE_URL` in the backend if using Google OAuth

---

## Environment Variable Reference

| Variable | Where | Required | Notes |
|----------|-------|----------|-------|
| `DATABASE_URL` | Backend | Yes | Auto from Postgres plugin |
| `REDIS_URL` | Backend | Yes | Auto from Redis plugin |
| `JWT_SECRET_KEY` | Backend | Yes | Min 32 chars random string |
| `CORS_ORIGINS` | Backend | Yes | Frontend Railway URL |
| `VITE_API_BASE_URL` | Frontend | Yes | Backend Railway URL |
| `DATAFORSEO_LOGIN` | Backend | For scans | DataForSEO email |
| `DATAFORSEO_PASSWORD` | Backend | For scans | DataForSEO password |
| `GOOGLE_PLACES_API_KEY` | Backend | For business lookup | Google Cloud |
| `ANTHROPIC_API_KEY` | Backend | For AI features | Anthropic console |
| `FIRECRAWL_API_KEY` | Backend | For citations | Firecrawl dashboard |
| `GOOGLE_REDIRECT_BASE_URL` | Backend | For GBP OAuth | Backend public URL |

---

## Troubleshooting

**“Deployment failed during build process” / build ~5s then FAILED**

→ Almost always: **Root Directory** is empty or wrong. Set it to `backend` for the API service and `frontend` for the web app, then redeploy. Open **Deployments → failed row → View logs** and confirm Nixpacks is running from the correct folder (you should see `pyproject.toml` or `package.json` at the build root, not both at once).

**Railpack: “could not determine how to build the app” / skipping `frontend/railway.toml`**

→ With **Root Directory empty**, Railpack only looks at the repo root (no `pyproject.toml` / `package.json` there). Set **Root Directory** to **`backend`** or **`frontend`**, or use the **root `Dockerfile`** for the API only (see the “Critical” section above).

**“Front-end” deploy logs show SQLAlchemy / asyncpg / `app.workers`**

→ That service is running the **Python API**, not the Vite SPA. Open **Settings → Source / Build**: set **Root Directory** to **`frontend`**, **Dockerfile** to **`Dockerfile`**, remove **Start Command** overrides like `uvicorn …`, then redeploy.

**Build fails with "No start command"**
→ Ensure the service Root Directory is set to `backend` or `frontend` respectively.

**`DATABASE_URL` format error**
→ The app auto-converts `postgresql://` (Railway format) to `postgresql+asyncpg://`. If you see a validator error, check the URL starts with `postgresql://` or `postgresql+asyncpg://`.

**CORS errors in browser**
→ Set `CORS_ORIGINS` in the backend to exactly match the frontend's Railway URL (e.g. `https://rankpilot-frontend.up.railway.app`).

**Frontend shows blank page / API errors**
→ Verify `VITE_API_BASE_URL` is set on the frontend service (not backend). This value is baked in at build time by Vite.

**Maps scan jobs stuck**
→ The app auto-resets `running` jobs to `queued` on startup. Restart the backend service if jobs appear stuck.

**Deploy logs: `ConnectionRefusedError` / `[Errno 111] Connection refused` when connecting to Postgres**

→ The API container is **not** using Railway’s Postgres URL (often it still has `localhost` from a copied `.env` or an unset variable). Fix it on the **RankPilot** (backend) service:

1. Open your **Postgres** plugin in the same Railway project and confirm it exposes **`DATABASE_URL`**.
2. Open **RankPilot** → **Variables**.
3. Add or replace **`DATABASE_URL`**: use **Variable Reference** (recommended) so it always matches the plugin, e.g. click **Reference** → choose your Postgres service → **`DATABASE_URL`**. Railway will insert a value like `${{ Postgres.DATABASE_URL }}` (exact name depends on how you named the Postgres service).
4. Add **`REDIS_URL`** the same way from your **Redis** service if the worker uses it.
5. **Remove** any manual `DATABASE_URL` that points to `localhost` or `127.0.0.1` — inside Docker, “localhost” is the container itself, not Railway Postgres.
6. **Redeploy** the RankPilot service.

After Postgres is reachable, run migrations once (Railway **Shell** on the API service): `python scripts/apply_migrations.py`.

---

## Splitting into two GitHub repositories (optional)

Use this only if you want **separate** repos (e.g. `RankPilot-api` and `RankPilot-web`). You can keep **one** repo and two Railway services with different Root Directories instead.

### Backend-only repo

From your machine, in the **monorepo** folder:

```bash
git fetch origin
git subtree split -P backend -b rankpilot-backend-only
```

Create an empty GitHub repo (e.g. `DM-ai-tools/RankPilot-api`), then:

```bash
git remote add api https://github.com/DM-ai-tools/RankPilot-api.git
git push api rankpilot-backend-only:main
```

Then on GitHub, set the default branch to `main` if needed.

**SQL migrations:** `git subtree` only includes the `backend/` tree. Copy SQL from the monorepo into the new repo **once**:

- Copy the folder `infra/sql` from the monorepo into **`backend/infra/sql`** in a fresh clone of `RankPilot-api` (repo root should look like `app/`, `scripts/`, `pyproject.toml`, `infra/sql/`, …).

`scripts/apply_migrations.py` looks for `infra/sql` next to the backend root first, then falls back to the monorepo layout.

**Railway:** connect `RankPilot-api`, leave **Root Directory empty** (repo root *is* the backend).

### Frontend-only repo

```bash
git subtree split -P frontend -b rankpilot-frontend-only
```

Create `DM-ai-tools/RankPilot-web` (empty), then:

```bash
git remote add web https://github.com/DM-ai-tools/RankPilot-web.git
git push web rankpilot-frontend-only:main
```

**Railway:** connect `RankPilot-web`, Root Directory empty. Set `VITE_API_BASE_URL` to your backend’s public URL.

### After the split

- **Backend variables:** same as Step 3 (`DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY`, API keys, `CORS_ORIGINS` = frontend URL).
- **Frontend variables:** `VITE_API_BASE_URL` = backend URL.
