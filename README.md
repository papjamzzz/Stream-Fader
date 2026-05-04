# StreamFader

**A live movie and TV discovery app powered by a critic-to-audience crossfader.**

🌐 **[stream.creativekonsoles.com](https://stream.creativekonsoles.com/)** — Public Beta

---

## What It Does

StreamFader lets you slide between two scoring philosophies in real time. Pull the fader left and critics take over — Rotten Tomatoes and Metacritic dominate the rankings. Pull it right and the audience wins — IMDb, Letterboxd, and RT Audience scores push crowd favorites to the top. Everything in between is a blend you control.

No accounts. No algorithms deciding for you. Just the fader.

---

## Product Snapshot

| | |
|---|---|
| **Status** | Public Beta / Launch Candidate |
| **Live URL** | https://stream.creativekonsoles.com/ |
| **Stack** | Python · Flask · Vanilla JS |
| **Data** | TMDb · MDBList · Trakt · TVmaze |
| **AI (optional)** | Anthropic · OpenAI · Gemini |
| **Part of** | [Creative Konsoles](https://creativekonsoles.com) |

---

## Key Features

- **Critic ↔ Audience Fader** — real-time score blending across all visible titles
- **Movie & TV Discovery** — separate ranked feeds updated every 6 hours
- **Genre Filtering** — pill-based multi-select genre filter
- **Watch Queue** — save titles to a persistent local watchlist
- **Seen It / No Thanks** — personalize your feed by dismissing titles you've watched or skipped
- **Share My Stream** — share your current fader position and genre filters via link
- **StreamFinder** — AI-assisted discovery from a three-word prompt (Claude / GPT / Gemini)
- **Trailer Lookup** — watch trailers in-app via TMDb
- **Cast & Actor Browse** — view full cast and browse an actor's filmography
- **5i AI Top Pick** — daily consensus recommendation from multiple AI personas
- **Brevo Email Capture** — optional newsletter signup (requires `BREVO_API_KEY`)
- **Anonymous Analytics** — lightweight engagement tracking, no PII stored
- **SEO Ready** — Open Graph tags, `robots.txt`, `sitemap.xml`

---

## How the Fader Works

```
SF Score = critic_score × (1 − fader) + audience_score × fader
```

- **Critic pole (left):** Rotten Tomatoes Tomatometer + Metacritic, averaged
- **Audience pole (right):** RT Audience Score (50%) + IMDb (25%) + Letterboxd (15%) + Trakt (10%)
- Titles with no real audience data are penalized at the audience pole to prevent pre-release films from ranking above established crowd favorites

---

## Data Sources

| Source | Used For |
|---|---|
| **TMDb** | Catalog, posters, streaming providers, trailers, cast, genres |
| **MDBList** | RT Tomatometer, Metacritic, RT Audience, Letterboxd, Trakt scores |
| **Trakt** | Trending signals and supplemental scores |
| **TVmaze** | New TV releases dropped this week on streaming |
| **Anthropic / OpenAI / Gemini** | StreamFinder recommendations, Top Pick (all optional) |
| **Brevo** | Email capture (optional) |

---

## Project Status

StreamFader is in **public beta**. Core features are stable and live. The scoring engine, fader logic, and personalization layer are all production-ready. Active development continues on the roadmap below.

---

## Roadmap

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full plan.

**Near term:**
- Watch Heat / trending proxy layer
- "Why this ranked here" explanations
- Stronger streaming provider badges
- StreamFinder grounded in cached candidates
- Improved Open Graph share cards

**Later:**
- Cross-device profiles
- Weekly personalized picks email
- Advanced mood modes

---

## Tech Stack

- **Backend:** Python 3.11+, Flask, Gunicorn
- **Frontend:** Vanilla JS, CSS custom properties, no frameworks
- **Caching:** File-based JSON cache (6h TTL for content, 7d for scores)
- **Deployment:** Railway (production), compatible with any Python host

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `TMDB_API_KEY` | ✅ | TMDb v3 API key |
| `MDBLIST_API_KEY` | ✅ | MDBList key for RT/MC/Letterboxd/Trakt scores |
| `TRAKT_CLIENT_ID` | Recommended | Trakt trending data |
| `TRAKT_CLIENT_SECRET` | Recommended | Trakt auth |
| `ANTHROPIC_API_KEY` | Optional | Claude for StreamFinder + Top Pick |
| `OPENAI_API_KEY` | Optional | GPT for StreamFinder |
| `GOOGLE_API_KEY` | Optional | Gemini for StreamFinder |
| `BREVO_API_KEY` | Optional | Email capture via Brevo |

Copy `.env.example` to `.env` and fill in your keys.

---

## Local Development

```bash
git clone https://github.com/papjamzzz/Stream-Fader.git
cd Stream-Fader
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your keys
python app.py
```

Open http://localhost:5556

---

## Privacy Notes

See [docs/PRIVACY.md](docs/PRIVACY.md). StreamFader does not collect personal information. Analytics are anonymous. No user accounts are required.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Issues and PRs welcome.

---

## License

MIT — see [LICENSE](LICENSE).
Copyright © 2026 Jeremiah S. Smith

---

## Part of Creative Konsoles

StreamFader is one project in the [Creative Konsoles](https://creativekonsoles.com) ecosystem — a suite of AI-powered tools built for discovery, creativity, and independent thinking.
