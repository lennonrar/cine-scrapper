# Plan — TMDB score cache, longer TTL, link persistence

**Spec:** `redis-tmdb-cache` · **Phase:** 1 of 4 (Plan → Design → Tasks → Execution)
**Status:** approved — all open questions resolved, see §6
**Baseline:** `main` @ 8c1ae5c

> This document defines **what** changes and **why**, and the conditions under which
> the change is done. It deliberately contains no code, key formats, or module
> layout — those are decided in `design.md` and only after this document is approved.

---

## 1. Context

`main.py` caches one JSON blob per date in Redis under `movies:<YYYY-MM-DD>` with a
12-hour TTL. Two costs follow from that shape:

- **TMDB requests are re-paid on every cache miss.** Scores are stored only as a side
  effect of being embedded in a date blob. `Movie.__init__` (`src/movies/movies.py:24-27`)
  issues an HTTP call per title constructed, so a film showing on five dates costs five
  identical lookups, and every blob expiry re-pays for the whole day's list.
- **The cached copy is lossy.** `to_json()` serializes `tmdb_url` and `ticket_url`, but
  the rehydration loop at `main.py:74-84` passes neither back to the constructor — it
  passes `duration`, which `to_json()` never emits. A cache hit therefore prints
  different, poorer output than a cache miss for the same date.

Storage engine stays Redis. The alternatives were evaluated in
[`../../redis-vs-mongodb.md`](../../redis-vs-mongodb.md); this change implements the
"keep Redis, improve the key layout" path from that document's recommendation.

---

## 2. Goals

| # | Goal | Rationale |
| --- | --- | --- |
| G1 | A TMDB result is fetched at most once per title per retention window, regardless of how many dates or runs reference it | Removes the dominant cost of a cache miss |
| G2 | Movie list freshness window extends from 12 h to 18 h | Requested; fewer full re-scrapes per day |
| G3 | A movie recovered from cache is indistinguishable from a freshly scraped one | Fixes user-visible loss of the TMDB link |

---

## 3. Requirements

### R1 — TMDB results are cached under their own namespace

- **R1.1** A TMDB lookup result is persisted in Redis keyed by the movie title,
  independently of any date key.
- **R1.2** Before issuing a TMDB HTTP request, the code consults that cache; on a hit
  no request is made.
- **R1.3** Both the **score** and the **TMDB URL** are stored and returned together. A
  hit must not require a follow-up request to recover the URL.
- **R1.4** A lookup that finds no match is also recorded ("negative caching"), so
  unmatched titles do not re-request on every run. Retrospective and festival
  programming produces many permanent non-matches; without this, R1 delivers little for
  exactly the titles that dominate this project's sources.
- **R1.5** TMDB entries expire on their own schedule, independent of and substantially
  longer than the movie-list window. Scores drift slowly; venue schedules do not.
- **R1.6** A cache read that fails or returns a malformed entry must fall back to a live
  request, never crash the run.

### R2 — Movie-list TTL becomes 18 hours

- **R2.1** The `movies:<date>` expiry changes from 43200 s to 64800 s (18 h).
- **R2.2** The value is a named constant, not a literal at the call site.
- **R2.3** *Accepted consequence:* an evening run writes tomorrow's key (see
  `main.py:137-139`), which will now expire around midday tomorrow rather than at
  breakfast. Tomorrow's evening run re-scrapes. This is understood and accepted, not a
  defect.

### R3 — Cached movies round-trip without loss

- **R3.1** Every field written by `to_json()` is restored on read. Specifically
  `tmdb_url` and `ticket_url`, which are currently dropped.
- **R3.2** The serialized shape and the constructor's parameters must agree; the
  present `duration` mismatch is removed by making one match the other.
- **R3.3** For a given date, output produced from a cache hit is identical to output
  produced from a cache miss.
- **R3.4** Blobs already written in the old format must still load without error.
  Fields absent from an old blob resolve to `None`.

### R4 — Adjacent fixes in the files being touched

Included because the change edits these exact lines; each is independently small. Call
them out for veto if you want the diff narrower.

- **R4.1** `setHash` writes the value and its expiry atomically. Adding a second key
  type doubles the exposure to the current two-round-trip write, which can leave a key
  with no expiry if the connection drops between them (`src/redis.py:9-11`).
- **R4.2** `deleteHash` is corrected — `hdel(key)` with no fields is a wrong-arity error
  and cannot work (`src/redis.py:16-17`).
- **R4.3** `getHash`'s return annotation matches what it returns, removing the need for
  the `cast` at `main.py:70-72`.

---

## 4. Out of scope

