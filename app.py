import threading, os, requests, json, hashlib
from datetime import datetime
from flask import Flask, render_template, jsonify, request
from engine import get_top_content, get_cached_content, generate_top10

TMDB_KEY = os.getenv('TMDB_API_KEY', '')

app = Flask(__name__)

# ── Background refresh ───────────────────────────────────────────────────────
_refreshing = False
_refresh_lock = threading.Lock()

def _background_refresh():
    global _refreshing
    if _refreshing:
        return
    with _refresh_lock:
        _refreshing = True
        try:
            get_top_content(force=True)
        except Exception:
            pass
        finally:
            _refreshing = False

_top10_generating = False
_top10_lock = threading.Lock()

def _background_top10():
    global _top10_generating
    if _top10_generating:
        return
    with _top10_lock:
        _top10_generating = True
        try:
            cached = get_cached_content()
            if cached:
                movies = cached.get('movies', [])
                tv     = cached.get('tv', [])
                if movies or tv:
                    generate_top10(movies, tv)
        except Exception:
            pass
        finally:
            _top10_generating = False

def _startup():
    """Warm content cache, then generate Top 12 once content is ready."""
    get_top_content(force=False)
    _background_top10()

# Pre-warm cache on startup so the first real user never hits a cold fetch
threading.Thread(target=_startup, daemon=True).start()

# ── Routes ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/content')
def content():
    force = request.args.get('force', 'false') == 'true'

    if force:
        try:
            return jsonify(get_top_content(force=True))
        except Exception as e:
            app.logger.error(f"Forced content fetch failed: {e}")
            return jsonify({'movies': [], 'tv': [], 'error': 'fetch_failed', 'fetched_at': None}), 500

    # Stale-while-revalidate: return whatever cache exists immediately,
    # kick off a background refresh if the data is stale.
    cached = get_cached_content()
    if cached:
        if cached.get('_stale'):
            threading.Thread(target=_background_refresh, daemon=True).start()
        return jsonify(cached)

    # No cache yet — kick off background build and tell the client to retry.
    # Never block a request waiting 60s for a cold fetch (gunicorn timeout killer).
    threading.Thread(target=_background_refresh, daemon=True).start()
    return jsonify({'movies': [], 'tv': [], 'loading': True, 'fetched_at': None})

@app.route('/api/top10')
def top10():
    """Return 5-persona AI consensus Top 12 Movies + Top 12 Series."""
    cached = get_cached_content()
    if not cached:
        return jsonify({'error': 'no_data', 'generating': False}), 503
    movies = cached.get('movies', [])
    tv     = cached.get('tv', [])
    try:
        data = generate_top10(movies, tv)
        if data:
            return jsonify(data)
        # No Anthropic key — return top items from cache directly
        return jsonify({
            'movies': movies[:12],
            'tv': tv[:12],
            'tonight': None,
            'generated_at': None,
            'fallback': True,
        })
    except Exception as e:
        app.logger.error(f"Top12 generation failed: {e}")
        # Kick off background generation and return cache fallback
        threading.Thread(target=_background_top10, daemon=True).start()
        return jsonify({
            'movies': movies[:12],
            'tv': tv[:12],
            'tonight': None,
            'generated_at': None,
            'generating': True,
        })


@app.route('/api/search')
def search():
    from engine import best_scores, STREAMING_PROVIDER_IDS
    q = (request.args.get('q') or '').strip()
    if not q or not TMDB_KEY:
        return jsonify([])

    try:
        r = requests.get(
            'https://api.themoviedb.org/3/search/multi',
            params={'api_key': TMDB_KEY, 'query': q, 'include_adult': 'false', 'page': 1},
            timeout=8
        )
        results = [x for x in r.json().get('results', []) if x.get('media_type') in ('movie', 'tv')][:12]
    except Exception:
        return jsonify([])

    def enrich(item):
        media = item.get('media_type', 'movie')
        tmdb_id = item.get('id')
        try:
            det = requests.get(
                f'https://api.themoviedb.org/3/{media}/{tmdb_id}',
                params={'api_key': TMDB_KEY, 'append_to_response': 'external_ids,watch/providers'},
                timeout=6
            ).json()
        except Exception:
            det = item

        imdb_id = (det.get('external_ids') or {}).get('imdb_id') or det.get('imdb_id') or ''
        title   = det.get('title') or det.get('name') or ''
        overview = det.get('overview', '')
        poster  = f"https://image.tmdb.org/t/p/w300{det['poster_path']}" if det.get('poster_path') else None
        release = det.get('release_date') or det.get('first_air_date') or ''
        genres  = [g['name'] for g in (det.get('genres') or []) if g.get('name')][:3]

        # US streaming providers
        wp = (det.get('watch/providers') or {}).get('results', {}).get('US', {})
        providers = [p['provider_name'] for p in (wp.get('flatrate') or [])[:4]]

        scores = best_scores(imdb_id) if imdb_id else {}
        blend_val = None
        if scores.get('critic') is not None and scores.get('audience') is not None:
            blend_val = round(scores['critic'] * 0.5 + scores['audience'] * 0.5)

        return {
            'id': imdb_id or str(tmdb_id),
            'imdb_id': imdb_id,
            'tmdb_id': tmdb_id,
            'title': title,
            'overview': overview,
            'poster': poster,
            'release': release,
            'genres': genres,
            'providers': providers,
            'media_type': media,
            'trending': False,
            'popularity': item.get('popularity', 0),
            'original_language': det.get('original_language', 'en'),
            'vote_count': det.get('vote_count', 0),
            'is_doc': False,
            'rated': scores.get('rated', ''),
            'critic_score': scores.get('critic'),
            'audience_score': scores.get('audience'),
            'rt_score': scores.get('rt'),
            'rt_audience': scores.get('rt_audience'),
            'mc_score': scores.get('mc'),
            'imdb_score': scores.get('imdb_display'),
            'letterboxd': scores.get('letterboxd'),
            'trakt_score': scores.get('trakt'),
            'tmdb_vote': scores.get('tmdb_vote'),
            'blend': blend_val,
        }

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=6) as ex:
        enriched = list(ex.map(enrich, results))

    return jsonify([e for e in enriched if e.get('title')])


