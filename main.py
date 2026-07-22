import json
import sys
from datetime import date, datetime, timedelta
import argparse
from typing import Dict, Optional, cast

from src.init import init_redis
from src.movies.movies import Movie
from src.movies.services.cinemateca import get_movies_cinemateca
from src.movies.services.velox_tickets import (
    get_movies_belasartes,
    get_movies_cinema_augusta,
)
from src.utils import get_today

LIMIT_HOUR = 18
MIN_SCORE = 7
TODAY = get_today()


def main(
        date2search: Optional[str] = TODAY,
        boring_mode: bool = False,
        force_refresh: bool = False):

    cache = init_redis()
    hash_key = f"movies:{date2search}"
    movies_hash = cache.getHash(hash_key)

    if not movies_hash or force_refresh:
        print("Cache miss, fetching movies...")
        movies = get_movies_cinemateca(date2search)
        movies.extend(get_movies_belasartes(date2search))
        movies.extend(get_movies_cinema_augusta(date2search))

        hash_obj = {
            "movies": json.dumps(
                [movie.to_json() for movie in movies],
                ensure_ascii=False
            ).encode('utf-8')
        }

        cache.setHash(
            hash_key,
            hash_obj,
            expire=43200,  # 12 hours
        )
    else:
        print("Cache hit, loading movies from cache.")
        cached_movies = cast(
            Dict[bytes, bytes], movies_hash
        )[b'movies'].decode('utf-8')
        movies_data = json.loads(cached_movies, parse_float=float)
        movies = [
            Movie(
                name=movie['name'],
                local=movie['local'],
                time=movie['time'],
                tmdb_score=movie.get('tmdb_score'),
                duration=movie.get('duration'),
                cached=True
            )
            for movie in movies_data
        ]

    print("*" * 20)

    movies = list(
        {movie.name.lower(): movie for movie in movies}.values()
    )
    movies = sorted(movies, key=lambda x: (x.time or 0), reverse=False)

    for movie in movies:
        if boring_mode and not movie.meets_score_threshold():
            continue
        print(movie)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "date",
        nargs="?",
        help="Date to search in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--date",
        dest="date_option",
        help="Date to search in YYYY-MM-DD format",
    )
    parser.add_argument(
        "--boring",
        action="store_true",
        help="Show only movies above the minimum TMDB score",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Ignore cache and fetch from source",
    )

    args = parser.parse_args()

    date2search = args.date_option or args.date or TODAY
    boring_mode = args.boring
    force_refresh = args.force_refresh

    if boring_mode:
        print(
            f"Boring mode activated: Only movies above {MIN_SCORE} "
            f"will be shown"
        )

    if force_refresh:
        print("Force refresh activated: Fetching movies from source")

    current_hour = datetime.now().hour
    if date2search == TODAY and current_hour >= LIMIT_HOUR:
        date2search = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        print(
            f"After {LIMIT_HOUR}:00, showing results for tomorrow: "
            f"{date2search}"
        )

    main(
        date2search=date2search,
        boring_mode=boring_mode,
        force_refresh=force_refresh
    )

    print("End of execution")
