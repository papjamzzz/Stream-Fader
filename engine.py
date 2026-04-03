"""
StreamFader V2 Engine
Sources: TMDb · OMDb (RT/MC/IMDb scores) · TVmaze · Trakt · MDBList
AI:      Claude Top Pick via Anthropic API
"""
import os, json, time, requests, re, anthropic
from datetime import datetime, timedelta
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

load_dotenv()

OMDB_KEY      = os.getenv('OMDB_API_KEY', '')
TMDB_KEY      = os.getenv('TMDB_API_KEY', '')
TRAKT_ID      = os.getenv('TRAKT_CLIENT_ID', '')
MDBLIST_KEY   = os.getenv('MDBLIST_API_KEY', '')
ANTHROPIC_KEY = os.getenv('ANTHROPIC_API_KEY', '')

CACHE_FILE      = 'data/cache.json'
TOPPICK_FILE    = 'data/toppick.json'
CACHE_TTL       = 6 * 3600
TOPPICK_TTL     = 12 * 3600

# ── Colors ─────────────────────────────────────────────────────────────────────

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

STREAMING_NAMES = list(CHANNEL_COLORS.keys())
STREAMING_PROVIDER_IDS = '8|119|350|337|15|531|1899|386'


def channel_color(name):
    for key, color in CHANNEL_COLORS.items():
        if key.lower() in name.lower():
            return color
    return '#888888'


def is_streaming(channel_name):
    return any(s.lower() in channel_name.lower() for s in STREAMING_NAMES)


def strip_html(text):
    return re.sub(r'<[^>]+>', '', text or '')


# ── OMDb ───────────────────────────────────────────────────────────────────────

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
        r = requests.get('http://www.omdbapi.com/', params=params, timeout=5)
        return r.json() if r.ok else {}
    except Exception:
        return {}


def parse_omdb_scores(omdb):
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
    imdb_display = round(imdb / 10, 1) if imdb else None
    return critic, imdb, rt, mc, imdb_display


# ── MDBList ─────────────────────────────────────────────────────────────────────

def mdblist_fetch(imdb_id):
    if not MDBLIST_KEY or not imdb_id:
        return {}
    try:
        r = requests.get('https://mdblist.com/api/',
                         params={'apikey': MDBLIST_KEY, 'i': imdb_id}, timeout=5)
        return r.json() if r.ok else {}
    except Exception:
        return {}


def parse_mdblist_scores(data):
    scores = {}
    for rating in data.get('ratings', []):
        source = rating.get('source', '').lower()
        val = rating.get('value')
        if val is None:
            continue
        try:
            if source == 'tomatoes':
                scores['rt'] = int(val)
            elif source == 'tomatoesaudience':
                scores['rt_audience'] = int(val)
            elif source == 'metacritic':
                scores['mc'] = int(val)
            elif source == 'imdb':
                scores['imdb'] = round(float(val) * 10)
                scores['imdb_display'] = float(val)
            elif source == 'letterboxd':
                scores['letterboxd'] = round(float(val) * 20)
            elif source == 'trakt':
                scores['trakt'] = int(val)
        except Exception:
            pass
    return scores


# ── Trakt ───────────────────────────────────────────────────────────────────────

def trakt_headers():
    h = {'Content-Type': 'application/json', 'trakt-api-version': '2'}
    if TRAKT_ID:
        h['trakt-api-key'] = TRAKT_ID
    return h


def trakt_fetch(path, limit=30):
    if not TRAKT_ID:
        return []
    try:
        r = requests.get(f'https://api.trakt.tv{path}', headers=trakt_headers(),
                         params={'limit': limit, 'extended': 'full'}, timeout=10)
        return r.json() if r.ok else []
    except Exception:
        return []


def trakt_trending_movies(limit=30):
    return [i.get('movie', {}) for i in trakt_fetch('/movies/trending', limit) if i.get('movie')]


def trakt_popular_movies(limit=20):
    return trakt_fetch('/movies/popular', limit)


