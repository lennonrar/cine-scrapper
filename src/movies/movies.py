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
            # TMDB indexes by original title, so a Portuguese release
            # title can miss entirely: "A Odisseia" returns 36 results
            # topped by an unrelated 0-vote film, while "The Odyssey"
            # returns the right one. Sources that carry the original
            # title win; the rest keep searching by name as before.
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

        # T8: a trailing release-status tag like "(Relançamento)" or
        # "(Remasterizado Em 4k)" defeats TMDB's title search entirely
        # (0 results), not just its ranking. Stripping it is safe -
        # the tag is never part of the actual title.
        without_tag = re.sub(r'\s*\([^)]*\)\s*$', '', moviename).strip()

        return without_tag or moviename

    def meets_score_threshold(self) -> bool:
        """Check if movie meets minimum score threshold"""
        return (self.tmdb_score is not None and
                self.tmdb_score >= self.min_score)
