import threading, os, requests
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

# Pre-warm cache on startup so the first real user never hits a cold fetch
threading.Thread(target=_background_refresh, daemon=True).start()

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
            return jsonify({'movies': [], 'tv': [], 'error': str(e), 'fetched_at': None}), 500

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
        return jsonify({'movies': [], 'tv': [], 'error': str(e), 'fetched_at': None}), 500

@app.route('/api/top10')
def top10():
    """Return 5-persona AI consensus Top 12 Movies + Top 12 Series."""
    cached = get_cached_content()
    if not cached:
        return jsonify({'error': 'no_data'}), 503
    movies = cached.get('movies', [])
    tv     = cached.get('tv', [])
    try:
        data = generate_top10(movies, tv)
        if data:
            return jsonify(data)
        return jsonify({'error': 'no_anthropic_key'}), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/trailer')
def trailer():
    """Return YouTube trailer URL for a given TMDb ID and media type."""
    tmdb_id   = request.args.get('tmdb_id')
    imdb_id   = request.args.get('imdb_id')
    media     = request.args.get('type', 'movie')  # 'movie' or 'tv'

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


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5556, debug=False)