def trakt_trending_shows(limit=30):
    return [i.get('show', {}) for i in trakt_fetch('/shows/trending', limit) if i.get('show')]


# ── TMDb helpers ───────────────────────────────────────────────────────────────

def tmdb_get(path, params=None):
    if not TMDB_KEY:
        return {}
    p = {'api_key': TMDB_KEY}
    if params:
        p.update(params)
    try:
        r = requests.get(f'https://api.themoviedb.org/3{path}', params=p, timeout=5)
        return r.json() if r.ok else {}
    except Exception:
        return {}


def tmdb_watch_providers(tmdb_id, media='movie'):
    data = tmdb_get(f'/{media}/{tmdb_id}/watch/providers')
    flatrate = data.get('results', {}).get('US', {}).get('flatrate', [])
    return [{'name': p['provider_name'], 'color': channel_color(p['provider_name'])} for p in flatrate]


# ── Score aggregation ──────────────────────────────────────────────────────────

def best_scores(imdb_id):
    scores = {
        'rt': None, 'rt_audience': None, 'mc': None,
        'imdb': None, 'imdb_display': None,
        'letterboxd': None, 'trakt': None,
        'critic': None, 'audience': None,
    }

    if MDBLIST_KEY and imdb_id:
        mdb = mdblist_fetch(imdb_id)
        if mdb and mdb.get('response') != 'False':
            s = parse_mdblist_scores(mdb)
            scores.update({k: v for k, v in s.items() if v is not None})

    if OMDB_KEY and imdb_id and (scores['rt'] is None or scores['mc'] is None):
        omdb = omdb_fetch(imdb_id=imdb_id)
        if omdb and omdb.get('Response') != 'False':
            _, imdb_raw, rt, mc, imdb_disp = parse_omdb_scores(omdb)
            if scores['rt'] is None and rt is not None:
                scores['rt'] = rt
            if scores['mc'] is None and mc is not None:
                scores['mc'] = mc
            if scores['imdb'] is None and imdb_raw is not None:
                scores['imdb'] = imdb_raw
                scores['imdb_display'] = imdb_disp

    critics = [s for s in [scores['rt'], scores['mc'], scores['letterboxd']] if s is not None]
    scores['critic'] = round(sum(critics) / len(critics)) if critics else None

    audience_sources = [s for s in [scores['rt_audience'], scores['trakt'], scores['imdb']] if s is not None]
    scores['audience'] = round(sum(audience_sources) / len(audience_sources)) if audience_sources else scores['imdb']

    return scores


# ── Movies ─────────────────────────────────────────────────────────────────────

MIN_VOTES       = 200    # minimum TMDb vote count — filters out small/limited releases
MIN_POPULARITY  = 10     # TMDb popularity floor — removes truly obscure titles
MIN_SCORE       = 60     # combined critic+audience floor — only quality content
DOC_GENRE_ID    = 99     # TMDb genre ID for Documentary

# TMDb TV genre IDs to exclude — News, Reality, Soap, Talk
TV_EXCLUDED_GENRES = '10763,10764,10766,10767'

# TMDb show types to keep — scripted fiction and limited series only
TV_ALLOWED_TYPES = {'Scripted', 'Miniseries'}

# TVmaze genres that indicate non-fiction / non-scripted programming
TVMAZE_EXCLUDED_GENRES = {
    'news', 'talk show', 'sports', 'game show', 'reality',
    'soap', 'variety', 'awards show', 'sports talk',
}


def _passes_filters(item):
    """Return True if a TMDb movie item clears popularity/vote thresholds."""
    if item.get('vote_count', 0) < MIN_VOTES:
        return False
    if item.get('popularity', 0) < MIN_POPULARITY:
        return False
    return True


def _passes_score_floor(result):
    """Drop cards where both scores are very low — not worth showing."""
    critic   = result.get('critic_score') or 0
    audience = result.get('audience_score') or 0
    combined = (critic + audience) / 2 if (critic and audience) else max(critic, audience)
    return combined >= MIN_SCORE


