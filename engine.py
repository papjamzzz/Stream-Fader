import os, json, time, requests, re
from datetime import datetime, timedelta
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

load_dotenv()
OMDB_KEY = os.getenv('OMDB_API_KEY', '')
TMDB_KEY = os.getenv('TMDB_API_KEY', '')
CACHE_FILE = 'data/cache.json'
CACHE_TTL = 3 * 3600  # 3 hours

STREAMING_NAMES = [
    'Netflix', 'Hulu', 'Amazon', 'Prime', 'Apple TV',
    'Disney+', 'Paramount', 'Max', 'HBO', 'Peacock', 'Showtime', 'AMC'
]

CHANNEL_COLORS = {
    'Netflix':    '#e50914',
    'Hulu':       '#1ce783',
    'Amazon':     '#00a8e0',
    'Prime':      '#00a8e0',
    'Apple TV':   '#a0a0a0',
    'Disney+':    '#113ccf',
    'Paramount':  '#0064ff',
    'Max':        '#5822d0',
    'HBO':        '#5822d0',
    'Peacock':    '#d0d0d0',
    'Showtime':   '#cc0000',
    'AMC':        '#ff6600',
}

MOVIE_SEARCH_TERMS = [
    'action', 'thriller', 'comedy', 'drama', 'horror',
    'adventure', 'mystery', 'crime', 'romance', 'sci-fi'
]


def tmdb_providers(imdb_id):
    if not TMDB_KEY or not imdb_id:
        return []
    try:
        # Resolve IMDB ID → TMDb movie ID
        r = requests.get(
            f'https://api.themoviedb.org/3/find/{imdb_id}',
            params={'api_key': TMDB_KEY, 'external_source': 'imdb_id'},
            timeout=8
        )
        if not r.ok:
            return []
        results = r.json().get('movie_results', [])
        if not results:
            return []
        tmdb_id = results[0]['id']

        # Fetch US streaming providers
        r2 = requests.get(
            f'https://api.themoviedb.org/3/movie/{tmdb_id}/watch/providers',
            params={'api_key': TMDB_KEY},
            timeout=8
        )
        if not r2.ok:
            return []
        flatrate = r2.json().get('results', {}).get('US', {}).get('flatrate', [])
        return [{'name': p['provider_name'], 'color': channel_color(p['provider_name'])} for p in flatrate]
    except Exception:
        return []


def omdb_fetch(imdb_id=None, title=None, year=None):
    if not OMDB_KEY:
        return {}
    params = {'apikey': OMDB_KEY}
    if imdb_id:
        params['i'] = imdb_id
    elif title:
        params['t'] = title
        if year:
            params['y'] = year
    try:
        r = requests.get('http://www.omdbapi.com/', params=params, timeout=8)
        return r.json() if r.ok else {}
    except Exception:
        return {}


def parse_scores(omdb):
    rt, mc, imdb = None, None, None
    for rating in omdb.get('Ratings', []):
        src, val = rating.get('Source', ''), rating.get('Value', '')
        try:
            if 'Rotten Tomatoes' in src:
                rt = int(val.replace('%', ''))
            elif 'Metacritic' in src:
                mc = int(val.split('/')[0])
            elif 'Internet Movie Database' in src:
                imdb = round(float(val.split('/')[0]) * 10)
        except Exception:
            pass
    critics = [s for s in [rt, mc] if s is not None]
    critic = round(sum(critics) / len(critics)) if critics else None
    return critic, imdb, rt, mc, round(imdb / 10, 1) if imdb else None


def channel_color(name):
    for key, color in CHANNEL_COLORS.items():
        if key.lower() in name.lower():
            return color
    return '#888888'


def is_streaming(channel_name):
    return any(s.lower() in channel_name.lower() for s in STREAMING_NAMES)


def strip_html(text):
    return re.sub(r'<[^>]+>', '', text or '')


# ── TV via TVmaze (free, no key) ──────────────────────────────────────────────

def fetch_tv(days=90):
    cutoff = datetime.now() - timedelta(days=days)
    seen_ids = set()
    candidates = []

    # Query TVmaze web schedule for the last 14 days — finds currently airing streaming shows
    for day_offset in range(0, 14):
        date_str = (datetime.now() - timedelta(days=day_offset)).strftime('%Y-%m-%d')
        try:
            r = requests.get(
                f'https://api.tvmaze.com/schedule/web?date={date_str}&country=US',
                timeout=10
            )
            if not r.ok:
                continue
            episodes = r.json()
            for ep in episodes:
                show = (ep.get('_embedded') or {}).get('show') or {}
                if not show:
                    continue
                sid = show.get('id')
                if not sid or sid in seen_ids:
                    continue
                seen_ids.add(sid)

                wc  = show.get('webChannel') or {}
                net = show.get('network') or {}
                channel = wc.get('name') or net.get('name') or ''
                if not is_streaming(channel):
                    continue

                # Only include shows with a rating or IMDB ID
                has_rating = (show.get('rating') or {}).get('average')
                has_imdb   = (show.get('externals') or {}).get('imdb')
                if not has_rating and not has_imdb:
                    continue

                candidates.append({'show': show, 'channel': channel})
        except Exception:
            continue

    enriched = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(enrich_tv, c): c for c in candidates}
        for future in as_completed(futures):
            result = future.result()
            if result:
                enriched.append(result)

    enriched.sort(key=lambda x: (
        ((x['critic_score'] or 50) + (x['audience_score'] or 50)) / 2
    ), reverse=True)
    return enriched


