import sys
from typing import Optional
from src.movies.services.cinemateca import get_movies_cinemateca
from src.movies.services.mostra import get_movies_mostra
from src.movies.services.velox_tickets import get_movies_belasartes
from src.utils import get_today
from datetime import datetime
from datetime import date, timedelta

LIMIT_HOUR = 18


def main(date2search: Optional[str]):
    movies = get_movies_cinemateca(date2search)
    movies.extend(get_movies_belasartes(date2search))
    movies.extend(get_movies_mostra(date2search))
    print('*' * 20)

    movies = list({movie.name.lower(): movie for movie in movies}.values())
    movies = sorted(movies, key=lambda x: (x.time or 0), reverse=False)

    for movie in movies:
        if boring_mode and not movie.meets_score_threshold():
            continue
        print(movie)


if __name__ == '__main__':
    date2search = None
    boring_mode = False
    today = get_today()
    if len(sys.argv) > 1:
        date2search = sys.argv[1]

    if len(sys.argv) > 2 and sys.argv[2] == '--boring':
        boring_mode = True
        print(f"Boring mode activated: Only movies above {MIN_SCORE} will be shown")
    if not date2search:
        date2search = today

    current_hour = datetime.now().hour
    if date2search == today and current_hour >= LIMIT_HOUR:
        date2search = (
            date.today() + timedelta(days=1)
            ).strftime('%Y-%m-%d')
        print(
            f"After {LIMIT_HOUR}:00, showing results for tomorrow: {date2search}"
        )

    main(date2search)
    print('End of execution')