@app.route('/api/trailer')
def trailer():
    """Return YouTube trailer URL for a given TMDb ID and media type."""
    tmdb_id   = request.args.get('tmdb_id')
    imdb_id   = request.args.get('imdb_id')
    media     = request.args.get('type', 'movie')
    if media not in ('movie', 'tv'):
        media = 'movie'  # sanitize — never pass arbitrary strings into TMDb URL

    if not TMDB_KEY:
        return jsonify({'url': None})

    # If we only have imdb_id, resolve to tmdb_id first
    if not tmdb_id and imdb_id:
        try:
            r = requests.get(
                f'https://api.themoviedb.org/3/find/{imdb_id}',
                params={'api_key': TMDB_KEY, 'external_source': 'imdb_id'},
                timeout=6
            )
            results = r.json().get(f'{media}_results', [])
            if results:
                tmdb_id = results[0]['id']
        except Exception:
            return jsonify({'url': None})

    if not tmdb_id:
        return jsonify({'url': None})

    try:
        r = requests.get(
            f'https://api.themoviedb.org/3/{media}/{tmdb_id}/videos',
            params={'api_key': TMDB_KEY},
            timeout=6
        )
        videos = r.json().get('results', [])
        # Prefer official trailers, then teasers, then any YouTube video
        for kind in ('Trailer', 'Teaser', None):
            for v in videos:
                if v.get('site') == 'YouTube':
                    if kind is None or v.get('type') == kind:
                        return jsonify({'url': f"https://www.youtube.com/watch?v={v['key']}"})
    except Exception:
        pass

    return jsonify({'url': None})


@app.route('/api/cast')
def cast():
    imdb_id = request.args.get('imdb_id', '')
    tmdb_id = request.args.get('tmdb_id', '')
    media   = request.args.get('type', 'movie')
    if media not in ('movie', 'tv'):
        media = 'movie'
    if not TMDB_KEY:
        return jsonify([])
    if not tmdb_id and imdb_id:
        try:
            r = requests.get(
                f'https://api.themoviedb.org/3/find/{imdb_id}',
                params={'api_key': TMDB_KEY, 'external_source': 'imdb_id'},
                timeout=6
            )
            results = r.json().get(f'{media}_results', [])
            if results:
                tmdb_id = results[0]['id']
        except Exception:
            return jsonify([])
    if not tmdb_id:
        return jsonify([])
    try:
        r = requests.get(
            f'https://api.themoviedb.org/3/{media}/{tmdb_id}/credits',
            params={'api_key': TMDB_KEY},
            timeout=6
        )
        cast_list = r.json().get('cast', [])[:4]
        return jsonify([{
            'id':        p['id'],
            'name':      p['name'],
            'character': p.get('character', ''),
            'photo':     f"https://image.tmdb.org/t/p/w185{p['profile_path']}" if p.get('profile_path') else None,
        } for p in cast_list])
    except Exception:
        return jsonify([])