def fetch_movies():
    seen_imdb = set()
    candidates = []

    if TMDB_KEY:
        cutoff = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

        # ── Popular mainstream movies on streaming (last year) ──
        for page in range(1, 6):
            data = tmdb_get('/discover/movie', {
                'sort_by': 'popularity.desc',
                'watch_region': 'US',
                'with_watch_providers': STREAMING_PROVIDER_IDS,
                'primary_release_date.gte': cutoff,
                'vote_count.gte': MIN_VOTES,
                'popularity.gte': MIN_POPULARITY,
                'page': page,
            })
            for m in data.get('results', []):
                if _passes_filters(m):
                    candidates.append(('tmdb_movie', m))

        # ── Hidden gems: older high-rated films now streaming ──
        # Sort by rating instead of popularity — surfaces excellent older titles
        data = tmdb_get('/discover/movie', {
            'sort_by': 'vote_average.desc',
            'watch_region': 'US',
            'with_watch_providers': STREAMING_PROVIDER_IDS,
            'vote_count.gte': 1000,       # needs real vote base to trust the rating
            'vote_average.gte': 7.5,
            'popularity.gte': MIN_POPULARITY,
            'page': 1,
        })
        for m in data.get('results', []):
            candidates.append(('tmdb_movie', m))

        # ── Top documentaries on streaming ──
        data = tmdb_get('/discover/movie', {
            'sort_by': 'vote_average.desc',
            'watch_region': 'US',
            'with_watch_providers': STREAMING_PROVIDER_IDS,
            'with_genres': DOC_GENRE_ID,
            'vote_count.gte': 200,
            'vote_average.gte': 7.0,
            'page': 1,
        })
        for m in data.get('results', []):
            m['_is_doc'] = True
            candidates.append(('tmdb_movie', m))

    for t in trakt_trending_movies(30):
        candidates.append(('trakt_movie', t))

    for t in trakt_popular_movies(20):
        candidates.append(('trakt_movie', t))

    candidates = candidates[:50]
    enriched = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_enrich_movie, src, item): (src, item) for src, item in candidates}
        for future in as_completed(futures):
            result = future.result()
            if result and _passes_score_floor(result):
                key = result.get('imdb_id') or result.get('id')
                if key and key not in seen_imdb:
                    seen_imdb.add(key)
                    enriched.append(result)

    enriched.sort(key=lambda x: (
        ((x['critic_score'] or 50) + (x['audience_score'] or 50)) / 2
    ), reverse=True)
    return enriched[:35]


def _enrich_movie(source, item):
    try:
        if source == 'tmdb_movie':
            tmdb_id = item.get('id')
            if not tmdb_id:
                return None
            details = tmdb_get(f'/movie/{tmdb_id}', {'append_to_response': 'external_ids,watch/providers'})
            imdb_id = (details.get('external_ids') or {}).get('imdb_id') or details.get('imdb_id')
            scores = best_scores(imdb_id) if imdb_id else {}
            if not scores.get('critic') and not scores.get('audience'):
                if item.get('vote_average'):
                    scores['audience'] = round(item['vote_average'] * 10)
                else:
                    return None
            wp = (details.get('watch/providers') or {}).get('results', {}).get('US', {})
            providers = [{'name': p['provider_name'], 'color': channel_color(p['provider_name'])}
                         for p in wp.get('flatrate', [])]
            poster = f"https://image.tmdb.org/t/p/w500{item['poster_path']}" if item.get('poster_path') else None
            title    = details.get('title') or item.get('title', 'Unknown')
            overview = (details.get('overview') or item.get('overview') or '')[:600]
            genres   = [g['name'] for g in (details.get('genres') or [])][:3]
            return _movie_record(imdb_id or str(tmdb_id), imdb_id, title, overview,
                                 poster, item.get('release_date', ''), providers, genres, scores,
                                 is_doc=item.get('_is_doc', False))

        elif source == 'trakt_movie':
            ids = item.get('ids') or {}
            imdb_id = ids.get('imdb')
            tmdb_id = ids.get('tmdb')
            scores = best_scores(imdb_id) if imdb_id else {}
            if not scores.get('critic') and not scores.get('audience'):
                if item.get('rating'):
                    scores['audience'] = round(float(item['rating']) * 10)
                else:
                    return None
            providers = tmdb_watch_providers(tmdb_id, 'movie') if tmdb_id and TMDB_KEY else []
            poster = None
            if tmdb_id and TMDB_KEY:
                t = tmdb_get(f'/movie/{tmdb_id}')
                if t.get('poster_path'):
                    poster = f"https://image.tmdb.org/t/p/w500{t['poster_path']}"
            return _movie_record(imdb_id or str(ids.get('trakt', '')), imdb_id,
                                 item.get('title', 'Unknown'), (item.get('overview') or '')[:600],
                                 poster, str(item.get('year', '')), providers,
                                 (item.get('genres') or [])[:3], scores)
    except Exception:
        return None


