from typing import List, Optional

from requests import RequestException
from src.movies.movies import Movie
from src.requests_service import get_data
from src.utils import get_today

# ingresso.com content API: city 1 is São Paulo, theater 330 is
# Reserva Cultural SP.
URL = (
    "https://api-content.ingresso.com/v0/sessions/city/1/theater/330"
    "/partnership/home/groupBy/sessionType?date={}"
)

# The API answers 403 to requests' default User-Agent. Any other
# value works, and no other header is needed.
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
        # A date with no programming returns 204 and a bad date 400.
        # get_data raises on both, so neither is a real failure.
        return movies

    # The response is a list of days, one per date requested.
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

        # One Movie per room, carrying that room's showtimes.
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
                    f"Reserva Cultural - {room}",
                    ", ".join(times),
                    # ticket_url=session.get("siteURL"),
                    original_title=raw_movie.get("originalTitle"),
                )
            )

    return movies
