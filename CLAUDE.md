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
- [x] Pre-share audit + fixes — DONE 2026-07-11

---
## Last Session (2026-07-11) — Pre-share audit + fixes
- **Full audit** (backend, frontend, live prod) before sharing the site with someone. Found and fixed:
  - **Cross-user data leak**: `/api/preference`/`/api/preferences` had no per-user scoping — everyone's seen/skip signals shared one global file and fed into everyone's genre ranking. Now scoped by `session_id` (the existing `sf_session_id` localStorage value); unscoped reads return `[]`, unscoped writes 400.
  - **Unescaped HTML injection**: titles with quotes (e.g. `"Wuthering Heights"`) broke poster `alt` attributes; Mood Magic's AI-generated `reason` text was injected into `innerHTML` completely raw (self-XSS risk via direct API calls). Added `escapeHtml()`, applied everywhere title/overview/reason hits `innerHTML`.
  - **Content filter leaks**: anime exclusion only applied on the TMDb ingestion path, not TVmaze/Trakt — Dorohedoro was slipping through. AEW Dynamite/WWE shows slipped through everywhere since TMDb mislabels wrestling as scripted Action/Drama (no genre signal) — added a title-keyword check.
  - **Stale cache risk**: cache only refreshed when a real visitor hit `/api/content`; during a quiet stretch it sat 32h+ stale. Added an in-process periodic refresh (30 min check, file-locked across gunicorn's 4 workers) so it self-heals with zero traffic.
  - **Minor**: `/api/streamfinder` could 500 on a non-numeric `fader` value — now falls back to 50.
- All fixes committed (`4f09654`), pushed, Railway auto-deployed and verified live (new deployment `f423cca0`): preferences properly scoped, wrestling/anime gone from catalog, cache fresh.
- **Next**: none of this is urgent — app is solid to share as-is.

---
## Last Session (2026-06-21)
- **Reddit feedback actioned**: removed over-the-top 3D flip animation → simple fadeIn; livePulse slowed; fader label glow reduced.
- **Content type selector**: "I want to watch: Movies / All / TV Shows" bar added above genre pills with localStorage persistence. Single-col mode collapses two-col grid.
- **Mobile breakpoint**: two-col collapse moved from 900px → 1024px for better tablet experience.
- **Mood Magic built**: full feature — header button, fullscreen overlay picker (Genre × Vibe dropdowns, 40+ options each), GPT-4o backend route `/api/mood-magic`, two-card side-by-side reveal (movie + show), SF scores, AI reason in teal, synopsis, trailer links, Seen it / Skip / Save buttons, pair cycling (5 rounds), "Try a new combo" end screen. Uses `OPENAI_API_KEY` (GPT-4o first, Anthropic fallback).
- Committed + pushed to papjamzzz/Stream-Fader as `a980975`.
- **Next**: Railway deploy with `OPENAI_API_KEY` env var set so Mood Magic works in prod.

---
## Last Session (2026-06-21) — Mobile tighten v2
- **Header**: StreamFader now centered in the open space, clear of the ✦ button (added `.hdr-left/.hdr-center/.hdr-right` classes, mobile-only re-center; smaller wordmark clamp).
- **Card buttons**: icon-only **✓ / ✗** circular buttons stacked in a slim column on mobile (`.dismiss-label` hidden ≤480px; desktop keeps full text). Title/year/🍅/⭐ no longer cut off.
- **Legend strip kept** but rebuilt as "Tap ✓ Seen it · ✗ No thanks" with matching colored `.hb-key` chips, slimmed to one line.
- **Removed** the "Tell us your vibe" hero subline → hero is a compact single row.
- **Shrunk** the giant MOVIES/TV section headers (`.col-section-head/-logo/-title`), tightened fader padding + thumb (65→52px).
- Result: first movie card is fully above the fold (was 461–571px in 844px viewport). Verified mobile + desktop, ✓ button still dismisses. Commit `5ccf78e`.

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
