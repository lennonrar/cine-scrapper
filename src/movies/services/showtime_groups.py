from collections import OrderedDict
from datetime import datetime
from typing import Any, Iterable

from src.movies.movies import Movie


def _time_sort_key(time: str) -> tuple[int, str]:
    normalized = time.strip()
    try:
        parsed = datetime.strptime(normalized, "%H:%M")
        return parsed.hour * 60 + parsed.minute, normalized
    except ValueError:
        return 24 * 60 + 1, normalized


def build_grouped_movies(records: Iterable[dict[str, Any]]) -> list[Movie]:
    grouped: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()

    for record in records:
        name = record.get("name")
        local = record.get("local")
        if not name or not local:
            continue

        key = (name, local)
        movie_group = grouped.setdefault(
            key,
            {
                "name": name,
                "local": local,
                "times": [],
                "tmdb_score": None,
                "duration": None,
                "tmdb_url": None,
                "ticket_url": None,
                "original_title": None,
            },
        )

        times = record.get("times")
        if times is None:
            time = record.get("time")
            if not time:
                continue
            times = [time]

        for time in times:
            movie_group["times"].append(time.strip())

        for field in (
            "tmdb_score",
            "duration",
            "tmdb_url",
            "ticket_url",
            "original_title",
        ):
            value = record.get(field)
            if movie_group[field] is None and value is not None:
                movie_group[field] = value

    movies: list[Movie] = []
    for movie_group in grouped.values():
        times = sorted(dict.fromkeys(movie_group["times"]), key=_time_sort_key)
        movies.append(
            Movie(
                movie_group["name"],
                movie_group["local"],
                ", ".join(times),
                tmdb_score=movie_group["tmdb_score"],
                duration=movie_group["duration"],
                tmdb_url=movie_group["tmdb_url"],
                ticket_url=movie_group["ticket_url"],
                original_title=movie_group["original_title"],
            )
        )

    return movies
