# Design — TMDB score cache, longer TTL, link persistence

**Spec:** `redis-tmdb-cache` · **Phase:** 2 of 4 (Plan → **Design** → Tasks → Execution)
**Status:** approved and implemented as specified. One correction applied post-execution
— see §4 on pipeline transaction semantics.
**Implements:** [`plan.md`](plan.md) §3 requirements, under §6 decisions D1–D6
**Baseline:** `main` @ 8c1ae5c → delivered as `06e8ad1` on `feat/tmdb-cache`

> This document fixes key formats, module layout, signatures and call sequences.
> It contains illustrative code, but it is not the change — `tasks.md` orders the work
> and phase 4 writes it.

---

## 1. Shape of the change

Four files. No scraper is touched, and no `Movie(...)` call site changes — that is what
decision D1 bought.

| File | Change | Requirement |
| --- | --- | --- |
| `src/tmdb/tmdb_service.py` | Module-level cache; `get_tmdb_details` becomes a cache-aware wrapper around the existing logic | R1 |
| `src/redis.py` | Atomic write, corrected delete, honest annotations | R4 |
| `src/movies/movies.py` | `to_json()` emits `duration` so the serialized shape matches the constructor | R3.2 |
| `main.py` | TTL constant 64800; lossless rehydration | R2, R3 |

Nothing else in the repo changes.

---

## 2. Key space

Two namespaces, disjoint, different lifetimes.

```
movies:<YYYY-MM-DD>          hash   TTL 64800 s (18 h)     unchanged shape
  └─ movies → utf-8 JSON array of session objects

tmdb:<normalized-title>      hash   TTL 2592000 s (30 d) resolved
  ├─ score → "7.1"  or  ""           432000 s  (5 d) unresolved
  └─ url   → "https://…"  or  ""
```

### 2.1 Normalization (D2)

```python
def _cache_key(movie_name: str) -> str:
    normalized = " ".join(movie_name.split()).lower()
    return f"tmdb:{normalized}"
```

`" ".join(s.split())` collapses runs of whitespace and strips the ends in one step.
Lowercasing makes the key stable against venue-by-venue capitalization of the same
title. Redis keys are binary-safe, so accents, colons and slashes need no escaping.

The input is the string `get_tmdb_details` already receives — i.e. post
`_sanitize_moviename` (`movies.py:69-73`). The `-` recursion at `tmdb_service.py:30-32`
stays internal: it is a fallback *within* one resolution, and its intermediate query
strings are never keyed. One caller-visible title, one cache entry.

### 2.2 Why empty strings, not absent fields

Verified against redis-py 6.4:

| Value | Result |
| --- | --- |
| `""` | encodes to `b''` — valid |
| `None` | raises `DataError` |
| `hset(key, mapping={})` | raises `DataError: 'hset' with no key value pairs` |

So `None` can never be written, and the mapping can never be empty. Both fields are
therefore **always written**, with `""` standing for "no value". This also gives the
three states a clean encoding, with **key existence meaning "a lookup completed"**:

| State | `score` | `url` |
| --- | --- | --- |
| Key absent | — | — (never looked up) |
| No TMDB match at all | `""` | `""` |
| Matched, but unrated (`vote_count == 0`) | `""` | `"https://…"` |
| Matched and rated | `"7.1"` | `"https://…"` |

The third row is real: `tmdb_service.py:25` sets `score = None` when `vote_count` is 0
while `tmdb_url` is still built from the id. Without a distinct encoding for it, that
case would either re-request forever or lose its URL.

### 2.3 TTL selection (D3)

```python
TMDB_TTL      = 30 * 24 * 3600   # 2592000 — a score was resolved
TMDB_MISS_TTL = 5 * 24 * 3600    #  432000 — no score resolved
```

Rule: **`TMDB_TTL` if `score` is not None, else `TMDB_MISS_TTL`.** Keyed on the score
alone, not the URL — the score is the field worth re-checking, so the unrated-match row
above correctly takes the shorter window while still caching its URL.

The 6:1 ratio is the point: a resolved score is near-static and a month of reuse is
free, while an unresolved one is a standing bet that TMDB will never index the title —
worth re-testing every 5 days, which for this project's retrospective and festival
programming is the common case.

---

## 3. `src/tmdb/tmdb_service.py`

### 3.1 Structure

The existing function body is renamed `_fetch_tmdb_details` and left alone, including
its recursion. A new `get_tmdb_details` wraps it. The public name and signature are
unchanged, which is what keeps `movies.py` and all four scrapers untouched.

```
get_tmdb_details(name)          ← public, cache-aware      [new]
├── _cache_read(key)            ← returns (score, url) | None
├── _fetch_tmdb_details(name)   ← today's body, verbatim   [renamed]
└── _cache_write(key, score, url)
```

### 3.2 Sketch

