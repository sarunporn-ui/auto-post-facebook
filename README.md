# Automated Content OS — Human-in-the-Loop Approval

Turns a YouTube video or Facebook post into 5 distinct, publish-ready content
formats, with a human approval step (via a local web dashboard, or optionally
Telegram) in between ideation and generation. Built with Python + FastAPI.

## Pipeline

```
YouTube URL / Facebook URL or text
        │
        ▼
  Module 1: Ingestion Engine        src/ingestion
  (transcript / scrape / paste)
        │
        ▼
  Module 2: AI Brain + Persona      src/ai_brain
  (persona-matched topic ideas)
        │
        ▼
  Module 3: Approval Interface      src/approval, web/
  (dashboard or Telegram: pick topic → format → optional custom prompt)
        │
        ▼
  Module 4: Multi-Format Generators src/generators
  (1 of 5 formats, LLM-generated)
        │
        ▼
  Module 5: Publisher               src/publisher
  (Facebook Graph API / WordPress REST API)
```

## Project layout

```
content-os/
├── .env.example            # all required API keys/config
├── target_persona.json     # the Target Persona the AI Brain writes for
├── requirements.txt
├── setup.sh                # installs deps, creates .env, prints run commands
├── data/                   # JSON "database" + generated PDFs (gitignored)
├── web/
│   └── index.html          # local dashboard UI (served at /dashboard)
└── src/
    ├── config.py           # Settings loaded from .env
    ├── models.py           # RawContent, ContentTopic, ApprovalRequest, GeneratedContent
    ├── storage.py           # JSON-file JsonStore (swap for a real DB later)
    ├── stores.py            # singleton stores per entity
    ├── main.py              # FastAPI app — orchestration + dashboard endpoints
    ├── ingestion/
    │   ├── youtube_ingestor.py    # youtube-transcript-api, Whisper fallback
    │   └── facebook_ingestor.py   # OG-tag scrape or pasted text
    ├── ai_brain/
    │   ├── llm_client.py    # unified OpenAI / Anthropic / Gemini caller
    │   ├── persona.py       # loads target_persona.json
    │   └── brain.py         # raw content -> 3-5 topic ideas
    ├── approval/
    │   ├── service.py       # shared approve+generate logic (dashboard & webhook)
    │   ├── webhook.py       # FastAPI alternative for external automations (Airtable/Zapier)
    │   └── telegram_bot.py  # optional alternative: approve from your phone via Telegram
    ├── generators/
    │   ├── base.py                   # format registry + dispatcher
    │   ├── format1_long_article.py   # SEO long-form article (H1/H2/H3/TOC/CTA)
    │   ├── format2_social_post.py    # short hook post + image-gen prompt
    │   ├── format3_fb_offer.py       # Problem -> Solution -> Offer -> CTA
    │   ├── format4_pdf_leadmagnet.py # "N Ideas/Rules" PDF via WeasyPrint
    │   └── format5_tiktok_script.py  # timestamped 60s script
    └── publisher/
        ├── facebook_publisher.py     # Meta Graph API
        └── wordpress_publisher.py    # WordPress REST API
```

## Setup

```bash
./setup.sh
```

This creates a virtualenv, installs dependencies, and copies `.env.example`
to `.env`. Then:

1. Fill in `.env` (see below). The Target Persona itself doesn't need editing
   by hand — it's edited from the dashboard's "Your Persona" section anytime,
   in any language.
2. Start the API:
   ```bash
   source .venv/bin/activate
   uvicorn src.main:app --reload
   ```
3. Open **http://localhost:8000/dashboard** in a browser. That's the whole
   approval UI — no Telegram required.

   Prefer approving from your phone via Telegram instead? Fill in
   `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` in `.env` and run the bot as a
   separate process (it long-polls Telegram, so it doesn't share the uvicorn
   event loop):
   ```bash
   source .venv/bin/activate
   python -m src.approval.telegram_bot
   ```

**macOS note:** WeasyPrint (used for Format 4 PDFs) needs system libraries:
```bash
brew install pango cairo gdk-pixbuf libffi
```

## Environment variables (`.env.example`)

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` / `LLM_MODEL` | Which AI Brain LLM to use: `openai`, `anthropic`, or `gemini` |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` | LLM credentials |
| `WHISPER_MODEL` | Used only as a fallback when a YouTube video has no captions |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Human-in-the-loop approval bot |
| `APPROVAL_WEBHOOK_SECRET` | Shared secret for the `/webhook/approve` REST alternative |
| `META_PAGE_ID` / `META_PAGE_ACCESS_TOKEN` / `META_GRAPH_API_VERSION` | Facebook Page publishing |
| `WORDPRESS_URL` / `WORDPRESS_USERNAME` / `WORDPRESS_APP_PASSWORD` | Website publishing (use a WP Application Password, not your login password) |

## End-to-end flow (dashboard)

1. Open `/dashboard`, paste a YouTube link (or a Facebook post URL/text), click
   **Generate Ideas**. This ingests the content and runs the AI Brain,
   producing 3-5 topic ideas (usually 5-30 seconds, depending on the LLM).

   Prefer not to paste links at all? Use **"Auto-fetch new videos"**: turn it
   on, paste your channel URL, pick a check frequency. A background loop
   (`src/watch_service.py`) polls the channel via `yt-dlp`'s flat playlist
   extraction (no download), and automatically ingests + analyzes any video
   it hasn't seen before — new ideas just appear under "Pending ideas" on
   their own. "Check now" triggers an immediate check instead of waiting.
2. Under **Pending ideas**, click a topic, then click one of the 5 format
   cards, optionally type custom style/tone instructions, and click
   **Generate**.
3. The result appears under **Generated content** — copy the text, download
   the PDF (Format 4), or click **Publish to Website/Facebook** (Formats 1-3)
   to push it live via the WordPress/Meta Graph API credentials in `.env`.
   Formats 4-5 (PDF, TikTok script) are meant for manual distribution.

Prefer Telegram, or a REST automation (Airtable/Zapier)? Both are still
available: run `python -m src.approval.telegram_bot`, or call
`POST /webhook/approve` with header `X-Webhook-Secret` — both use the same
underlying generation logic as the dashboard.

## Dashboard layout

The board is 3 columns: **Ideas** (left, grouped by day — pick a topic and a
format, optionally add custom instructions, click Generate) → **Preview**
(middle — shows the real generated caption, plus a real DALL-E image for
Format 2 if `OPENAI_API_KEY` is set, otherwise just the image prompt text) →
**Publish** (right — pick platform(s), publish immediately, or set a date/time
to schedule; a background loop checks every minute and publishes anything
due, recording an error on the item if the platform credentials aren't
configured yet rather than retrying forever).

## Design notes / things to swap out as you scale

- **Storage** is a flat JSON-file store (`src/storage.py`) — deliberately
  simple for an MVP. Swap `JsonStore` for a real database once you need
  concurrent writers, querying, or multi-user support.
- **Facebook post scraping** only recovers Open Graph `title`/`description`
  meta tags for public posts (Facebook blocks full-body scraping without the
  Graph API or a logged-in session). For your own Page's posts, pasting the
  text directly into `/ingest/facebook` is more reliable.
- **Telegram bot runs by long-polling** in its own process for simplicity. For
  production, switch to webhook mode (`Application.run_webhook`) behind the
  same FastAPI app/reverse proxy.
