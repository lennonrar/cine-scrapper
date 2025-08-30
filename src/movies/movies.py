from typing import Optional


class Movie:
    def __init__(
            self, name: str,
            local: str,
            time: str,
            tmdb_score: Optional[float] = None
            ):
        self.name = name
        self.local = local
        self.time = time
        self.tmdb_score = tmdb_score

    def __str__(self):
        return f"{self.name}, {self.time}, {self.local}, {self.tmdb_score}"