def _movie_record(uid, imdb_id, title, overview, poster, release, providers, genres, scores, is_doc=False):
    return {
        'id': uid, 'imdb_id': imdb_id, 'title': title, 'overview': overview,
        'poster': poster, 'release': release, 'media_type': 'movie',
        'is_doc': is_doc,
        'providers': providers, 'genres': genres,
        'critic_score': scores.get('critic'), 'audience_score': scores.get('audience'),
        'rt_score': scores.get('rt'), 'rt_audience': scores.get('rt_audience'),
        'mc_score': scores.get('mc'), 'imdb_score': scores.get('imdb_display'),
        'letterboxd': scores.get('letterboxd'), 'trakt_score': scores.get('trakt'),
    }


# ── TV Shows ───────────────────────────────────────────────────────────────────

TV_RECENCY_CUTOFF = (datetime.now() - timedelta(days=548)).strftime('%Y-%m-%d')  # ~18 months


def fetch_tv():
    seen_ids = set()
    candidates = []

    if TMDB_KEY:
        # ── Currently airing popular shows — MUST have aired a new episode in last 18 months ──
        for page in range(1, 5):
            data = tmdb_get('/discover/tv', {
                'sort_by': 'popularity.desc',
                'watch_region': 'US',
                'with_watch_providers': STREAMING_PROVIDER_IDS,
                'without_genres': TV_EXCLUDED_GENRES,
                'air_date.gte': TV_RECENCY_CUTOFF,   # last episode within 18 months
                'vote_count.gte': 30,
                'popularity.gte': 5,
                'page': page,
            })
            for s in data.get('results', []):
                sid = str(s.get('id'))
                if sid and sid not in seen_ids:
                    seen_ids.add(sid)
                    candidates.append(('tmdb_tv', s))

        # ── Top-rated shows with RECENT episodes — high bar, still active ──
        for page in range(1, 3):
            data = tmdb_get('/discover/tv', {
                'sort_by': 'vote_average.desc',
                'watch_region': 'US',
                'with_watch_providers': STREAMING_PROVIDER_IDS,
                'without_genres': TV_EXCLUDED_GENRES,
                'air_date.gte': TV_RECENCY_CUTOFF,
                'vote_count.gte': 100,
                'vote_average.gte': 7.8,
                'page': page,
            })
            for s in data.get('results', []):
                sid = str(s.get('id'))
                if sid and sid not in seen_ids:
                    seen_ids.add(sid)
                    candidates.append(('tmdb_tv', s))

    # ── TVmaze: what dropped this week on streaming (supplement) ──
    for day_offset in range(0, 7):
        date_str = (datetime.now() - timedelta(days=day_offset)).strftime('%Y-%m-%d')
        try:
            r = requests.get(
                f'https://api.tvmaze.com/schedule/web?date={date_str}&country=US',
                timeout=6
            )
            if not r.ok:
                continue
            for ep in r.json():
                show = (ep.get('_embedded') or {}).get('show') or {}
                if not show:
                    continue
                sid = str(show.get('id', ''))
                if not sid or sid in seen_ids:
                    continue
                wc      = show.get('webChannel') or {}
                net     = show.get('network') or {}
                channel = wc.get('name') or net.get('name') or ''
                if not is_streaming(channel):
                    continue
                # Skip non-scripted genres
                show_genres = {g.lower() for g in (show.get('genres') or [])}
                if show_genres & TVMAZE_EXCLUDED_GENRES:
                    continue
                show_type = (show.get('type') or '').lower()
                if show_type in ('news', 'sports', 'variety', 'talk show', 'reality', 'game show'):
                    continue
                has_rating = (show.get('rating') or {}).get('average')
                has_imdb   = (show.get('externals') or {}).get('imdb')
                if not has_rating and not has_imdb:
                    continue
                seen_ids.add(sid)
                candidates.append(('tvmaze', {'show': show, 'channel': channel}))
        except Exception:
            continue

    for t in trakt_trending_shows(30):
        imdb_id = (t.get('ids') or {}).get('imdb')
        if imdb_id and imdb_id not in seen_ids:
            seen_ids.add(imdb_id)
            candidates.append(('trakt_show', t))

    enriched = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_enrich_tv, src, item): (src, item) for src, item in candidates}
        for future in as_completed(futures):
            result = future.result()
            if result:
                enriched.append(result)

    seen_final = set()
    deduped = []
    for item in enriched:
        if not _passes_score_floor(item):
            continue
        key = item.get('imdb_id') or item.get('id')
        if key and key not in seen_final:
            seen_final.add(key)
            deduped.append(item)

    deduped.sort(key=lambda x: (
        ((x['critic_score'] or 50) + (x['audience_score'] or 50)) / 2
    ), reverse=True)
    return deduped[:30]


