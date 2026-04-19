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
           '</urlset>')
    return app.response_class(xml, mimetype='application/xml')


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5556, debug=False)
