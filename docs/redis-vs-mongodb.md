# Storage layer in cine-scrapper: Redis vs. MongoDB vs. SQLite

Scope: `src/redis.py`, `src/init.py`, `main.py` — against `main` @ 8c1ae5c.

## Verdict

Redis is the right tool for what the code asks of it today — and the code asks for
almost nothing, which is the actual problem.

The cache stores one opaque JSON blob per date under a 12-hour TTL. Nothing indexes
it, nothing queries it, and it is discarded twice a day. Swapping in MongoDB to serve
that same access pattern is a straight downgrade: more memory, more disk, more setup,
slower reads, zero new capability.

A persistent store earns its place only if the goal changes from *"avoid re-scraping
within a day"* to *"keep a queryable record of what São Paulo cinemas played."* That is
a product decision, not a performance one — see [What only a queryable store
answers](#what-only-a-queryable-store-answers).

And if that is the goal, **MongoDB is the wrong persistent store for this project.**
SQLite delivers the same queries, the same history and better modelling of the TMDB
scores, while *removing* a dependency and a container instead of adding one. It is the
only candidate that could replace Redis outright rather than sit next to it — see
[modelled in SQLite](#the-same-feature-modelled-in-sqlite).

---

## What the cache does right now

The whole storage layer is 17 lines. `RedisCache` wraps three calls, and `main()`
uses exactly one key shape:

```
movies:2026-08-10                 Redis hash, TTL 43200s
  └─ field "movies"  →  utf-8 JSON array of every session, all four venues
```

One field. That is the entire schema — which makes the hash a plain string key
wearing a costume; `SET`/`GET` would be equivalent.

The read path (`main.py:45-84`) is all-or-nothing: `hgetall` the key, and on a hit
deserialize the array back into `Movie` objects with `cached=True` so the TMDB lookup
is skipped. On a miss, all four scrapers run, every title gets a TMDB round trip, and
the combined result is written back as one blob. Dedup by lowercased title and sorting
both happen in Python afterward, on the full list.

Two consequences matter more than the Redis-vs-Mongo question:

- **Failure gets cached as success.** `velox_tickets.py:26` and `ims.py:34` both
  swallow a `RequestException` and return `[]`. If IMS is down during a cache miss, a
  three-venue result is written under the date key and served confidently for 12 hours.
- **TMDB work is thrown away.** Scores are cached only as a side effect of being
  embedded in a date blob. The same film showing on five dates costs five API calls,
  and every blob expiry re-pays for all of them.

---

## Three defects in the current implementation

Independent of which database wins, these are wrong today.

### 1. Cache hits silently drop the ticket and TMDB links

`main.py:74-84` · `src/movies/movies.py:57-66`

`to_json()` serializes `tmdb_url` and `ticket_url`, but the reconstruction loop never
passes them back to the constructor — it passes `duration` instead, which `to_json()`
does not emit at all. So a cache hit prints bare rows while a cache miss prints rows
with links, and `duration` is permanently `None`.

### 2. `deleteHash` cannot work

`src/redis.py:16-17`

`self.client.hdel(key)` issues `HDEL` with no field arguments, which Redis rejects as
a wrong-arity error. Deleting a cached date needs `self.client.delete(key)`. Nothing
calls this method yet, which is the only reason it has not surfaced.

### 3. The TTL is a separate, non-atomic round trip

`src/redis.py:9-11`

`hset` then `expire` are two commands. A crash or connection drop between them leaves
an immortal key holding one day's schedule forever.

```python
def set_hash(self, key: str, mapping: dict, expire: int = 3600) -> None:
    with self.client.pipeline() as pipe:
        pipe.hset(key, mapping=mapping)
        pipe.expire(key, expire)
        pipe.execute()
```

Minor, same file: `getHash` is annotated `Optional[str]` but returns
`dict[bytes, bytes]` (empty dict on miss), which is why `main.py` needs the `cast`.

---

## The same feature, modelled in MongoDB

The interesting part of a document store is not that it holds JSON — Redis holds JSON
fine. It is that the unit of storage becomes the *session* rather than the *day*, and
that unit is independently indexed, upserted, and queried.

### Documents

```js
// sessions — one document per showing
{
  source:     "cinemateca",
  date:       "2026-08-10",
  name:       "Level Five",
  local:      "Sala Grande Otelo",
  time:       "19:00",
  tmdb:       { id: 66290, score: 7.1, url: "https://..." },
  ticket_url: null,
  scraped_at: ISODate("2026-08-10T09:12:44Z")
}

// scrape_runs — freshness per (source, date), replaces the TTL
{ source: "ims", date: "2026-08-10", scraped_at: ISODate(...), count: 4 }

// tmdb — title → score, cached once and reused across every date
{ _id: "level five", score: 7.1, url: "https://...", fetched_at: ISODate(...) }
```

### Store

```python
from datetime import datetime, timedelta, timezone
from pymongo import ASCENDING, MongoClient, UpdateOne

FRESH_FOR = timedelta(hours=12)


class MovieStore:
    def __init__(self, uri="mongodb://127.0.0.1:27017", db="cine"):
        self.db = MongoClient(uri).get_database(db)
        self.sessions = self.db.sessions
        self.runs = self.db.scrape_runs
        self.sessions.create_index(
            [("source", ASCENDING), ("date", ASCENDING),
             ("name", ASCENDING), ("time", ASCENDING)],
            unique=True, name="session_identity")
        self.sessions.create_index([("date", ASCENDING), ("local", ASCENDING)])
        self.runs.create_index(
            [("source", ASCENDING), ("date", ASCENDING)], unique=True)

    def is_fresh(self, source: str, date2search: str) -> bool:
        run = self.runs.find_one({"source": source, "date": date2search})
        return bool(run) and (
            datetime.now(timezone.utc) - run["scraped_at"] < FRESH_FOR)

    def save(self, source: str, date2search: str, movies: list) -> None:
        if movies:
            self.sessions.bulk_write([
                UpdateOne(
                    {"source": source, "date": date2search,
                     "name": m.name, "time": m.time},
                    {"$set": {**m.to_json(), "source": source,
                              "date": date2search,
                              "scraped_at": datetime.now(timezone.utc)}},
                    upsert=True)
                for m in movies
            ], ordered=False)
        self.runs.update_one(
            {"source": source, "date": date2search},
            {"$set": {"scraped_at": datetime.now(timezone.utc),
                      "count": len(movies)}},
            upsert=True)

    def load(self, date2search: str) -> list:
        return list(self.sessions.find({"date": date2search}, {"_id": 0}))
```

### Caller

The `if not movies_hash or force_refresh` branch collapses into a per-source loop,
which is the real behavioural win — a dead venue no longer poisons the other three:

```python
SOURCES = {
    "cinemateca":     get_movies_cinemateca,
    "belasartes":     get_movies_belasartes,
    "cinema_augusta": get_movies_cinema_augusta,
    "ims":            get_movies_ims,
}

for source, fetch in SOURCES.items():
    if force_refresh or not store.is_fresh(source, date2search):
        store.save(source, date2search, fetch(date2search))

movies = [Movie(cached=True, **row) for row in store.load(date2search)]
```

**Note:** that same loop is implementable on Redis today with one key per
`(source, date)`. It is not a MongoDB feature.

---

## The same feature, modelled in SQLite

Verified locally: Python 3.14.6 ships SQLite **3.51.2**, which supports `STRICT`
tables, `WITHOUT ROWID`, WAL, and `ON CONFLICT … DO UPDATE` upserts. The schema and
queries below were executed against it before being written down. Everything runs on
the stdlib `sqlite3` module — no new dependency, no container, no port.

The structural difference from both other options: **the TMDB score stops being
denormalized into every record.** In Redis it is copied into each entry of each date
blob; in MongoDB it is copied into each session document. In SQLite it lives once, in
its own table, and joins in. When a score changes, that is one row instead of N.

### Schema

```sql
CREATE TABLE IF NOT EXISTS sessions (
    source      TEXT NOT NULL,
    date        TEXT NOT NULL,          -- YYYY-MM-DD
    name        TEXT NOT NULL,
    local       TEXT NOT NULL,
    time        TEXT NOT NULL,
    ticket_url  TEXT,
    scraped_at  TEXT NOT NULL,
    PRIMARY KEY (source, date, name, time)
) STRICT, WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS sessions_by_date ON sessions(date, local);

CREATE TABLE IF NOT EXISTS tmdb (
    title       TEXT PRIMARY KEY,       -- lowercased, post-sanitize
    tmdb_id     INTEGER,
    score       REAL,
    url         TEXT,
    fetched_at  TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS scrape_runs (
    source      TEXT NOT NULL,
    date        TEXT NOT NULL,
    scraped_at  TEXT NOT NULL,
    count       INTEGER NOT NULL,
    PRIMARY KEY (source, date)
) STRICT, WITHOUT ROWID;
```

`STRICT` is worth taking: it is the one thing here that would have caught the schema
drift described in defect #1, by refusing a wrong-typed column outright instead of
storing it and failing later.

### Store

```python
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "cine.db"
FRESH_FOR = timedelta(hours=12)


class MovieStore:
    def __init__(self, path: Path = DB_PATH):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    def is_fresh(self, source: str, date2search: str) -> bool:
        row = self.db.execute(
            "SELECT scraped_at FROM scrape_runs WHERE source=? AND date=?",
            (source, date2search)).fetchone()
        return bool(row) and (
            datetime.now(timezone.utc)
            - datetime.fromisoformat(row["scraped_at"]) < FRESH_FOR)

    def save(self, source: str, date2search: str, movies: list) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.db:                      # one transaction: both or neither
            self.db.executemany(
                """INSERT INTO sessions
                       (source, date, name, local, time, ticket_url, scraped_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source, date, name, time) DO UPDATE SET
                       local      = excluded.local,
                       ticket_url = excluded.ticket_url,
                       scraped_at = excluded.scraped_at""",
                [(source, date2search, m.name, m.local, m.time,
                  m.ticket_url, now) for m in movies])
            self.db.execute(
                """INSERT INTO scrape_runs (source, date, scraped_at, count)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(source, date) DO UPDATE SET
                       scraped_at = excluded.scraped_at,
                       count      = excluded.count""",
                (source, date2search, now, len(movies)))

    def load(self, date2search: str, min_score: float | None = None) -> list:
        # named params, not qmark: a bare "?" and "?1" collide on index 1
        return self.db.execute(
            """SELECT s.name, s.local, MIN(s.time) AS time, s.ticket_url,
                      t.score AS tmdb_score, t.url AS tmdb_url
                 FROM sessions s
                 LEFT JOIN tmdb t ON t.title = lower(s.name)
                WHERE s.date = :date
                  AND (:min_score IS NULL OR t.score >= :min_score)
             GROUP BY lower(s.name)
             ORDER BY time""",
            {"date": date2search, "min_score": min_score}).fetchall()

    def tmdb_get(self, title: str) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT score, url FROM tmdb WHERE title=?", (title.lower(),)
        ).fetchone()
```

### What that deletes from `main.py`

The SQLite version absorbs work that is currently hand-rolled in Python:

| Today | After |
| --- | --- |
| `main.py:88-90` — dedup by lowercased title via dict comprehension (silently keeps the *last* match) | `GROUP BY lower(s.name)` — the rule becomes explicit and reviewable |
| `main.py:91` — `sorted(..., key=lambda x: (x.time or 0))`, a string sort | `ORDER BY time` |
| `main.py:94` — `if boring_mode and not movie.meets_score_threshold(): continue` | `AND t.score >= ?` — filtered before it leaves the DB |
| `movies.py:24-27` — TMDB fetched per `Movie` construction | `tmdb_get()` first, network call only on a real miss |
| `src/redis.py` (17 lines) + `redis` dependency + `docker-compose.yml` | stdlib `sqlite3`, one file `cine.db` |

The `--boring` flag becomes a `WHERE` clause rather than a print-time `continue`, which
also fixes a subtlety in the current code: today, filtering happens *after* dedup, so a
dedup that discards the scored copy of a title can drop a movie that should have passed.

### Transactions

`with self.db:` commits both writes or neither. This is the one place SQLite is
straightforwardly ahead of MongoDB in the deployment shape being proposed: **MongoDB
multi-document transactions require a replica set**, so a single standalone `mongo`
container cannot give you the sessions-write and freshness-marker-write atomically.
Redis needs an explicit pipeline/`MULTI`. SQLite gives it in a context manager.

### The honest costs

- **No TTL.** Redis evicts for free; here you compare `scraped_at`, and prune manually
  if you ever care (`DELETE FROM sessions WHERE date < date('now','-1 year')`). Same
  cost as the MongoDB design.
- **Single writer.** Concurrent writers get `database is locked`. WAL gives one writer
  plus many concurrent readers, which covers this CLI completely — the per-source loop
  is sequential — but it is a real ceiling if the scraper ever becomes a service.
- **Not a network store.** A web frontend on another host cannot share `cine.db`.
  Redis and MongoDB can. This is the scenario that would justify either of them.
- **Explicit migrations.** Adding `duration` means an `ALTER TABLE`, where MongoDB
  would just accept the new field. That is a cost — and also why the drift bug in
  defect #1 could not have happened silently.

---

## Side by side

| Axis | Redis (as built) | MongoDB | SQLite |
| --- | --- | --- | --- |
| **Unit of storage** | One blob per date; read/write the whole day | ✅ One doc per session | ✅ One row per session |
| **Read latency** | ~0.1–0.3 ms — in-memory, but over a loopback socket | ~1–5 ms local, disk-backed | ✅ Sub-ms; in-process, **no round trip at all** |
| **Secondary queries** | None; `SCAN` + fetch + JSON-parse every date in Python | ✅ Indexed `find`/`aggregate`, server-side | ✅ Full SQL + indexes, in-process |
| **Relational modelling** | n/a — score copied into every entry | Score copied into every doc, or `$lookup` | ✅ `tmdb` table joined in; score stored once |
| **Expiry model** | ✅ Native TTL, free | Compare `scraped_at`, or a TTL index that destroys the history you switched for | Compare `scraped_at`; manual `DELETE` to prune |
| **History** | Gone after 12 h by design | ✅ Retained | ✅ Retained |
| **Partial-failure isolation** | Not as built — a failed source is cached as an empty day | Falls out of per-source freshness | Falls out of per-source freshness |
| **TMDB score reuse** | Not as built; needs a 2nd key namespace | Needs a 2nd collection | ✅ Needs a 2nd table — and a join, so it stays correct |
| **Multi-write atomicity** | Explicit pipeline / `MULTI` | ⚠️ Multi-doc txns **require a replica set** — a standalone container can't | ✅ `with self.db:` |
| **Concurrent writers** | ✅ Many | ✅ Many | ⚠️ One (WAL: 1 writer + N readers) |
| **Network access** | ✅ Shared across hosts | ✅ Shared across hosts | ⚠️ Local file only |
| **Schema drift** | No version field; old blobs deserialize wrong until they expire (happening now) | Accepts the new field silently — same class of bug | ✅ `STRICT` + `ALTER TABLE`: explicit, can't drift silently |
| **Footprint** | `redis:alpine` 71 MB pulled; few MB resident | ≈700–800 MB image; WiredTiger reserves ≥256 MB cache | ✅ Zero infra; ~2 MB file for a year of data |
| **Dependencies** | `redis` pkg + compose service | `pymongo` + compose service | ✅ stdlib `sqlite3`; **removes** both |
| **Durability** | AOF is on, so writes survive restart — but the TTL means they were never meant to | ✅ Journaled | ✅ WAL journaled |
| **Code cost** | ✅ 17 lines, already written | ~50 lines + indexes + service + connection handling | ~60 lines + schema; deletes `src/redis.py` and `docker-compose.yml` |

**On latency:** it does not matter for any of the three. A cache miss costs four HTTP
scrapes plus a TMDB call per title — seconds. Every option here is noise against that,
and the row is included only to retire the "but Redis is faster" argument: for an
in-process single-user CLI, it isn't. SQLite has no socket to cross.

---

## What only a queryable store answers

This is the whole case for switching, so it is worth being concrete. None of these are
expressible against the current key layout without pulling every date into Python.

**MongoDB — which venue programmes the most well-rated films?**

```js
db.sessions.aggregate([
  {$match: {"tmdb.score": {$gte: 7}, date: {$gte: "2026-08-01"}}},
  {$group: {_id: "$local", n: {$sum: 1}, titles: {$addToSet: "$name"}}},
  {$sort: {n: -1}}
])
```

**SQLite, same question:**

```sql
SELECT s.local, COUNT(*) AS n, GROUP_CONCAT(DISTINCT s.name) AS titles
  FROM sessions s
  JOIN tmdb t ON t.title = lower(s.name)
 WHERE t.score >= 7 AND s.date >= '2026-08-01'
 GROUP BY s.local
 ORDER BY n DESC;
```

Same answer, one fewer service, and runnable straight from a terminal with
`sqlite3 cine.db` — no client library, no container, no connection string.

**Redis, same question:**

```python
rows = []
for k in r.scan_iter("movies:2026-08-*"):
    rows += json.loads(r.hget(k, "movies"))
# then group in Python…
# …over dates that expired 12 hours ago
```

N round trips, full deserialization, and most of the month is already evicted.

Other questions in the same family: *how often does a given film get programmed?* ·
*which titles am I repeatedly missing?* · *did Belas Artes move a session time after I
looked?* Each needs retained, per-session, indexed records. If none of those are
interesting to the project, MongoDB has nothing to sell.

---

## The framing that actually matters

"Redis vs. MongoDB" sets up a comparison the project does not have — both are NoSQL.
The real axis is **opaque blob under one key** vs. **indexed collection of records**,
and that axis cuts across products rather than between them.

- **Redis can be the document store.** With Redis Stack, `JSON.SET` plus an
  `FT.CREATE` index over `$.local` and `$.tmdb.score` gives secondary queries and
  aggregation without leaving the service already in compose. A different image, not a
  different architecture.
- **MongoDB can be just as opaque.** One document per date with an array field
  reproduces every limitation above, at higher cost.
- **SQLite is not a compromise here, it is the fit.** A single file, no daemon, no
  compose service, real indexes, real joins — and it ships with Python. For a
  single-user CLI holding a few thousand rows it wins on every axis except concurrent
  writers and network access, neither of which this project has.

The "NoSQL" framing is doing work it should not. The reason to leave Redis is the
*shape* of the storage unit, not the letter S in SQL — and once the unit becomes a
session record with a foreign key to a TMDB score, that shape is relational.

---

## Recommendation

**1. Fix the three defects first.** The dropped-links bug is user-visible on every
cache hit and has nothing to do with the storage engine.

**2. Then answer one question: do you want history and queries?**

*No — it is only a scrape cache.* Keep Redis and change the key layout: one key per
`(source, date)` so a dead venue is not cached as an empty schedule, plus a
`tmdb:<title>` namespace with a long TTL so scores stop being re-fetched. A few dozen
lines, no new service, and it captures most of what MongoDB was being considered for.

*Yes.* Go to SQLite and **delete Redis rather than adding to it.** At this data volume
a hot cache in front of a local file is pure overhead — the file *is* the cache. That
drops the `redis` dependency, `src/redis.py`, `src/init.py`, and `docker-compose.yml`,
and replaces them with one stdlib module and one `cine.db`. It is the only option on
this page that makes the project smaller.

**3. MongoDB is the answer to a question this project has not asked.** It would be
justified if the scraper became a networked service with multiple writers across hosts
— and even then, given a session table with a foreign key to a scores table, Postgres
would be the more natural pick than a document store.

Replacing Redis with MongoDB to serve the current access pattern would add an ~800 MB
dependency, slow down reads, and deliver no capability the code uses. Replacing it with
SQLite delivers every capability MongoDB was wanted for and removes a container.

---

*Latency and footprint figures are order-of-magnitude. The `redis:alpine` size (71 MB)
is from the locally pulled image. The SQLite version (3.51.2), `STRICT` table support
and upsert behaviour were verified locally against Python 3.14.6. MongoDB figures are
typical published values, not measured on this machine.*