def _enrich_tv(source, item):
    try:
        if source == 'tmdb_tv':
            tmdb_id = item.get('id')
            if not tmdb_id:
                return None
            details  = tmdb_get(f'/tv/{tmdb_id}', {'append_to_response': 'external_ids,watch/providers'})

            # Drop non-scripted types
            show_type = details.get('type', '')
            if show_type and show_type not in TV_ALLOWED_TYPES:
                return None

            # Hard recency gate: last_air_date must be within 18 months
            last_air = details.get('last_air_date') or item.get('last_air_date', '')
            if last_air and last_air < TV_RECENCY_CUTOFF:
                return None

            # Require at least 3 episodes
            if details.get('number_of_episodes', 99) < 3:
                return None

            # Build season label — show which season is current
            num_seasons = details.get('number_of_seasons', 1)
            seasons     = details.get('seasons') or []
            # Find the latest non-special season that aired recently
            current_season = num_seasons
            for s in reversed(seasons):
                if s.get('season_number', 0) > 0:
                    s_air = s.get('air_date') or ''
                    if s_air and s_air >= TV_RECENCY_CUTOFF:
                        current_season = s.get('season_number', num_seasons)
                        break

            imdb_id  = (details.get('external_ids') or {}).get('imdb_id')
            scores   = best_scores(imdb_id) if imdb_id else {}
            if not scores.get('critic') and not scores.get('audience'):
                if item.get('vote_average'):
                    scores['audience'] = round(item['vote_average'] * 10)
                else:
                    return None

            wp        = (details.get('watch/providers') or {}).get('results', {}).get('US', {})
            providers = [{'name': p['provider_name'], 'color': channel_color(p['provider_name'])}
                         for p in wp.get('flatrate', [])]

            # Use season-specific poster if available
            season_poster = None
            for s in reversed(seasons):
                if s.get('season_number') == current_season and s.get('poster_path'):
                    season_poster = f"https://image.tmdb.org/t/p/w500{s['poster_path']}"
                    break
            poster = season_poster or (
                f"https://image.tmdb.org/t/p/w500{item['poster_path']}" if item.get('poster_path') else None
            )

            base_title = details.get('name') or item.get('name', 'Unknown')
            # Append season number if multi-season show
            title = f"{base_title} — S{current_season}" if num_seasons > 1 else base_title

            overview  = (details.get('overview') or item.get('overview') or '')[:600]
            genres    = [g['name'] for g in (details.get('genres') or [])][:3]
            release   = last_air or details.get('first_air_date', '')

            return _tv_record(imdb_id or str(tmdb_id), imdb_id, title, overview,
                              poster, release, providers, genres, scores)

        elif source == 'tvmaze':
            show    = item['show']
            channel = item['channel']
            imdb_id = (show.get('externals') or {}).get('imdb')
            scores  = best_scores(imdb_id) if imdb_id else {}
            if not scores.get('audience'):
                avg = (show.get('rating') or {}).get('average')
                if avg:
                    scores['audience'] = round(float(avg) * 10)
            if not scores.get('critic') and not scores.get('audience'):
                return None
            img = show.get('image') or {}
            return _tv_record(
                str(show['id']), imdb_id, show.get('name', 'Unknown'),
                strip_html(show.get('summary', ''))[:600],
                img.get('medium') or img.get('original'),
                show.get('premiered', ''),
                [{'name': channel, 'color': channel_color(channel)}],
                (show.get('genres') or [])[:3], scores
            )

        elif source == 'trakt_show':
            ids     = item.get('ids') or {}
            imdb_id = ids.get('imdb')
            tmdb_id = ids.get('tmdb')
            scores  = best_scores(imdb_id) if imdb_id else {}
            if not scores.get('critic') and not scores.get('audience'):
                if item.get('rating'):
                    scores['audience'] = round(float(item['rating']) * 10)
                else:
                    return None
            providers = tmdb_watch_providers(tmdb_id, 'tv') if tmdb_id and TMDB_KEY else []
            poster = None
            if tmdb_id and TMDB_KEY:
                t = tmdb_get(f'/tv/{tmdb_id}')
                if t.get('poster_path'):
                    poster = f"https://image.tmdb.org/t/p/w500{t['poster_path']}"
            return _tv_record(
                imdb_id or str(ids.get('trakt', '')), imdb_id,
                item.get('title', 'Unknown'), (item.get('overview') or '')[:600],
                poster, str(item.get('year', '')), providers,
                (item.get('genres') or [])[:3], scores
            )
    except Exception:
        return None


