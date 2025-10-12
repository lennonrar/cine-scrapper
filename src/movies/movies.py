from typing import Optional

from src.tmdb.tmdb_service import get_tmdb_score


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
        self.tmdb_score = tmdb_score if tmdb_score else get_tmdb_score(
            self._sanitize_moviename(name)
            )

    def __str__(self):
        return f"{self.name}, {self.time}, {self.local}, {self.tmdb_score}"

    @staticmethod
    def _sanitize_moviename(moviename: str) -> str:
        if 'Ciência no Cinema' in moviename:
            return moviename.split(':')[-1]

        return moviename
