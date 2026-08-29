from typing import List, Optional

from requests import RequestException
from src.movies.movies import Movie
from src.requests_service import get_data
from src.utils import get_today

# ingresso.com's content API. city=1 is São Paulo; theater=330 is
# Reserva Cultural SP (confirmed against /v0/theaters/city/1 by
# urlKey "cinema-reserva-cultural-sao-paulo").
URL = (
    "https://api-content.ingresso.com/v0/sessions/city/1/theater/330"
    "/partnership/home/groupBy/sessionType?date={}"
)

# F1: requests' default User-Agent gets 403 Forbidden. Any other UA
# (browser string or even curl's) gets 200 - the value itself does
# not matter, only its presence. No other header is needed (verified
# identical 200 with and without Accept/Origin/DNT/Sec-*).
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def get_movies_reserva_cultural(
        date2search: Optional[str] = get_today()
        ) -> List[Movie]:
    print("Fetching movies from Reserva Cultural...")
    movies: List[Movie] = []
    url = URL.format(date2search)
    print(url)
    try:
        response = get_data(url, header=HEADERS)
    except RequestException:
        # F3/F4: a date with no programming returns 204 (empty body),
        # a malformed date returns 400. Both raise here before ever
        # reaching .json(), so both degrade to an empty schedule. This
        # is deliberate, not incidental - see get_data's HTTPStatus.OK
        # check: it can only ever raise on non-200, so a future 2xx
        # that is not exactly 200 would still land here, not crash on
        # an empty body.
        return movies

    # F5: the response is a list of days; omitting `date` returns 5,
    # passing it returns 1. Index defensively regardless.
    if not response:
        return movies
    day = response[0] if isinstance(response, list) else None
    if not isinstance(day, dict):
        return movies

    raw_movies = day.get("movies") or []
    print(f"Found {len(raw_movies)} movies")

    for raw_movie in raw_movies:
        title = raw_movie.get("title")
        if not title:
            continue
        session_types = raw_movie.get("sessionTypes") or []

        # R1.5/D2: group sessions by (title, room), one Movie per
        # group carrying all of that room's showtimes for the date.
        rooms: dict = {}
        for session_type in session_types:
            for session in session_type.get("sessions") or []:
                room = session.get("room")
                time = session.get("time")
                if not room or not time:
                    continue
                rooms.setdefault(room, []).append(time)

        for room, times in rooms.items():
            times.sort()
            movies.append(
                Movie(
                    title,
                    f"Reserva Cultural - {room}",  # D1
                    ", ".join(times),  # R1.6
                    # ticket_url left disabled per D3, matching
                    # velox_tickets.py / ims.py.
                    # ticket_url=session.get("siteURL"),
                )
            )

    return movies
