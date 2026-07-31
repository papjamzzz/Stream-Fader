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
- [ ] If you want to use `/api/patch-scores`, `/api/score-debug`, `/api/stats`, `/api/watchlist` (GET), or `/api/content?force=true` again, set `ADMIN_TOKEN` in Railway env vars and pass it as `?admin_token=...` or `X-Admin-Token` header — they now 404/lock by default (see 2026-07-31 session)
- [x] Mobile polish pass — DONE 2026-06-21
- [x] Pre-share audit + fixes — DONE 2026-07-11
- [x] Security/cost audit — DONE 2026-07-31

---
## Last Session (2026-07-31) — Security + cost audit (repo-wide)
- **Full audit** of live production app for the pattern found across sibling repos this session (exposed secrets, unauthenticated debug endpoints, cost-exposure endpoints, missing security headers, unpinned deps). Confirmed: no secrets ever committed to git history (checked `.env`, `git log --all`), `.gitignore` already solid.
- **Unauthenticated debug/rebuild endpoints locked down**: `/api/patch-scores`, `/api/score-debug`, `/api/content?force=true` — none used by the live frontend (verified via grep), yet `force=true` bypassed the 6h cache and triggered a full synchronous TMDb/OMDb/MDBList rebuild for anyone who found the query param. Added fail-closed `_is_admin()` gate (`ADMIN_TOKEN` env var). Commit `4cc8ff4`.
- **Unauthenticated data-dump endpoints locked down**: `GET /api/watchlist` (returned every visitor's saved titles — it's a single shared file, not scoped per session) and `/api/stats` (internal engagement metrics). Same admin gate. Commit `b007b81`.
- **Security headers added**: X-Content-Type-Options, X-Frame-Options, Referrer-Policy via `after_request`. Skipped CSP — page relies on large inline `<script>` blocks, would need a nonce rework. Verified locally (homepage + `/api/content` still serve fine). Commit `9cfe5ff`.
- **Cost protection on AI endpoints**: `/api/mood-magic` and `/api/streamfinder` call paid AI APIs (GPT-4o, Claude Haiku, Gemini Flash) per request with zero throttling. Added in-memory per-IP rate limit (10 calls / 5 min → 429). Process-local, resets on deploy — good enough to stop scripted abuse, not a real distributed limiter. Commit `f7ede02`.
- **Removed unused `openai` package** from requirements.txt — never imported anywhere (app uses `openai_chat()` REST helper instead, per the Railway gotcha above). Commit `96c6f4a`.
- **README fix**: corrected "no PII stored" claim (raw IP is stored per event in `data/events.jsonl` for abuse detection) and added missing Mood Magic feature entry. Commit `c10778a`.
- **Flagged, not fixed**: requirements.txt still uses `>=` ranges for flask/requests/anthropic/gunicorn/google-generativeai — didn't pin to exact versions since there's no lockfile and no way to confirm what Railway actually has deployed right now; pinning blind could change production behavior on next deploy without warning. If you want this hardened, check installed versions on the actual Railway instance first.
- All 6 commits pushed to `papjamzzz/Stream-Fader` main directly (no PR), verified `git log`/`git push` succeeded each time.
- **Next**: nothing urgent left from this pass. If Mood Magic/StreamFinder usage looks throttled unexpectedly, it's the new rate limiter (10 req / 5 min per IP) — bump `max_calls`/`window` in `_rate_limited()` calls in `app.py` if legitimate traffic needs more headroom.

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