| Excluded | Why |
| --- | --- |
| Per-`(source, date)` keys / partial-failure isolation | Real problem (a failed venue is cached as an empty schedule) but a separate behavioural change with its own risk. Own spec. |
| Any migration to SQLite, MongoDB, or Redis Stack | Settled: staying on Redis. |
| Deduplication and sort-order behaviour (`main.py:88-91`) | Untouched, including the string-sort of `time`. |
| Scraper/parsing changes in `src/movies/services/*` | No source behaviour changes. |
| Redis connection config (host/port hardcoded at `src/redis.py:7`) | Pre-existing; not required by these goals. |
| Reinstating the commented-out `ticket_url` arguments at the call sites | R3 makes the round-trip lossless so it works when re-enabled; enabling it is a separate call. |

---

## 5. Acceptance criteria

Each is observable from the CLI or `redis-cli`; the design phase must keep them testable.

| # | Criterion |
| --- | --- |
| AC1 | Two consecutive `--force-refresh` runs for the same date: the second issues **zero** TMDB HTTP requests. |
| AC2 | For one date, output of a cache-miss run and a subsequent cache-hit run are byte-identical. |
| AC3 | A TMDB URL is present in cache-hit output wherever it is present in cache-miss output. |
| AC4 | `TTL movies:<date>` immediately after a write is `> 0` and `<= 64800`. |
| AC5 | A title with no TMDB match issues no request on the second run. |
| AC6 | A key written by the current code still loads under the new code without error. |
| AC7 | TMDB keys survive `--force-refresh` and outlive `movies:<date>` keys. |
| AC8 | With Redis reachable but the TMDB entry absent, behaviour is identical to today. |

---

## 6. Decisions (resolved 2026-08-12)

All six are settled. `design.md` implements exactly these.

- **D1 — Cache lookup lives in a module-level client inside `src/tmdb/tmdb_service.py`.**
  *(Q1)* `tmdb_service` owns a module-scoped `RedisCache` and consults it internally.
  No call site changes: `Movie.__init__` keeps calling `get_tmdb_details(name)` and the
  scrapers are untouched. Chosen for the smallest diff.
  *Accepted trade-offs:* network I/O stays inside a constructor, and the module carries
  global state that tests must monkeypatch. Verified safe at import time — `redis.Redis()`
  does not connect until the first command (measured 0.19 ms against an unroutable
  host), so importing the module cannot block or fail.
- **D2 — Key derives from the caller's sanitized title** *(Q2)*, normalized by
  lowercasing and collapsing whitespace. The `-` recursion in `get_tmdb_details`
  (`tmdb_service.py:30-32`) stays an internal detail; intermediate queries are not
  cached separately.
- **D3 — Retention: 30 days for a resolved score, 5 days for an unresolved one** *(Q3)*.
  Both set by you. The unresolved window is the shorter of the two because a title
  gaining a TMDB entry is likelier than an already-published score changing. Both are
  single constants; adjust freely.
- **D4 — `--force-refresh` does not drop TMDB entries** *(Q4)*. It re-scrapes venues
  only; scores survive. AC7 encodes this. No new flag is added, so the only way to
  clear a score is manual (`redis-cli DEL tmdb:<title>`) or waiting out D3.
- **D5 — A TMDB entry is a Redis hash** *(Q5)*, reusing the existing `setHash`/`getHash`
  methods rather than adding a string-key API.
- **D6 — No version marker on the movie blob** *(Q6)*. R3.4 covers the one migration
  actually in front of us.

**R4 confirmed in scope** — all three fixes (atomic write, `deleteHash`, return
annotation).

---

## 7. Risks

| Risk | Mitigation |
| --- | --- |
| Cached score becomes wrong for a title | Bounded by D3's 30-day window. D4 declined a refresh flag, so the only manual remedy is `redis-cli DEL tmdb:<title>`. Widening the window from 5 to 30 days raises this risk in exchange for the cheaper refresh path — accepted. |
| Negative caching hides a title that later gains a TMDB entry | Shorter unresolved TTL — 5 days (D3) |
| Q1's third option touches all four scrapers | Behaviour is covered by AC2/AC3; keep it a pure refactor with no parsing changes |
| TMDB key growth is unbounded | Every entry carries a TTL (R1.5); volume is a few hundred titles |
| Two live keys are already in Redis in the old format | R3.4 + AC6 |

---

## 8. Definition of done

1. All requirements in §3 implemented.
2. All acceptance criteria in §5 demonstrated.
3. No item from §4 present in the diff.
4. `README.md` updated if any user-facing flag or timing behaviour changed.
5. `design.md` and `tasks.md` reflect what was actually built.

---

## Next phase

Plan approved and §6 settled → [`design.md`](design.md) (phase 2), then
`tasks.md` (phase 3), then execution (phase 4).