@app.route('/api/actor/<int:actor_id>')
def actor_credits(actor_id):
    if not TMDB_KEY:
        return jsonify([])
    try:
        r = requests.get(
            f'https://api.themoviedb.org/3/person/{actor_id}',
            params={'api_key': TMDB_KEY, 'append_to_response': 'combined_credits'},
            timeout=8
        )
        data = r.json()
        person = {'name': data.get('name', ''), 'photo': f"https://image.tmdb.org/t/p/w185{data['profile_path']}" if data.get('profile_path') else None}
        credits = data.get('combined_credits', {}).get('cast', [])
        credits.sort(key=lambda x: x.get('popularity', 0), reverse=True)
        seen, results = set(), []
        for c in credits:
            title = c.get('title') or c.get('name', '')
            if not title or title in seen:
                continue
            seen.add(title)
            poster = f"https://image.tmdb.org/t/p/w300{c['poster_path']}" if c.get('poster_path') else None
            results.append({
                'id':         c.get('id'),
                'title':      title,
                'poster':     poster,
                'release':    c.get('release_date') or c.get('first_air_date') or '',
                'overview':   (c.get('overview') or '')[:300],
                'media_type': c.get('media_type', 'movie'),
                'character':  c.get('character', ''),
                'vote':       round(c.get('vote_average', 0) * 10),
            })
            if len(results) >= 20:
                break
        return jsonify({'person': person, 'credits': results})
    except Exception:
        return jsonify({'person': {}, 'credits': []})


@app.route('/api/score-debug')
def score_debug():
    """Show score distribution to find the fader sweet spot."""
    cached = get_cached_content()
    if not cached:
        return jsonify({'error': 'no data'}), 503

    def analyze(items):
        results = []
        for i in items:
            c = i.get('critic_score')
            a = i.get('audience_score')
            if c is None or a is None:
                gap = None
            else:
                gap = abs(c - a)
            results.append({
                'title': i.get('title') or i.get('name'),
                'critic': c,
                'audience': a,
                'gap': gap,
            })
        results.sort(key=lambda x: (x['gap'] or 0), reverse=True)
        gaps = [r['gap'] for r in results if r['gap'] is not None]
        return {
            'count': len(results),
            'polarized_15plus': sum(1 for g in gaps if g >= 15),
            'polarized_25plus': sum(1 for g in gaps if g >= 25),
            'avg_gap': round(sum(gaps) / len(gaps), 1) if gaps else 0,
            'titles': results
        }

    return jsonify({
        'movies': analyze(cached.get('movies', [])),
        'tv': analyze(cached.get('tv', [])),
    })


DATA_DIR         = os.getenv('DATA_DIR', 'data')
PREFS_FILE       = os.path.join(DATA_DIR, 'preferences.json')
WATCH_FILE       = os.path.join(DATA_DIR, 'watchlist.json')
SUBSCRIBERS_FILE = os.path.join(DATA_DIR, 'subscribers.json')
BREVO_API_KEY    = os.getenv('BREVO_API_KEY', '')

def _load_json(path):
    try:
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    except Exception:
        pass
    return []

def _save_json(path, data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f)

def _load_prefs():  return _load_json(PREFS_FILE)
def _save_prefs(p): _save_json(PREFS_FILE, p)

@app.route('/api/preference', methods=['POST'])
def preference():
    body = request.get_json(force=True)
    imdb_id = body.get('imdb_id')
    signal  = body.get('signal')  # "seen" or "skip"
    if not imdb_id or signal not in ('seen', 'skip'):
        return jsonify({'error': 'bad_request'}), 400
    prefs = _load_prefs()
    # Remove any existing signal for this title
    prefs = [p for p in prefs if p.get('imdb_id') != imdb_id]
    prefs.append({
        'imdb_id': imdb_id,
        'title': body.get('title', ''),
        'genres': body.get('genres', []),
        'signal': signal,
        'timestamp': datetime.utcnow().isoformat(),
    })
    _save_prefs(prefs)
    return jsonify({'ok': True})

@app.route('/api/preferences')
def get_preferences():
    return jsonify(_load_prefs())


@app.route('/api/watchlist', methods=['POST'])
def watchlist_save():
    body    = request.get_json(force=True)
    imdb_id = body.get('imdb_id')
    action  = body.get('action')  # 'add' or 'remove'
    if not imdb_id or action not in ('add', 'remove'):
        return jsonify({'error': 'bad_request'}), 400
    items = _load_json(WATCH_FILE)
    items = [i for i in items if i.get('imdb_id') != imdb_id]
    if action == 'add':
        items.append({
            'imdb_id':    imdb_id,
            'title':      body.get('title', ''),
            'genres':     body.get('genres', []),
            'media_type': body.get('media_type', 'movie'),
            'poster':     body.get('poster', ''),
            'providers':  body.get('providers', []),
            'saved_at':   datetime.utcnow().isoformat(),
        })
    _save_json(WATCH_FILE, items)
    return jsonify({'ok': True, 'count': len(items)})

@app.route('/api/watchlist')
def watchlist_get():
    return jsonify(_load_json(WATCH_FILE))


# ── Engagement Tracking ──────────────────────────────────────────────────────
EVENTS_FILE = os.path.join(DATA_DIR, 'events.jsonl')

