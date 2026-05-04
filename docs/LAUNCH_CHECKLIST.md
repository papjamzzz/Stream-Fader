# Launch Checklist

## Repo

- [ ] README current and accurate
- [ ] All data source claims verified against engine.py
- [ ] No secrets committed (check with `git log -p | grep -i "api_key\|secret\|token"`)
- [ ] `.env.example` current and complete
- [ ] `.gitignore` covers data/, .env, cache files, subscriber lists

## App

- [ ] sitemap.xml verified at /sitemap.xml
- [ ] robots.txt verified at /robots.txt
- [ ] Open Graph tags verified (title, description, image, url)
- [ ] Mobile hero layout checked on real device
- [ ] Share link generates correct URL with fader position
- [ ] Analytics events firing (check /api/track)
- [ ] Fader resorting confirmed working at both poles
- [ ] StreamFinder returns results (at least one AI key configured)

## GitHub

- [ ] Repo pinned to Creative Konsoles profile
- [ ] Screenshot or GIF added to README
- [ ] Topics/tags set (flask, python, movies, streaming, ai)
- [ ] LICENSE present
- [ ] CONTRIBUTING.md present
- [ ] SECURITY.md present

## Launch Distribution

- [ ] Product Hunt listing drafted
- [ ] Hacker News Show HN post drafted
- [ ] Reddit post drafted (r/Python, r/webdev, r/movies)
- [ ] X/Twitter post drafted
- [ ] LinkedIn post drafted
- [ ] Creative Konsoles newsletter queued
