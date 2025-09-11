from typing import List, Optional
from src.movies.movies import Movie
from src.requests_service import get_html_page
from src.soup import get_soup
from src.tmdb.tmdb_service import get_tmdb_score
from src.utils import get_today


def get_movies_cinemateca(
        date2search: Optional[str] = get_today()
        ) -> List[Movie]:
    print("Fetching movies from Cinemateca...")
    movies: List[Movie] = []
    html_content = get_html_page("https://cinemateca.org.br/programacao/")
    soup = get_soup(html_content)
    today_movies = soup.find(id=f'tribe-events-calendar-day-{date2search}')
    if today_movies:
        today_events = today_movies.find_all(
            class_="tribe-events-calendar-month__calendar-event-details"
            )
        print(f"Found {len(today_events)} events")
        for event in today_events:
            event_datetime = event.find('time') if event.find(
                class_="tribe-events-calendar-month__calendar-event-datetime"
                ) else None
            event_title = event.find(
                "a",
                class_="tribe-events-calendar-month__calendar-event-"
                       "tooltip-title-link"
            )
            event_location = event.find('span', class_="deltec-location-name")
            if event_title and event_location and event_datetime:
                movie_name = event_title.get_text(strip=True)
                movies.append(
                    Movie(
                        movie_name,
                        event_location.get_text(strip=True),
                        event_datetime.get_text(strip=True),
                        get_tmdb_score(movie_name)
                    )
                )
    else:
        print("No movies found for today.")

    return movies
