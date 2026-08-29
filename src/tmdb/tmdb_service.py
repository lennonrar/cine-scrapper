from typing import Optional, Tuple
from urllib.parse import quote_plus

from redis.exceptions import RedisError

from src.redis import RedisCache
from src.requests_service import get_data
from src.tmdb.dtos import TMDBResponse
from src.utils import get_env

TMDB_TTL = 30 * 24 * 3600       # 2592000 seconds, 30 days: resolved score
TMDB_MISS_TTL = 5 * 24 * 3600   # 432000 seconds, 5 days: unresolved

_cache = RedisCache()


def _cache_key(movie_name: str) -> str:
    normalized = " ".join(movie_name.split()).lower()
    return f"tmdb:{normalized}"


def _cache_read(
    key: str,
) -> Optional[Tuple[Optional[float], Optional[str]]]:
    try:
        entry = _cache.getHash(key)
    except RedisError:
        return None                      # degrade to a live request
    if not entry:
        return None
    try:
        raw_score = entry[b"score"].decode("utf-8")
        raw_url = entry[b"url"].decode("utf-8")
    except (KeyError, AttributeError, UnicodeDecodeError):
        return None                      # malformed entry
    try:
        score = float(raw_score) if raw_score else None
    except ValueError:
        return None
    return score, (raw_url or None)


def _cache_write(
    key: str, score: Optional[float], url: Optional[str]
) -> None:
    try:
        _cache.setHash(
            key,
            {"score": "" if score is None else str(score),
             "url": url or ""},
            expire=TMDB_TTL if score is not None else TMDB_MISS_TTL,
        )
    except RedisError:
        pass                             # a cold cache is not a failed run


def _fetch_tmdb_details(
    movie_name: str,
) -> Tuple[Optional[float], Optional[str]]:
    print(f"Fetching TMDB score for {movie_name}...")
    score = None
    tmdb_url = None
    encoded_movie_name = quote_plus(movie_name)
    url = f"https://api.themoviedb.org/3/search/movie?query={encoded_movie_name}"  # noqa: E501
    api_token = get_env('read_token')
    header = {
        "Authorization": f"Bearer {api_token}"
    }
    response_data = get_data(url=url, header=header)
    response = TMDBResponse(**response_data)
    if response.get('results'):
        result = response.get('results', [])[0]
        vote_count = result.get('vote_count', None)
        vote_avg = result.get('vote_average', None)
        score = vote_avg if vote_count and vote_count > 0 else None
        tmdb_id = result.get('id')
        if tmdb_id:
            tmdb_url = f"https://www.themoviedb.org/movie/{tmdb_id}"

    finder = movie_name.find('-')
    if not score and finder > 0:
        return _fetch_tmdb_details(movie_name.split('-')[-1])

    return score, tmdb_url


def get_tmdb_details(
    movie_name: str,
) -> Tuple[Optional[float], Optional[str]]:
    key = _cache_key(movie_name)

    hit = _cache_read(key)
    if hit is not None:
        score, url = hit
        print(
            f"TMDB cache hit for {movie_name} "
            f"({score if score else 'no score'})"
        )
        return score, url

    score, url = _fetch_tmdb_details(movie_name)
    _cache_write(key, score, url)
    return score, url


def get_tmdb_score(movie_name: str) -> Optional[float]:
    score, _ = get_tmdb_details(movie_name)
    return score