```python
from redis.exceptions import RedisError

from src.redis import RedisCache

TMDB_TTL = 30 * 24 * 3600
TMDB_MISS_TTL = 5 * 24 * 3600

_cache = RedisCache()          # lazy: no connection until first command


def get_tmdb_details(movie_name: str) -> Tuple[Optional[float], Optional[str]]:
    key = _cache_key(movie_name)

    hit = _cache_read(key)
    if hit is not None:
        score, url = hit
        print(f"TMDB cache hit for {movie_name} ({score if score else 'no score'})")
        return score, url

    score, url = _fetch_tmdb_details(movie_name)
    _cache_write(key, score, url)
    return score, url


def _cache_read(key: str) -> Optional[Tuple[Optional[float], Optional[str]]]:
    try:
        entry = _cache.getHash(key)
    except RedisError:
        return None                      # R1.6 — degrade to a live request
    if not entry:
        return None
    try:
        raw_score = entry[b"score"].decode("utf-8")
        raw_url = entry[b"url"].decode("utf-8")
    except (KeyError, AttributeError, UnicodeDecodeError):
        return None                      # R1.6 — malformed entry
    try:
        score = float(raw_score) if raw_score else None
    except ValueError:
        return None
    return score, (raw_url or None)


def _cache_write(key: str, score, url) -> None:
    try:
        _cache.setHash(
            key,
            {"score": "" if score is None else str(score),
             "url": url or ""},
            expire=TMDB_TTL if score is not None else TMDB_MISS_TTL,
        )
    except RedisError:
        pass                             # a cold cache is not a failed run
```

### 3.3 Failure behaviour (R1.6)

Every cache interaction is wrapped. `redis.exceptions.RedisError` is the common base of
the connection, timeout and protocol errors (verified: a connect failure surfaces as
`TimeoutError`/`ConnectionError`, both subclasses of `RedisError`), so one `except`
covers the realistic failure set without swallowing `KeyboardInterrupt`.

Read failure → live request. Write failure → ignored. Malformed entry → live request.
With Redis unreachable the module behaves exactly as it does today, only slower.

`get_tmdb_score` (`tmdb_service.py:37-38`) delegates to `get_tmdb_details` and so is
cached for free; it needs no edit.

### 3.4 Consequences of D1 to accept knowingly

- Importing `tmdb_service` constructs a `RedisCache`. Safe: `redis.Redis()` is lazy
  (0.19 ms against an unroutable host, no socket opened), so import cannot block.
- `main.py` already calls `init_redis()`, so a second client object exists. Two clients
  against the same server is fine; it is untidy, not incorrect. Unifying them means
  passing a store around — which is exactly the option D1 rejected.
- Tests must monkeypatch `src.tmdb.tmdb_service._cache`.

---

## 4. `src/redis.py` (R4)

```python
from typing import Dict, Optional          # Optional retained for deleteHash's caller
import redis


class RedisCache:
    def __init__(self):
        self.client = redis.Redis(host='127.0.0.1', port=6379, db=0)

    def setHash(self, key: str, hash: dict, expire: int = 3600) -> None:
        with self.client.pipeline() as pipe:          # R4.1 — one round trip
            pipe.hset(key, mapping=hash)
            pipe.expire(key, expire)
            pipe.execute()

    def getHash(self, key: str) -> Dict[bytes, bytes]:   # R4.3 — was Optional[str]
        return self.client.hgetall(key)

    def deleteHash(self, key: str) -> None:
        self.client.delete(key)                        # R4.2 — was hdel(key)
```

Notes:

- `Redis.pipeline()` defaults to **`transaction=True`** in redis-py, so the pair is
  genuinely `MULTI`/`EXEC`-wrapped, not merely batched. Verified: `pipeline().transaction`
  is `True` without arguments. R4.1 therefore gets real atomicity — the write and its
  expiry commit together or not at all — in one round trip, which is stronger than the
  requirement asked for. Pass `transaction=False` to opt out; there is no reason to here.
- The `hash: str | dict` annotation loses the `str` arm: `hset(mapping=...)` requires
  a mapping, so `str` was never a valid argument.
- `getHash` returning `Dict[bytes, bytes]` (empty on miss) is what `hgetall` actually
  returns, which retires the `cast` at `main.py:70-72`.
- Method names stay `camelCase` to match the existing class. Renaming is a separate
  concern and is out of scope per plan §4.

---

## 5. `src/movies/movies.py` (R3.2)

One line. `to_json()` gains the field the constructor already accepts:

```python
def to_json(self):
    """Convert Movie object to JSON serializable dictionary"""
    return {
        'name': self.name,
        'local': self.local,
        'time': self.time,
        'duration': self.duration,        # ← added
        'tmdb_score': self.tmdb_score,
        'tmdb_url': self.tmdb_url,
        'ticket_url': self.ticket_url,
    }
```

After this, **every key `to_json()` emits is a parameter name of `Movie.__init__`.**
That invariant is what makes §6's rehydration safe, and it is the property to protect
in review.

`duration` is `None` for every scraper today (all four construct `Movie` with three
positional arguments). Including it costs four bytes per record and removes the
mismatch rather than papering over it.

