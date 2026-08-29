import json
from datetime import date, datetime, timedelta
import argparse
import re
from typing import Optional

from src.init import init_redis
from src.movies.movies import Movie
from src.movies.services.cinemateca import get_movies_cinemateca
from src.movies.services.ims import get_movies_ims
from src.movies.services.reserva_cultural import (
    get_movies_reserva_cultural,
)
from src.movies.services.velox_tickets import (
    get_movies_belasartes,
    get_movies_cinema_augusta,
)
from src.utils import get_today

LIMIT_HOUR = 18
MIN_SCORE = 7
MOVIES_TTL = 18 * 3600  # 64800 seconds
TODAY = get_today()


def normalize_date_input(date_input: Optional[str]) -> str:
    if not date_input:
        return TODAY

    normalized_input = date_input.strip()

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized_input):
        return normalized_input

    if re.fullmatch(r"\d{2}-\d{2}", normalized_input):
        return f"{date.today().year}-{normalized_input}"

    if re.fullmatch(r"\d{1,2}", normalized_input):
        return f"{date.today().year}-{date.today().month:02d}-{int(normalized_input):02d}"

    return normalized_input


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
        movies.extend(get_movies_ims(date2search))
        movies.extend(get_movies_reserva_cultural(date2search))

        hash_obj = {
            "movies": json.dumps(
                [movie.to_json() for movie in movies],
                ensure_ascii=False
            ).encode('utf-8')
        }

        cache.setHash(
            hash_key,
            hash_obj,
            expire=MOVIES_TTL,
        )
    else:
        print("Cache hit, loading movies from cache.")
        cached_movies = movies_hash[b'movies'].decode('utf-8')
        movies_data = json.loads(cached_movies, parse_float=float)
        movies = [Movie(**movie, cached=True) for movie in movies_data]

    print("*" * 20)

    # Key on local as well, so the same film at two venues keeps
    # a row for each.
    movies = list(
        {
            (movie.name.lower(), movie.local): movie
            for movie in movies
        }.values()
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
        help="Date to search as YYYY-MM-DD, MM-DD, or day of month",
    )
    parser.add_argument(
        "--date",
        dest="date_option",
        help="Date to search as YYYY-MM-DD, MM-DD, or day of month",
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

    date2search = normalize_date_input(args.date_option or args.date)
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
