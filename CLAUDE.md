# StreamFader — CLAUDE.md
*Re-entry: StreamFader*

## What This Is
Streaming content ranker with a DJ-style crossfader.
Blends critic (RT/Metacritic) and audience (IMDB) scores in real time.
Port 5556.

## Status
🟢 Live on GitHub

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

## Next Steps
- [ ] Add watchlist persistence
- [ ] Add streaming platform filter
- [ ] Dark/light mode toggle
