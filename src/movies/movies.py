from typing import Optional

from src.tmdb.tmdb_service import get_tmdb_score


class Movie:
    def __init__(
            self, name: str,
            local: str,
            time: str,
            tmdb_score: Optional[float] = None,
            duration: Optional[str] = None,
            cached: bool = False
            ):
        self.name = name
        self.local = local
        self.time = time
        self.duration = duration
        self.tmdb_score = (
            tmdb_score if tmdb_score or cached
            else get_tmdb_score(self._sanitize_moviename(name))
        )
        self.min_score = 7

    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'duration': self.duration,
            'date': self.time.split(' ')[0] if ' ' in self.time else None,
            'time': self.time.split(' ')[1] if ' ' in self.time else self.time,
            'local': self.local,
            'tmdb_score': self.tmdb_score
        }

    def __str__(self):
        score = self.tmdb_score if self.tmdb_score else 'N/A'
        return (f"{self.name:<50} | {self.time:<8} | {self.local:<50} | "
                f"TMDB Score: {score:<5}")

    def to_json(self):
        """Convert Movie object to JSON serializable dictionary"""
        return {
            'name': self.name,
            'local': self.local,
            'time': self.time,
            'tmdb_score': self.tmdb_score,
        }

    @staticmethod
    def _sanitize_moviename(moviename: str) -> str:
        if 'Ciência no Cinema' in moviename:
            return moviename.split(':')[-1]

        return moviename

    def meets_score_threshold(self) -> bool:
        """Check if movie meets minimum score threshold"""
        return (self.tmdb_score is not None and
                self.tmdb_score >= self.min_score)
