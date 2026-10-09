from datetime import datetime, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

from requests import RequestException
from src.movies.movies import Movie
from src.movies.services.showtime_groups import build_grouped_movies
from src.requests_service import get_data
from src.utils import get_today

TIMEZONE = ZoneInfo("America/Sao_Paulo")
URL = (
    "https://ims.com.br/wp-json/ims/v1/programacao-unidade-posts"
    "?unidade=11&evento-tipo[]=cinema&show_online=253428"
    "&date={timestamp}&viewing=week&start_date={timestamp}"
    "&slider_eventos_posts_id=null"
)


def _date_to_timestamp_ms(date2search: str) -> int:
    day = datetime.strptime(date2search, "%Y-%m-%d").replace(tzinfo=TIMEZONE)
    return int(day.timestamp() * 1000)


def get_movies_ims(
        date2search: Optional[str] = get_today()
        ) -> List[Movie]:
    print("Fetching movies from IMS...")
    timestamp = _date_to_timestamp_ms(date2search)
    url = URL.format(timestamp=timestamp)
    print(url)
    try:
        response = get_data(url)
    except RequestException:
        return []

    events = response.get("eventos_por_dia", {}).get(date2search)
    if not events:
        print("No movies found for today.")
        return []

    events = events.values() if isinstance(events, dict) else events
    print(f"Found {len(events)} events")
    records = []
    for event in events:
        horarios = event.get("horarios")
        if not horarios:
            continue
        local = event.get("outra_localidade") or event.get("unidade_title")
        for horario in horarios:
            # horarios encodes local wall-clock time as if it were UTC
            # (e.g. 16h in São Paulo is stored as 16:00 UTC), so decode as UTC.
            session_time = datetime.fromtimestamp(horario, tz=timezone.utc)
            records.append(
                {
                    "name": event.get("post_title"),
                    "local": local,
                    "time": session_time.strftime("%H:%M"),
                    # ticket_url=event.get("permalink"),
                }
            )

    return build_grouped_movies(records)
