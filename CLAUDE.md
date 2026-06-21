# StreamFader — CLAUDE.md
*Re-entry: StreamFader*

## What This Is
Streaming content ranker with a DJ-style crossfader.
Blends critic (RT/Metacritic) and audience (IMDB) scores in real time.
Port 5556.

## Status
🟢 Live on GitHub — stream.creativekonsoles.com

## Architecture
- `app.py`     — Flask server (port 5556)
- `engine.py`  — TMDb + OMDb + TVmaze fetch + caching (6h TTL)
- `templates/index.html` — Crossfader UI, genre pills, card grid

## Fader Logic
blend = critic × (1 - fader_pos) + audience × fader_pos
Left = critics (RT + MC avg) | Right = audience (IMDB × 10)

## API Keys Required
- TMDB_API_KEY
- OMDB_API_KEY

## AI Keys
- `OPENAI_API_KEY` — required for Mood Magic (GPT-4o); copied from ~/represented/.env
- `ANTHROPIC_API_KEY` — present but balance depleted as of 2026-06-21

## ⚠️ Railway + OpenAI gotcha
The OpenAI **SDK (httpx) throws `Connection error.` on Railway egress** — works
locally, fails in prod. `requests` works fine on Railway (TMDb/OMDb prove it).
Fix: call OpenAI via the `openai_chat()` helper in app.py (REST + requests),
NOT the `openai` SDK. Use this pattern for any future OpenAI calls in Railway apps.

## Next Steps
- [ ] Add streaming platform filter
- [ ] Dark/light mode toggle
- [x] Mobile polish pass — DONE 2026-06-21

---
## Last Session (2026-06-21)
- **Reddit feedback actioned**: removed over-the-top 3D flip animation → simple fadeIn; livePulse slowed; fader label glow reduced.
- **Content type selector**: "I want to watch: Movies / All / TV Shows" bar added above genre pills with localStorage persistence. Single-col mode collapses two-col grid.
- **Mobile breakpoint**: two-col collapse moved from 900px → 1024px for better tablet experience.
- **Mood Magic built**: full feature — header button, fullscreen overlay picker (Genre × Vibe dropdowns, 40+ options each), GPT-4o backend route `/api/mood-magic`, two-card side-by-side reveal (movie + show), SF scores, AI reason in teal, synopsis, trailer links, Seen it / Skip / Save buttons, pair cycling (5 rounds), "Try a new combo" end screen. Uses `OPENAI_API_KEY` (GPT-4o first, Anthropic fallback).
- Committed + pushed to papjamzzz/Stream-Fader as `a980975`.
- **Next**: Railway deploy with `OPENAI_API_KEY` env var set so Mood Magic works in prod.

---
## Last Session (2026-06-21) — Hero + Railway fix
- **Genre pills removed** → replaced with a **Mood Magic hero** card in the same spot (animated spark, gradient wordmark, Find My Match CTA). Genre JS left dormant/harmless.
- **Content type selector** reduced to **Movies / TV Shows** (dropped "All"); Movies default, legacy 'all' coerces to Movies.
- **Mood Magic fixed in prod** — OpenAI SDK/httpx `Connection error.` on Railway. New `openai_chat()` helper (REST via requests) used in `mood_magic` + `streamfinder`. Verified live: 5+5 results. See Railway gotcha above.
- Commits `0c2b18a`, `7a4144a` pushed; Railway redeployed + confirmed.

---
## Last Session (2026-06-21) — Mobile pass
- **Header**: hid Help + Share on mobile; Mood Magic + Saved collapse to icon-only via `.hdr-btn-label` spans hidden at ≤480px
- **Genre pills**: single horizontal scrollable row (`flex-wrap: nowrap`, `overflow-x: auto`, hidden scrollbar)
- **Cards**: forced 1-col grid with `!important` to override higher-specificity `.two-col.single-col .card-list` selector
- **TV Shows section** verified: full-width cards, poster + title + year + score + actions all visible
- Committed `f511320`, pushed to papjamzzz/Stream-Fader