def _get_fingerprint():
    """Stable anonymous fingerprint from IP + user agent."""
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
    ua = request.headers.get('User-Agent', '')
    raw = f"{ip}|{ua}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

def _append_event(event: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(EVENTS_FILE, 'a') as f:
        f.write(json.dumps(event) + '\n')

@app.route('/api/track', methods=['POST'])
def track():
    body       = request.get_json(force=True, silent=True) or {}
    event_type = body.get('event')  # 'swipe','save','fader','session_end','page_view'
    if not event_type:
        return jsonify({'error': 'missing event'}), 400

    ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
    event = {
        'ts':         datetime.utcnow().isoformat(),
        'event':      event_type,
        'session_id': body.get('session_id', ''),
        'fingerprint': _get_fingerprint(),
        'ip':         ip,
        'ua':         request.headers.get('User-Agent', '')[:120],
        'fader':      body.get('fader'),
        'signal':     body.get('signal'),       # seen / skip / save / unsave
        'imdb_id':    body.get('imdb_id', ''),
        'title':      body.get('title', ''),
        'media_type': body.get('media_type', ''),
        'genres':     body.get('genres', []),
        'session_duration_s': body.get('session_duration_s'),
        'swipe_count': body.get('swipe_count'),
        'country':    body.get('country', ''),
    }
    _append_event(event)
    return jsonify({'ok': True})

def _brevo_add_contact(email):
    """Push email to Brevo contacts list. Returns True on success."""
    if not BREVO_API_KEY:
        return False
    try:
        r = requests.post(
            'https://api.brevo.com/v3/contacts',
            headers={'api-key': BREVO_API_KEY, 'Content-Type': 'application/json'},
            json={'email': email, 'updateEnabled': True},
            timeout=8,
        )
        return r.status_code in (200, 201, 204)
    except Exception:
        return False

@app.route('/api/subscribe', methods=['POST'])
def subscribe():
    body  = request.get_json(force=True, silent=True) or {}
    email = (body.get('email') or '').strip().lower()
    if not email or '@' not in email or '.' not in email.split('@')[-1]:
        return jsonify({'error': 'invalid_email'}), 400

    # Check local cache for duplicate before hitting Brevo
    subs = _load_json(SUBSCRIBERS_FILE)
    duplicate = any(s.get('email') == email for s in subs)

    if not duplicate:
        # Persist to Brevo (permanent) + local JSON (backup)
        _brevo_add_contact(email)
        subs.append({'email': email, 'ts': datetime.utcnow().isoformat()})
        _save_json(SUBSCRIBERS_FILE, subs)

    return jsonify({'ok': True, 'duplicate': duplicate})


@app.route('/api/stats')
def stats():
    """Quick engagement summary — unique sessions, swipes, saves."""
    if not os.path.exists(EVENTS_FILE):
        return jsonify({'sessions': 0, 'swipes': 0, 'saves': 0, 'events': 0})
    sessions, swipes, saves = set(), 0, 0
    total = 0
    with open(EVENTS_FILE) as f:
        for line in f:
            try:
                e = json.loads(line)
                total += 1
                if e.get('session_id'): sessions.add(e['session_id'])
                if e.get('event') == 'swipe': swipes += 1
                if e.get('event') == 'save' and e.get('signal') == 'save': saves += 1
            except Exception:
                pass
    return jsonify({'sessions': len(sessions), 'swipes': swipes, 'saves': saves, 'events': total})


@app.route('/best-movies-streaming-now')
def seo_movies():
    from datetime import timedelta
    cached = get_cached_content()
    movies = cached.get('movies', []) if cached else []
    def sweet_score(m):
        c = m.get('critic_score') or 50
        a = m.get('audience_score') or 50
        return c * 0.5 + a * 0.5
    top = sorted([m for m in movies if m.get('title')], key=sweet_score, reverse=True)[:25]
    now = datetime.utcnow()
    updated = now.strftime('%B %d, %Y')
    now_minus_7 = (now - timedelta(days=7)).strftime('%Y-%m-%d')
    return render_template('seo_movies.html', movies=top, updated=updated, now_minus_7=now_minus_7)

@app.route('/robots.txt')
def robots():
    return app.response_class(
        "User-agent: *\nAllow: /\nSitemap: https://stream.creativekonsoles.com/sitemap.xml\n",
        mimetype='text/plain'
    )

@app.route('/sitemap.xml')
def sitemap():
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
           '<url><loc>https://stream.creativekonsoles.com/</loc>'
           '<changefreq>daily</changefreq><priority>1.0</priority></url>'
           '<url><loc>https://stream.creativekonsoles.com/best-movies-streaming-now</loc>'
           '<changefreq>daily</changefreq><priority>0.9</priority></url>'
           '</urlset>')
    return app.response_class(xml, mimetype='application/xml')


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5556, debug=False)
