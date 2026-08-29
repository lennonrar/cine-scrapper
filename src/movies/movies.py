import re
from typing import Optional

from src.tmdb.tmdb_service import get_tmdb_details


class Movie:
    def __init__(
            self, name: str,
            local: str,
            time: str,
            tmdb_score: Optional[float] = None,
            duration: Optional[str] = None,
            cached: bool = False,
            tmdb_url: Optional[str] = None,
            ticket_url: Optional[str] = None,
            original_title: Optional[str] = None
            ):
        self.name = name
        self.local = local
        self.time = time
        self.duration = duration
        self.ticket_url = ticket_url
        self.original_title = original_title
        self.tmdb_url = tmdb_url
        self.tmdb_score = tmdb_score
        if self.tmdb_score is None and not cached:
            # TMDB indexes by original title, so a Portuguese one can
            # match the wrong film or none at all. Prefer it when known.
            self.tmdb_score, self.tmdb_url = get_tmdb_details(
                self._sanitize_moviename(original_title or name)
            )
        self.min_score = 7

    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'duration': self.duration,
            'date': self.time.split(' ')[0] if ' ' in self.time else None,
            'time': self.time.split(' ')[1] if ' ' in self.time else self.time,
            'local': self.local,
            'tmdb_score': self.tmdb_score,
            'tmdb_url': self.tmdb_url,
            'ticket_url': self.ticket_url,
        }

    def __str__(self):
        score = self.tmdb_score if self.tmdb_score else 'N/A'
        base = (
            f"{self.name:<50} | {self.time:<20} | {self.local:<50} | "
            f"TMDB Score: {score:<5}"
        )
        links = []
        if self.ticket_url:
            links.append(f"Tickets: {self.ticket_url}")
        if self.tmdb_url:
            links.append(f"TMDB: {self.tmdb_url}")
        if links:
            return f"{base} | {' | '.join(links)}"
        return base

    def to_json(self):
        """Convert Movie object to JSON serializable dictionary"""
        return {
            'name': self.name,
            'local': self.local,
            'time': self.time,
            'duration': self.duration,
            'original_title': self.original_title,
            'tmdb_score': self.tmdb_score,
            'tmdb_url': self.tmdb_url,
            'ticket_url': self.ticket_url,
        }

    @staticmethod
    def _sanitize_moviename(moviename: str) -> str:
        if 'Ciência no Cinema' in moviename:
            return moviename.split(':')[-1]

        # A trailing tag like "(Relançamento)" makes TMDB return zero
        # results, so drop it before searching.
        without_tag = re.sub(r'\s*\([^)]*\)\s*$', '', moviename).strip()

        return without_tag or moviename

    def meets_score_threshold(self) -> bool:
        """Check if movie meets minimum score threshold"""
        return (self.tmdb_score is not None and
                self.tmdb_score >= self.min_score)
