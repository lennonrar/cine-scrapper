from src.init import init_redis
import sys
from typing import Optional
from src.movies.movies import Movie
from src.movies.services.cinemateca import get_movies_cinemateca
from src.movies.services.mostra import get_movies_mostra
from src.movies.services.velox_tickets import get_movies_belasartes
from src.utils import get_today
from datetime import datetime
from datetime import date, timedelta
import json

LIMIT_HOUR = 18
MIN_SCORE = 7
TODAY = get_today()


def main(
        date2search: Optional[str] = TODAY,
        boring_mode: bool = False,
        force_refresh: bool = False
        ):

    cache = init_redis()
    hashKey = f"movies:{date2search}"
    movies_hash = cache.getHash(hashKey)

    if not movies_hash or force_refresh:
        print("Cache miss, fetching movies...")
        movies = get_movies_cinemateca(date2search)
        movies.extend(get_movies_belasartes(date2search))
        movies.extend(get_movies_mostra(date2search))

        hashObject = {
            "movies": json.dumps(
                [movie.to_json() for movie in movies], 
                ensure_ascii=False
            ),
            "lenght": str(len(movies)),
            "date": date2search
        }

        cache.setHash(
            hashKey,
            hashObject,
            expire=43200,  # 12 hours
        )
    else:
        print("Cache hit, loading movies from cache.")
        cached_movies = movies_hash[b'movies'].decode('utf-8')
        movies_data = json.loads(cached_movies, parse_float=float)
        movies = [
            Movie(
                name=movie['name'],
                local=movie['local'],
                time=movie['time'],
                tmdb_score=movie.get('tmdb_score'),
                duration=movie.get('duration'),
                cached=True
            ) for movie in movies_data]  # noqa: E501

    print("*" * 20)

    movies = list({movie.name.lower(): movie for movie in movies}.values())  # noqa: E501
    movies = sorted(movies, key=lambda x: (x.time or 0), reverse=False)

    for movie in movies:
        if boring_mode and not movie.meets_score_threshold():
            continue
        print(movie)


if __name__ == "__main__":
    date2search = None
    boring_mode = False
    force_refresh = False

    if len(sys.argv) > 1:
        date2search = sys.argv[1]

    if len(sys.argv) > 2 and sys.argv[2] == "--boring":
        boring_mode = True
        print(f"Boring mode activated: Only movies above {MIN_SCORE} will be shown")  # noqa: E501

    if len(sys.argv) > 2 and sys.argv[3] == "--force-refresh":
        force_refresh = True
        print("Force refresh activated: Fetching movies from source")  # noqa: E501

    if not date2search:
        date2search = TODAY

    current_hour = datetime.now().hour
    if date2search == TODAY and current_hour >= LIMIT_HOUR:
        date2search = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        print(f"After {LIMIT_HOUR}:00, showing results for tomorrow: " f"{date2search}")  # noqa: E501

    main(
        date2search=date2search,
        boring_mode=boring_mode,
        force_refresh=force_refresh
        )

    print("End of execution")
