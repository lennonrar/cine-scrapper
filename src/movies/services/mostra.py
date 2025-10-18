from typing import List, Optional
from src.files import get_file
from src.movies.movies import Movie
from src.soup import get_soup
from src.utils import get_today
from datetime import datetime


def get_movies_mostra(
        date2search: Optional[str] = get_today()
        ) -> List[Movie]:
    print("Fetching movies from Mostra...")

    movies: List[Movie] = []
    html_content = get_file('./files/mostra_sp.html')
    mostra_soup = get_soup(html_content)
    mostra_list = mostra_soup.find_all('div', class_="card-content")
    for card in mostra_list:
        movie_name = card.find('h3', class_='card__title').text.strip()
        place = card.find('span', class_='place').text.strip()
        time = card.find('span', class_='time').text.strip()
        date = card.find('span', class_='date').text.strip()
        date = datetime.strptime(date, '%d/%m/%Y').strftime('%Y-%m-%d')
        if (date == date2search):
            movies.append(
                Movie(
                    movie_name,
                    place,
                    f"{time}"
                )
            )
    print(f"Found {len(movies)} movies")
    return movies
