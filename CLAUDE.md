# StreamFader — Project Re-Entry File
*Claude: read this before touching anything.*

---

## What This Is
A local streaming aggregator dashboard that blends critic + audience scores via a DJ-style crossfader.
- Top 5 Movies + Top 5 TV Shows debuted on major streaming in the last 90 days
- THE FADER: left=100% critic score, right=100% audience score, middle=sweet spot
- Genre filtering, live re-ranking as fader moves
- Heavy eye candy. The fader IS the product.

## Re-Entry Phrase
> "Re-entry: StreamFader"

## Data Sources
- **TMDb API** (free) — movie/TV data, streaming platform availability, posters
- **OMDb API** (free, 1000/day) — Rotten Tomatoes critic %, Metacritic, IMDB scores
- Critic score = avg(RT Tomatometer, Metacritic)
- Audience score = IMDB rating × 10
- Cache: data/cache.json, 3-hour TTL

## Major Streaming Platforms Tracked
Netflix (8), Prime Video (119), Apple TV+ (350), Disney+ (337),
Hulu (15), Paramount+ (531), Max (1899), Peacock (386)

## Stack
- Python + Flask, port 5556, host 127.0.0.1
- Inter font, custom CSS variables — no frameworks
- Color palette: critics=blue (#4fc3f7), audience=amber (#ffb74d), mid=purple (#c678dd)

## File Structure
```
streamfader/
├── app.py              ← Flask (port 5556)
├── engine.py           ← TMDb + OMDb + caching
├── templates/
│   └── index.html      ← Full dashboard + fader UI
├── static/             ← logo.png, logo2.png
├── data/               ← cache.json (auto-generated)
├── requirements.txt
├── launch.command
├── Makefile
├── .env                ← TMDB_API_KEY + OMDB_API_KEY
└── .env.example
```

## API Keys Needed (both free)
- TMDb: https://www.themoviedb.org/settings/api
- OMDb: https://www.omdbapi.com/apikey.aspx
Drop both into .env file.

## Run
```bash
cd ~/streamfader && make run
```

## GitHub
- Repo: papjamzzz/stream-fader
- Push: cd ~/streamfader && git add . && git commit -m "msg" && git push origin main

## Current Status
🔨 Initial build — just created

## What's Next
- [ ] User adds API keys to .env
- [ ] Add logo.png + logo2.png to static/
- [ ] Test with live data
- [ ] Genre filter polish

---
*Last updated: 2026-03-10*
