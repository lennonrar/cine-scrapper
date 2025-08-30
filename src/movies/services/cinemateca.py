from typing import List
from src.movies.movies import Movie
from src.requests_service import get_html_page
from src.soup import get_soup
from src.tmdb.tmdb_service import get_tmdb_score
from src.utils import get_today


def get_movies_cinemateca() -> List[Movie]:
    print("Fetching movies from Cinemateca...")
    movies: List[Movie] = []
    html_content = get_html_page("https://cinemateca.org.br/programacao/")
    soup = get_soup(html_content)
    today_movies = soup.find(id=f'tribe-events-calendar-day-{get_today()}')
    if today_movies:
        print("Found today's movies!")
        today_events = today_movies.find_all(
            class_="tribe-events-calendar-month__calendar-event-details"
            )
        print(f"Number of events found: {len(today_events)}")
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
