# Automated Content OS

Multi-user web app: turn a YouTube video or Facebook post into 5 publish-ready
content formats — with a human approval step — then schedule them to **auto-post
to a Facebook Page each user connects themselves**. Python + FastAPI + SQLModel,
Supabase (Postgres + Auth + Storage), deployed on Railway.

## Pipeline

```
YouTube URL / Facebook URL or text
        ▼  src/ingestion      transcript / OG-scrape / pasted text
        ▼  src/ai_brain       persona-matched topic ideas (per-user Persona)
        ▼  web/ dashboard     pick topic → format → optional custom prompt
        ▼  src/generators     one of 5 formats, LLM-generated
        ▼  src/publisher      Facebook Page (per-user OAuth) / WordPress
```

## Local development

Runs in single-user **dev mode** (SQLite, no login) when Supabase env vars are
unset — good enough to work on the pipeline.

```bash
./setup.sh                       # venv + deps + .env
source .venv/bin/activate
uvicorn src.main:app --reload
open http://localhost:8000/dashboard
```

`target_persona.json` is only a *template* now — it seeds each new user's
persona row on first login; edit personas from the dashboard.

## Architecture

| Area | Module | Notes |
|---|---|---|
| Config | `src/config.py` | all env vars; `DATABASE_URL` picks SQLite vs Postgres |
| DB | `src/db.py`, `src/models.py` | SQLModel tables, every user-owned row has `user_id` |
| Data access | `src/repositories.py` | `user_id`-scoped `Repo[T]`; cross-user reads isolated in `*_all_*` |
| Auth | `src/auth.py` | verifies the Supabase JWT; dev mode = fixed local user |
| Facebook | `src/facebook/oauth.py` | server-side Login flow, per-user Page token (Fernet-encrypted, `src/crypto.py`) |
| Storage | `src/storage_client.py` | Supabase Storage for images/PDFs, local-file fallback |
| Background | `src/main.py` | `_schedule_loop` (60s, all users) auto-publishes due items; `_watch_loop` (5m) checks channels; `POST /internal/cron/tick` is a backup trigger |

`src/approval/telegram_bot.py` is the old single-user interface and is **not
wired** into the multi-user app.

## Deploying

See **DEPLOY.md** for the full checklist (Supabase project, Meta app, Railway).
Short version:

1. **Supabase**: create project → copy `DATABASE_URL` (pooler, `+psycopg`),
   `SUPABASE_URL`, anon key, service-role key, JWT secret → enable Email +
   Google auth → create a public Storage bucket `generated`.
2. **Meta app** (developers.facebook.com): add *Facebook Login*, set the OAuth
   redirect URI to `https://<your-app>/connect/facebook/callback`, add yourself
   + testers, copy App ID / Secret. Public users need Meta App Review later.
3. **Railway**: deploy this repo (Dockerfile), set every env var from
   `.env.example`, generate `FERNET_KEY`. Auto-deploys on push to `main`.
