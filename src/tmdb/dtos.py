from typing import List, Optional, TypedDict


class MovieResult(TypedDict):
    adult: bool
    backdrop_path: Optional[str]
    genre_ids: List[int]
    id: int
    original_language: str
    original_title: str
    overview: str
    popularity: float
    poster_path: Optional[str]
    release_date: str
    title: str
    video: bool
    vote_average: float
    vote_count: int


class TMDBResponse(TypedDict):
    page: int
    results: List[MovieResult]
    total_pages: int
    total_results: int

    def __init__(self, response):
        self.page = response.get("page", 1)
        self.results = [
            MovieResult(**result) for result in response.get("results", [])
            ]
        self.total_pages = response.get("total_pages", 1)
        self.total_results = response.get("total_results", 0)
