from typing import List, Optional

from requests import RequestException
from src.movies.movies import Movie
from src.requests_service import get_data
from src.utils import get_today

URL = "https://www.veloxtickets.com/Parceiro/P-BELASARTES/AjaxService/LocalDetail/ServiceGetSessions?date={}&localCode=BLT&cityCode=saopaulo"  # noqa: E501
URL_CINEMA_AUGUSTA = (
    "https://www.veloxtickets.com/Portal/AjaxService/LocalDetail/"
    "ServiceGetSessions?date={}&localCode=AG1&cityCode=saopaulo"
)


def _get_movies_from_url(
        title: str,
        url_template: str,
        date2search: Optional[str]
        ) -> List[Movie]:
    print(f"Fetching movies from {title}...")
    movies = []
    url = url_template.format(date2search)
    print(url)
    try:
        response = get_data(url)
    except RequestException:
        return movies

    print(f"Found {len(response)} events")
    for obj in response:
        event = obj.get("event")
        rooms = obj.get("rooms")
        movie_name = event.get("eventTitle")
        ticket_url = None
        for candidate in (
            event.get("ticketUrl"),
            event.get("salesUrl"),
            event.get("url"),
            event.get("link"),
            event.get("eventUrl"),
            event.get("detailUrl"),
            event.get("eventLink"),
            obj.get("ticketUrl"),
            obj.get("salesUrl"),
            obj.get("url"),
            obj.get("link"),
        ):
            if candidate:
                ticket_url = candidate
                break
        movies.append(
            Movie(
                movie_name,
                rooms[0].get("roomName"),
                rooms[0].get("schedules")[0].get("startTime"),
                # ticket_url=ticket_url,
            )
        )

    return movies


def get_movies_belasartes(
        date2search: Optional[str] = get_today()
        ) -> List[Movie]:
    return _get_movies_from_url("Belas Artes", URL, date2search)


def get_movies_cinema_augusta(
        date2search: Optional[str] = get_today()
        ) -> List[Movie]:
    return _get_movies_from_url(
        "Cinema Augusta",
        URL_CINEMA_AUGUSTA,
        date2search,
    )
