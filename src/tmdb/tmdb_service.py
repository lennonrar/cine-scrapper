from typing import Optional
from urllib.parse import quote_plus

from src.requests_service import get_data
from src.tmdb.dtos import TMDBResponse
from src.utils import get_env


def get_tmdb_score(movie_name: str) -> Optional[float]:
    print(f"Fetching TMDB score for {movie_name}...")
    score = None
    encoded_movie_name = quote_plus(movie_name)
    url = f"https://api.themoviedb.org/3/search/movie?query={encoded_movie_name}"  # noqa: E501
    api_token = get_env('read_token')
    header = {
        "Authorization": f"Bearer {api_token}"
    }
    response_data = get_data(url=url, header=header)
    response = TMDBResponse(**response_data)
    if response.get('results'):
        vote_count = response.get('results', [])[0].get('vote_count', None)
        vote_avg = response.get('results', [])[0].get('vote_average', None)
        score = vote_avg if vote_count > 0 else None

    finder = movie_name.find('-')
    if not score and finder > 0:
        score = get_tmdb_score(movie_name.split('-')[-1])

    return score
