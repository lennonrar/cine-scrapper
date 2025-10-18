# Cine Scrapper

A movie schedule scraper that collects information from various cinema venues and provides movie schedules with TMDB ratings.

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

### Show Only High-Rated Movies:
Add the `--boring` flag to show only movies with TMDB ratings above 7.0:
```bash
python main.py --boring
# or
python main.py 2025-10-19 --boring
```

## Features

- Caches results in Redis for 6 hours
- Filters duplicate movies
- Shows TMDB ratings when available
- Sorts movies by showtime
- Option to filter low-rated movies

## Cache Management

The program uses Redis to cache movie data. Cache entries expire after 6 hours (21600 seconds).

To clear the cache manually:
```bash
docker compose exec redis redis-cli FLUSHALL
```

## Docker Compose Services

The `docker-compose.yml` configuration includes:
- Redis server on port 6379
- Persistent Redis data through Docker volumes