import threading, os, requests, json
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

    # No cache at all — must wait for a live fetch
    try:
        return jsonify(get_top_content(force=False))
    except Exception as e:
        app.logger.error(f"Content fetch failed: {e}")
        return jsonify({'movies': [], 'tv': [], 'error': 'fetch_failed', 'fetched_at': None}), 500

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


PREFS_FILE = 'data/preferences.json'

def _load_prefs():
    try:
        if os.path.exists(PREFS_FILE):
            with open(PREFS_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return []

def _save_prefs(prefs):
    os.makedirs('data', exist_ok=True)
    with open(PREFS_FILE, 'w') as f:
        json.dump(prefs, f)

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


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5556, debug=False)
