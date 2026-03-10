import os, json, time, requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

load_dotenv()

TMDB_KEY = os.getenv('TMDB_API_KEY', '')
OMDB_KEY = os.getenv('OMDB_API_KEY', '')
CACHE_FILE = 'data/cache.json'
CACHE_TTL = 3 * 3600  # 3 hours

STREAMING_PROVIDERS = {
    8:    {'name': 'Netflix',     'color': '#e50914'},
    119:  {'name': 'Prime',       'color': '#00a8e0'},
    350:  {'name': 'Apple TV+',   'color': '#a0a0a0'},
    337:  {'name': 'Disney+',     'color': '#113ccf'},
    15:   {'name': 'Hulu',        'color': '#1ce783'},
    531:  {'name': 'Paramount+',  'color': '#0064ff'},
    1899: {'name': 'Max',         'color': '#5822d0'},
    386:  {'name': 'Peacock',     'color': '#f0f0f0'},
}

GENRE_MAP = {
    28: 'Action', 12: 'Adventure', 16: 'Animation', 35: 'Comedy',
    80: 'Crime', 99: 'Documentary', 18: 'Drama', 10751: 'Family',
    14: 'Fantasy', 27: 'Horror', 9648: 'Mystery', 10749: 'Romance',
    878: 'Sci-Fi', 53: 'Thriller', 37: 'Western',
    10759: 'Action/Adv', 10765: 'Sci-Fi/Fantasy', 10768: 'War/Politics',
    10762: 'Kids', 10763: 'News', 10764: 'Reality', 10767: 'Talk',
}


def tmdb_get(path, params=None):
    try:
        p = {'api_key': TMDB_KEY, **(params or {})}
        r = requests.get(f'https://api.themoviedb.org/3{path}', params=p, timeout=10)
        return r.json() if r.ok else {}
    except Exception:
        return {}


def omdb_get(imdb_id):
    try:
        r = requests.get('http://www.omdbapi.com/',
                         params={'i': imdb_id, 'apikey': OMDB_KEY}, timeout=8)
        return r.json() if r.ok else {}
    except Exception:
        return {}


def parse_scores(omdb_data):
    rt, mc, imdb = None, None, None
    for rating in omdb_data.get('Ratings', []):
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
    critic_parts = [s for s in [rt, mc] if s is not None]
    critic = round(sum(critic_parts) / len(critic_parts)) if critic_parts else None
    audience = imdb
    return critic, audience, rt, mc, round(imdb / 10, 1) if imdb else None


def enrich_item(raw, media_type):
    tmdb_id = raw['id']

    ext = tmdb_get(f'/{media_type}/{tmdb_id}/external_ids')
    imdb_id = ext.get('imdb_id')

    wp = tmdb_get(f'/{media_type}/{tmdb_id}/watch/providers')
    us = wp.get('results', {}).get('US', {})
    providers = []
    for p in us.get('flatrate', []):
        pid = p.get('provider_id')
        if pid in STREAMING_PROVIDERS:
            providers.append(STREAMING_PROVIDERS[pid])
    if not providers:
        return None

    critic, audience, rt, mc, imdb_display = None, None, None, None, None
    if imdb_id and OMDB_KEY:
        omdb = omdb_get(imdb_id)
        critic, audience, rt, mc, imdb_display = parse_scores(omdb)

    if critic is None and audience is None:
        return None

    title = raw.get('title') or raw.get('name', 'Unknown')
    poster = raw.get('poster_path')
    release = raw.get('release_date') or raw.get('first_air_date', '')
    genres = [GENRE_MAP[g] for g in raw.get('genre_ids', []) if g in GENRE_MAP][:3]

    return {
        'id': tmdb_id,
        'imdb_id': imdb_id,
        'title': title,
        'overview': (raw.get('overview') or '')[:220],
        'poster': f'https://image.tmdb.org/t/p/w342{poster}' if poster else None,
        'release': release,
        'media_type': media_type,
        'providers': providers,
        'genres': genres,
        'critic_score': critic,
        'audience_score': audience,
        'rt_score': rt,
        'mc_score': mc,
        'imdb_score': imdb_display,
        'popularity': raw.get('popularity', 0),
    }


def fetch_items(media_type, days=90):
    if not TMDB_KEY:
        return []
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    date_field = 'primary_release_date' if media_type == 'movie' else 'first_air_date'
    provider_ids = '|'.join(str(p) for p in STREAMING_PROVIDERS)

    params = {
        'with_watch_providers': provider_ids,
        'watch_region': 'US',
        'with_watch_monetization_types': 'flatrate',
        f'{date_field}.gte': cutoff,
        'sort_by': 'popularity.desc',
        'page': 1,
    }
    data = tmdb_get(f'/discover/{media_type}', params)
    raw_results = data.get('results', [])[:24]

    enriched = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(enrich_item, r, media_type): r for r in raw_results}
        for future in as_completed(futures):
            result = future.result()
            if result:
                enriched.append(result)

    # Sort by 50/50 blend as default
    enriched.sort(key=lambda x: (
        ((x['critic_score'] or 50) + (x['audience_score'] or 50)) / 2
    ), reverse=True)
    return enriched


def get_top_content(force=False):
    if not TMDB_KEY:
        return {'movies': [], 'tv': [], 'error': 'missing_keys', 'fetched_at': None}

    if not force and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as f:
                cached = json.load(f)
            if time.time() - cached.get('timestamp', 0) < CACHE_TTL:
                return cached['data']
        except Exception:
            pass

    movies = fetch_items('movie')
    tv = fetch_items('tv')

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
