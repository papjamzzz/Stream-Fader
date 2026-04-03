import threading
from flask import Flask, render_template, jsonify, request
from engine import get_top_content, get_cached_content

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

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5556, debug=False)
