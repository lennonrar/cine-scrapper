# Cine Scrapper

A movie schedule scraper that collects information from various cinema venues and provides movie schedules with TMDB ratings.

## Sources

- Cinemateca
- Belas Artes
- Cinema Augusta
- IMS Paulista
- Reserva Cultural (São Paulo)

A film playing at more than one venue on the same day is now shown once
per venue instead of once overall — the dedupe key is `(name, local)`,
not just `name`, so a title at both Belas Artes and Reserva Cultural
prints twice.

## Prerequisites

- Docker and Docker Compose
- Python 3.x

## Setup

1. Clone the repository:
```bash
git clone https://github.com/lennonrar/cine-scrapper.git
cd cine-scrapper
```

2. Create a Python virtual environment (optional but recommended):
```bash
poetry install
```

4. Activate the Poetry shell:
```bash
poetry shell
```

## Running with Docker Compose

1. Start Redis using Docker Compose:
```bash
docker compose up -d
```

This will start a Redis instance on port 6379.

## Running the Program

### Basic Usage:
```bash
python main.py
```

This will show today's movies. If it's after 18:00, it will show tomorrow's schedule.

### Specific Date:
```bash
python main.py YYYY-MM-DD
```
Example:
```bash
python main.py 2025-10-19
```

You can also pass a bare day of month like `1` or `10`. This resolves to the
**next** time that day comes around: the current month if the day has not passed
yet, otherwise the following month. Running `python main.py 1` on August 28th
searches September 1st, not the August 1st already behind you. December rolls
into the next year.

A month-day value like `07-01` uses the current year and is not rolled forward.

### Show Only High-Rated Movies:
Add the `--boring` flag to show only movies with TMDB ratings above 7.0:
```bash
python main.py --boring
# or
python main.py 2025-10-19 --boring
```

### Force a Refresh:
Add the `--force-refresh` flag to bypass the movie-list cache and re-scrape
all venues:
```bash
python main.py --force-refresh
```
This re-fetches venue schedules only. Cached TMDB scores and links are kept
— it does not re-query TMDB for titles already resolved. To force a single
title's score to be re-fetched, delete its cache entry manually:
```bash
docker compose exec redis redis-cli DEL "tmdb:<title>"
```

## Features

- Caches movie-list results in Redis for 18 hours
- Caches TMDB scores and links per title, independent of the movie list
- Filters duplicate movies
- Shows TMDB ratings when available
- Sorts movies by showtime
- Option to filter low-rated movies

## Cache Management

The program uses Redis to cache movie data. Movie-list entries
(`movies:<date>`) expire after 18 hours (64800 seconds). TMDB entries
(`tmdb:<title>`) expire after 30 days if a score was found, or 5 days if
the title had no match.

To clear the cache manually:
```bash
docker compose exec redis redis-cli FLUSHALL
```

## Docker Compose Services

The `docker-compose.yml` configuration includes:
- Redis server on port 6379
- Persistent Redis data through Docker volumes