---

## 6. `main.py` (R2, R3)

### 6.1 TTL constant

```python
LIMIT_HOUR = 18
MIN_SCORE = 7
MOVIES_TTL = 18 * 3600      # 64800 — R2.1, R2.2
TODAY = get_today()
```

and at the write site, `expire=MOVIES_TTL` replaces the inline `43200  # 12 hours`.

### 6.2 Lossless rehydration

Given §5's invariant, the whole read branch collapses:

```python
else:
    print("Cache hit, loading movies from cache.")
    cached_movies = movies_hash[b'movies'].decode('utf-8')
    movies_data = json.loads(cached_movies, parse_float=float)
    movies = [Movie(**movie, cached=True) for movie in movies_data]
```

Replacing `main.py:70-84`. This satisfies:

- **R3.1** — every emitted field is restored, `tmdb_url` and `ticket_url` included.
- **R3.2** — the `duration` mismatch is gone; the dict *is* the kwargs.
- **R3.4** — old blobs lack only `duration`, which defaults to `None` in the
  constructor, so they load unchanged. No migration, no version check.
- The `cast` and the `Dict`/`cast` imports become unused and are removed.

`cached=True` still suppresses the constructor's TMDB call, so a hit stays request-free
even for rows whose `tmdb_score` is `None`.

**Accepted fragility:** `Movie(**movie)` fails on an *unknown* key, so a future field
added to `to_json()` without a matching constructor parameter breaks reads until the
old blobs expire. That is the §5 invariant restated — acceptable at 18 h, and cheaper
than the defensive per-field mapping it replaces.

### 6.3 What `--force-refresh` does now (D4)

Unchanged code, but state the resulting behaviour explicitly, since it is the point of
the spec: the flag bypasses only the `movies:<date>` read. Every `Movie` constructed
during the re-scrape still consults `tmdb:*` and finds it warm. A forced refresh
re-fetches four venue pages and issues **zero** TMDB requests (AC1, AC7).

---

## 7. End-to-end sequences

**Cold — nothing cached**

```
main → getHash movies:2026-08-12          → {}  (miss)
     → 4 scrapers → N × Movie(...)
                    → get_tmdb_details    → getHash tmdb:<t>   → {}  (miss)
                                          → HTTP api.themoviedb.org
                                          → setHash tmdb:<t> ttl 30d | 5d
     → setHash movies:2026-08-12 ttl 18h
```

**Warm scores, cold list — e.g. `--force-refresh`, or the list expired at 18 h**

```
main → 4 scrapers → N × Movie(...)
                    → get_tmdb_details    → getHash tmdb:<t>   → hit
                                          → 0 HTTP requests
     → setHash movies:2026-08-12 ttl 18h
```

**Warm list**

```
main → getHash movies:2026-08-12          → hit
     → Movie(**row, cached=True)          → 0 HTTP requests, links intact
```

**Redis down**

```
main → init_redis() → ping raises → run aborts at startup, as it does today
```

The TMDB path's own guards (§3.3) matter for the narrower case where Redis dies
*mid-run* after the initial ping succeeded.

---

## 8. Verification plan

Mapped to plan §5. Each is a command, not a judgement call.

| AC | How |
| --- | --- |
| AC1 | `python main.py <date> --force-refresh` twice; second run prints no `Fetching TMDB score for …` lines |
| AC2 | Capture run 1 (miss) and run 2 (hit) stdout past the `****` separator; `diff` is empty |
| AC3 | Covered by AC2 — a dropped `TMDB:` link makes the diff non-empty |
| AC4 | `redis-cli TTL movies:<date>` → `0 < ttl <= 64800` |
| AC5 | Seed a nonsense title, run twice, assert one `Fetching TMDB score` line total |
| AC6 | Read back one of the pre-existing keys (`movies:2026-08-11`, `movies:2026-08-13`) written by current code; loads without error, `duration` is `None` |
| AC7 | `redis-cli TTL tmdb:<t>` unchanged across a `--force-refresh` |
| AC8 | `redis-cli DEL tmdb:<t>`, rerun; one live request, entry rewritten |

AC6 is time-sensitive — those two keys carry the old 12 h TTL and will expire. Capture
one blob to a file before starting so the case stays testable.

There is no test suite in the repo, so these are manual CLI checks. Adding `pytest` is
out of scope (plan §4); if you want automated coverage instead, say so and it becomes a
task with its own dependency change.

---

## 9. Open points

None blocking. Two worth a nod at review:

1. **Two `RedisCache` instances** (§3.4) — accepted cost of D1.
2. **`_cache_key` is not exported.** If a "clear one title" escape hatch is ever wanted
   (D4 declined it), that function plus `deleteHash` — now working, R4.2 — is the whole
   implementation.

---

## Next phase

On approval → `tasks.md` (phase 3): ordered, individually verifiable work items with
their requirement and AC references, sized so each is a reviewable commit.
