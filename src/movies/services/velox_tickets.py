from typing import List, Optional

from requests import RequestException
from src.movies.movies import Movie
from src.movies.services.showtime_groups import build_grouped_movies
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
    url = url_template.format(date2search)
    print(url)
    try:
        response = get_data(url)
    except RequestException:
        return []

    print(f"Found {len(response)} events")
    records = []
    for obj in response:
        event = obj.get("event")
        rooms = obj.get("rooms")
        if not event or not rooms:
            continue
        movie_name = event.get("eventTitle")
        for room in rooms:
            room_name = room.get("roomName")
            schedules = room.get("schedules") or []
            if not movie_name or not room_name:
                continue
            for schedule in schedules:
                start_time = schedule.get("startTime")
                if not start_time:
                    continue
                records.append(
                    {
                        "name": movie_name,
                        "local": room_name,
                        "time": start_time,
                        # ticket_url=ticket_url,
                        "original_title": event.get("originalTitle"),
                    }
                )

    return build_grouped_movies(records)


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