def enrich_tv(candidate):
    show    = candidate['show']
    channel = candidate['channel']
    imdb_id = (show.get('externals') or {}).get('imdb')

    critic, audience, rt, mc, imdb_display = None, None, None, None, None
    if imdb_id:
        omdb = omdb_fetch(imdb_id=imdb_id)
        critic, audience, rt, mc, imdb_display = parse_scores(omdb)

    # fallback: use TVmaze average rating as audience proxy
    if audience is None:
        avg = (show.get('rating') or {}).get('average')
        if avg:
            audience = round(float(avg) * 10)

    if critic is None and audience is None:
        return None

    img = show.get('image') or {}
    poster = img.get('medium') or img.get('original')
    genres = [g for g in (show.get('genres') or [])][:3]

    return {
        'id': show['id'],
        'imdb_id': imdb_id,
        'title': show.get('name', 'Unknown'),
        'overview': strip_html(show.get('summary', ''))[:220],
        'poster': poster,
        'release': show.get('premiered', ''),
        'media_type': 'tv',
        'providers': [{'name': channel, 'color': channel_color(channel)}],
        'genres': genres,
        'critic_score': critic,
        'audience_score': audience,
        'rt_score': rt,
        'mc_score': mc,
        'imdb_score': imdb_display,
    }


# ── Movies via OMDb search ────────────────────────────────────────────────────

def fetch_movies(days=90):
    if not OMDB_KEY:
        return []

    years = set()
    cutoff = datetime.now() - timedelta(days=days)
    for i in range((datetime.now() - cutoff).days // 30 + 2):
        d = datetime.now() - timedelta(days=30 * i)
        years.add(str(d.year))

    seen = set()
    raw = []
    for year in years:
        for term in MOVIE_SEARCH_TERMS:
            try:
                r = requests.get('http://www.omdbapi.com/', params={
                    'apikey': OMDB_KEY, 's': term,
                    'type': 'movie', 'y': year, 'page': 1
                }, timeout=8)
                data = r.json()
                for m in data.get('Search', []):
                    if m.get('imdbID') and m['imdbID'] not in seen:
                        seen.add(m['imdbID'])
                        raw.append(m)
            except Exception:
                pass

    enriched = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(enrich_movie, m): m for m in raw}
        for future in as_completed(futures):
            result = future.result()
            if result:
                enriched.append(result)

    enriched.sort(key=lambda x: (
        ((x['critic_score'] or 50) + (x['audience_score'] or 50)) / 2
    ), reverse=True)
    return enriched


def enrich_movie(raw):
    omdb = omdb_fetch(imdb_id=raw.get('imdbID'))
    if not omdb or omdb.get('Response') == 'False':
        return None

    critic, audience, rt, mc, imdb_display = parse_scores(omdb)
    if critic is None and audience is None:
        return None

    year = omdb.get('Year', '')
    release = f'{year}-01-01' if year.isdigit() else ''

    return {
        'id': raw.get('imdbID'),
        'imdb_id': raw.get('imdbID'),
        'title': omdb.get('Title', raw.get('Title', 'Unknown')),
        'overview': omdb.get('Plot', '')[:220],
        'poster': omdb.get('Poster') if omdb.get('Poster') != 'N/A' else None,
        'release': release,
        'media_type': 'movie',
        'providers': tmdb_providers(raw.get('imdbID')),
        'genres': [g.strip() for g in omdb.get('Genre', '').split(',')][:3],
        'critic_score': critic,
        'audience_score': audience,
        'rt_score': rt,
        'mc_score': mc,
        'imdb_score': imdb_display,
    }


# ── Cache + entry point ───────────────────────────────────────────────────────

def get_top_content(force=False):
    if not OMDB_KEY:
        return {'movies': [], 'tv': [], 'error': 'missing_keys', 'fetched_at': None}

    if not force and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as f:
                cached = json.load(f)
            if time.time() - cached.get('timestamp', 0) < CACHE_TTL:
                return cached['data']
        except Exception:
            pass

    tv     = fetch_tv()
    movies = fetch_movies()

    data = {
        'movies': movies,
        'tv': tv,
        'fetched_at': datetime.now().isoformat(),
        'error': None,
    }

    os.makedirs('data', exist_ok=True)
    with open(CACHE_FILE, 'w') as f:
        json.dump({'timestamp': time.time(), 'data': data}, f)

    return data
