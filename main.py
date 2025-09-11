import sys
from typing import Optional
from src.movies.services.cinemateca import get_movies_cinemateca
from src.movies.services.velox_tickets import get_movies_belasartes
from src.utils import get_today
from datetime import datetime
from datetime import date, timedelta


def main(date2search: Optional[str]):
    movies = get_movies_cinemateca(date2search)
    movies.extend(get_movies_belasartes(date2search))
    print('*' * 20)

    for movie in movies:
        print(movie)


if __name__ == '__main__':
    date2search = None
    today = get_today()
    if len(sys.argv) > 1:
        date2search = sys.argv[1]

    if not date2search:
        date2search = today

    current_hour = datetime.now().hour
    if date2search == today and current_hour >= 20:
        date2search = (
            date.today() + timedelta(days=1)
            ).strftime('%Y-%m-%d')
        print(f"After 20:00, showing results for tomorrow: {date2search}")

    main(date2search)
    print('End of execution')
