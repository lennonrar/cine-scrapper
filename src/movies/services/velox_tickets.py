from typing import List, Optional

from requests import RequestException
from src.movies.movies import Movie
from src.requests_service import get_data
from src.utils import get_today

URL = "https://www.veloxtickets.com/Parceiro/P-BELASARTES/AjaxService/LocalDetail/ServiceGetSessions?date={}&localCode=BLT&cityCode=saopaulo"  # noqa: E501


def get_movies_belasartes(
        date2search: Optional[str] = get_today()
        ) -> List[Movie]:
    print("Fetching movies from Belas Artes...")
    movies = []
    url_belas = URL.format(date2search)
    print(url_belas)
    try:
        response = get_data(url_belas)
    except RequestException:
        return movies

    print(f"Found {len(response)} events")
    for obj in response:
        event = obj.get("event")
        rooms = obj.get("rooms")
        movie_name = event.get("eventTitle")
        movies.append(
            Movie(
                movie_name,
                rooms[0].get("roomName"),
                rooms[0].get("schedules")[0].get("startTime")
            )
        )

    return movies