def _tv_record(uid, imdb_id, title, overview, poster, release, providers, genres, scores):
    return {
        'id': uid, 'imdb_id': imdb_id, 'title': title, 'overview': overview,
        'poster': poster, 'release': release, 'media_type': 'tv',
        'providers': providers, 'genres': genres,
        'critic_score': scores.get('critic'), 'audience_score': scores.get('audience'),
        'rt_score': scores.get('rt'), 'rt_audience': scores.get('rt_audience'),
        'mc_score': scores.get('mc'), 'imdb_score': scores.get('imdb_display'),
        'letterboxd': scores.get('letterboxd'), 'trakt_score': scores.get('trakt'),
    }


# ── Claude Top Pick ─────────────────────────────────────────────────────────────

def generate_top_pick(movies, tv):
    if not ANTHROPIC_KEY:
        return None

    if os.path.exists(TOPPICK_FILE):
        try:
            with open(TOPPICK_FILE) as f:
                cached = json.load(f)
            if time.time() - cached.get('timestamp', 0) < TOPPICK_TTL:
                return cached['data']
        except Exception:
            pass

    def fmt(items, limit=10):
        lines = []
        for i in items[:limit]:
            sc = []
            if i.get('rt_score'):    sc.append(f"RT {i['rt_score']}%")
            if i.get('mc_score'):    sc.append(f"MC {i['mc_score']}")
            if i.get('imdb_score'):  sc.append(f"IMDb {i['imdb_score']}")
            if i.get('letterboxd'):  sc.append(f"LB {i['letterboxd']}%")
            if i.get('trakt_score'): sc.append(f"Trakt {i['trakt_score']}%")
            providers = ', '.join(p['name'] for p in (i.get('providers') or [])[:2]) or 'Unknown'
            genres    = ', '.join(i.get('genres') or [])
            line = f"- {i['title']} ({str(i.get('release',''))[:4]}) [{', '.join(sc)}] on {providers}"
            if genres:
                line += f" | {genres}"
            lines.append(line)
        return '\n'.join(lines)

    prompt = f"""You are the recommendation engine for StreamFader, a premium streaming guide.

Today's top-rated content across all streaming platforms:

MOVIES:
{fmt(movies)}

TV SHOWS:
{fmt(tv)}

Pick the single best thing to watch tonight. Weigh critic scores, audience scores, and broad appeal.

Respond in this exact JSON format:
{{
  "title": "exact title from the list",
  "media_type": "movie or tv",
  "headline": "one punchy sentence, max 12 words, why this is tonight's must-watch",
  "reason": "2-3 sentences. Specific — mention scores, what makes it stand out, who it's for.",
  "watch_if": "one short phrase — e.g. 'you loved Succession' or 'you want a thriller that does not let up'"
}}

Only return valid JSON. No markdown, no explanation."""

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        msg = client.messages.create(
            model='claude-opus-4-5',
            max_tokens=400,
            messages=[{'role': 'user', 'content': prompt}]
        )
        raw = msg.content[0].text.strip()
        raw = re.sub(r'^```(?:json)?\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)
        pick = json.loads(raw)

        all_items = movies + tv
        match = next(
            (i for i in all_items if i['title'].lower() == pick.get('title', '').lower()),
            None
        )
        if match:
            pick['poster']     = match.get('poster')
            pick['providers']  = match.get('providers', [])
            pick['imdb_id']    = match.get('imdb_id')
            pick['rt_score']   = match.get('rt_score')
            pick['mc_score']   = match.get('mc_score')
            pick['imdb_score'] = match.get('imdb_score')
            pick['letterboxd'] = match.get('letterboxd')

        os.makedirs('data', exist_ok=True)
        with open(TOPPICK_FILE, 'w') as f:
            json.dump({'timestamp': time.time(), 'data': pick}, f)

        return pick
    except Exception:
        return None


# ── Stale cache accessor ─────────────────────────────────────────────────────────

def get_cached_content():
    """Return cached data immediately. Sets _stale=True if TTL has expired."""
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE) as f:
            cached = json.load(f)
        data = cached['data']
        if time.time() - cached.get('timestamp', 0) >= CACHE_TTL:
            data['_stale'] = True
        return data
    except Exception:
        return None


# ── Entry point ─────────────────────────────────────────────────────────────────

def get_top_content(force=False):
    if not TMDB_KEY and not TRAKT_ID:
        return {'movies': [], 'tv': [], 'top_pick': None,
                'error': 'missing_keys', 'fetched_at': None}

    if not force and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as f:
                cached = json.load(f)
            if time.time() - cached.get('timestamp', 0) < CACHE_TTL:
                data = cached['data']
                if not data.get('top_pick'):
                    data['top_pick'] = generate_top_pick(data['movies'], data['tv'])
                return data
        except Exception:
            pass

    movies = fetch_movies()
    tv     = fetch_tv()
    pick   = generate_top_pick(movies, tv)

    data = {
        'movies':     movies,
        'tv':         tv,
        'top_pick':   pick,
        'fetched_at': datetime.now().isoformat(),
        'error':      None,
    }

    os.makedirs('data', exist_ok=True)
    with open(CACHE_FILE, 'w') as f:
        json.dump({'timestamp': time.time(), 'data': data}, f)

    return data
