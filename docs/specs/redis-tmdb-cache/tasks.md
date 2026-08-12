# Tasks — TMDB score cache, longer TTL, link persistence

**Spec:** `redis-tmdb-cache` · **Phase:** 3 of 4 (Plan → Design → **Tasks** → Execution)
**Status:** executed — all tasks complete, all acceptance criteria pass. See §Outcome.
**Implements:** [`plan.md`](plan.md) · [`design.md`](design.md)
**Baseline:** `main` @ 8c1ae5c → delivered as `06e8ad1` on `feat/tmdb-cache`

Nine tasks, ordered by dependency. Each leaves the CLI working. `redis-cli` is not
installed on the host, so all Redis commands go through
`docker compose exec redis redis-cli …` (container `cine-scrapper-redis-1`, running).

## Execution decisions (agreed 2026-08-12)

Binding for whoever executes this — including a fresh session or a different model.

- **E1 — One commit for the entire change.** Not one per task. Tasks are units of work
  and review, not units of history. Stage everything, including the spec docs (T8),
  and commit once at the end.
- **E2 — Running against the live Redis is authorised.** The instance at
  `127.0.0.1:6379` (container `cine-scrapper-redis-1`) may be written to, and may be
  cleared if needed: `docker compose exec redis redis-cli FLUSHALL`. **T0 must be done
  before any flush** — it captures the only old-format data that exists.
- **E3 — Do not commit until T6 passes.** All eight acceptance criteria green first.

## Environment notes

- Python is `./venv/bin/python` (3.14.6). Poetry manages `pyproject.toml`; no new
  dependency is needed — `redis` is already a dependency and `sqlite3`/`typing` are stdlib.
- No test suite, no linter installed, no lint config. The code nonetheless follows
  79-column flake8 style with explicit `# noqa: E501` on the four lines that exceed it.
  Match that: keep new lines ≤79 chars or add the pragma.
- Existing naming is `camelCase` on `RedisCache` methods and `snake_case` everywhere
  else. Preserve it; renaming is out of scope (plan §4).
- Running `main.py` hits four live venue sites plus TMDB, and needs `read_token` in
  `.env` for TMDB. Expect real network latency on a cache miss.

| # | Task | Files | Reqs | Blocks |
| --- | --- | --- | --- | --- |
| T0 | Capture an old-format blob | `tests/fixtures/` | R3.4 | T3 verification |
| T1 | Atomic write, working delete, honest types | `src/redis.py` | R4.1–4.3 | T5 |
| T2 | `to_json()` emits `duration` | `src/movies/movies.py` | R3.2 | T3 |
| T3 | TTL constant + lossless rehydration | `main.py` | R2, R3.1/3.3/3.4 | — |
| T4 | TMDB cache helpers (additive) | `src/tmdb/tmdb_service.py` | R1.1/1.3/1.6 | T5 |
| T5 | Wire the cache into `get_tmdb_details` | `src/tmdb/tmdb_service.py` | R1.2/1.4/1.5 | T6 |
| T6 | Acceptance pass | — | all ACs | T7 |
| T7 | README correction | `README.md` | DoD 4 | — |
| T8 | Commit the spec | `docs/` | — | — |

**T0 first, and soon** — it depends on two live keys that expire on the old 12 h TTL.

---

## T0 — Capture an old-format blob

**Why first:** AC6 proves old blobs still load. The only genuine old-format data in
existence is `movies:2026-08-11` and `movies:2026-08-13`, both written by current code
under the old 12 h TTL. Once they expire the case becomes untestable without hand-forging
a fixture.

**Steps**

1. `mkdir -p tests/fixtures`
2. Dump whichever key still exists:
   ```bash
   docker compose exec redis redis-cli --raw HGET movies:2026-08-13 movies \
     > tests/fixtures/movies_old_format.json
   ```
   **`--raw`, not `--no-raw`.** `--no-raw` emits redis-cli's shell-escaped display form
   — backslash-escaped UTF-8 — which is not valid JSON and fails step 3. `--raw` writes
   the actual bytes. *(Corrected after execution; the original text specified `--no-raw`
   and did not work.)*

   If both are gone, forge one by checking out `8c1ae5c`, running it once, and dumping
   the result — then note in the fixture that it is reconstructed.
3. Confirm it parses and that `duration` is absent:
   ```bash
   ./venv/bin/python -c "
   import json; d=json.load(open('tests/fixtures/movies_old_format.json'))
   print(len(d), 'records; keys:', sorted(d[0]))
   assert 'duration' not in d[0], 'not old format'"
   ```

**Done when** the fixture exists, parses, and has no `duration` key.
**Rollback** — delete the file.

---

## T1 — `src/redis.py`: atomic write, working delete, honest types

**Implements** R4.1, R4.2, R4.3 · **Design** §4

**Steps**

1. `setHash` — queue `hset` + `expire` in a pipeline, one round trip. Narrow the
   `hash: str | dict` annotation to `dict`; the `str` arm was never valid for
   `hset(mapping=…)`. Return `None`.
2. `deleteHash` — `self.client.delete(key)`, replacing the wrong-arity `hdel(key)`.
3. `getHash` — annotate `Dict[bytes, bytes]`, matching what `hgetall` returns. Drop the
   now-unused `Optional` import if nothing else needs it.

**Verify**

```bash
./venv/bin/python -c "
from src.redis import RedisCache
c = RedisCache()
c.setHash('spec:t1', {'a': '1'}, expire=60)
print('ttl :', c.client.ttl('spec:t1'))        # 0 < ttl <= 60
print('read:', c.getHash('spec:t1'))           # {b'a': b'1'}
c.deleteHash('spec:t1')                         # must not raise
print('gone:', c.getHash('spec:t1') == {})     # True"
```

**Done when** the TTL is set, the read round-trips, and `deleteHash` removes the key
without raising. **Rollback** — revert the file; nothing else depends on it yet.

---

## T2 — `src/movies/movies.py`: `to_json()` emits `duration`

**Implements** R3.2 · **Design** §5

Establishes the invariant T3 relies on: *every key `to_json()` emits is a parameter of
`Movie.__init__`*.

**Steps** — add `'duration': self.duration,` to the `to_json()` dict. One line.

**Verify** — mechanical, not by eye:

```bash
./venv/bin/python -c "
import inspect
from src.movies.movies import Movie
m = Movie.__new__(Movie)
for f in ('name','local','time','duration','tmdb_score','tmdb_url','ticket_url'):
    setattr(m, f, None)
params = set(inspect.signature(Movie.__init__).parameters) - {'self'}
keys = set(m.to_json())
assert keys <= params, f'not constructible: {keys - params}'
assert 'duration' in keys
print('invariant holds; to_json keys:', sorted(keys))"
```

**Done when** the assertion passes. **Rollback** — revert; T3 is unaffected because the
pre-existing `to_json()` keys were already all valid parameter names.

---

## T3 — `main.py`: TTL constant and lossless rehydration

**Implements** R2.1, R2.2, R3.1, R3.3, R3.4 · **Design** §6

**Steps**

1. Add `MOVIES_TTL = 18 * 3600` beside `LIMIT_HOUR` / `MIN_SCORE`; replace the inline
   `expire=43200,  # 12 hours` with `expire=MOVIES_TTL`.
2. Replace the rehydration block (`main.py:70-84`) with
   `movies = [Movie(**movie, cached=True) for movie in movies_data]`.
3. Drop the now-unused `Dict` and `cast` imports; keep `Optional`.

**Verify**

- **AC4** — after a run: `docker compose exec redis redis-cli TTL movies:<date>` is
  `> 0` and `<= 64800`.
- **AC6** — the T0 fixture loads and `duration` defaults to `None`:
  ```bash
  ./venv/bin/python -c "
  import json
  from src.movies.movies import Movie
  rows = json.load(open('tests/fixtures/movies_old_format.json'))
  ms = [Movie(**r, cached=True) for r in rows]
  print(len(ms), 'loaded; duration:', ms[0].duration)"
  ```
  `cached=True` matters — it suppresses the constructor's TMDB call, so this makes no
  network requests.
- **AC2/AC3** — deferred to T6; they need T5's cache to be meaningful.

**Done when** AC4 and AC6 pass.
**Rollback** — revert. Note the change is rollback-safe in both directions: new blobs
carry `duration`, which old code reads via its explicit `movie.get('duration')`.

---

## T4 — `src/tmdb/tmdb_service.py`: cache helpers (additive)

**Implements** R1.1, R1.3, R1.6 · **Design** §2.1, §2.2, §3.2 · **Decisions** D2, D5

Pure addition — nothing calls these yet, so this task cannot change behaviour.

**Steps**

1. Imports: `from redis.exceptions import RedisError` and `from src.redis import RedisCache`.
   *Verified non-conflicting:* `src.redis` and the pip `redis` package resolve to
   different modules, so `src/redis.py` does not shadow the library.
2. Constants `TMDB_TTL = 30 * 24 * 3600` and `TMDB_MISS_TTL = 5 * 24 * 3600`.
3. Module-level `_cache = RedisCache()`. Lazy — no socket at import.
4. `_cache_key`, `_cache_read`, `_cache_write` per design §3.2. Both hash fields are
   always written, with `""` for absent: redis-py raises `DataError` on a `None` value
   and on an empty mapping.
5. TTL choice keys on the **score**, not the URL, so a matched-but-unrated title takes
   the shorter window while keeping its URL.

**Verify**

```bash
./venv/bin/python -c "
import src.tmdb.tmdb_service as t
print(t._cache_key('  A   Origem Do Mal '))      # tmdb:a origem do mal
for score, url in ((7.1,'http://x'), (None,'http://y'), (None,None)):
    t._cache_write('spec:t4', score, url)
    print(f'{score!s:5} {url!s:10} -> {t._cache_read(\"spec:t4\")}'
          f'  ttl={t._cache.client.ttl(\"spec:t4\")}')
t._cache.deleteHash('spec:t4')
print('miss ->', t._cache_read('spec:t4'))       # None"
```

Expect the three states to round-trip as `(7.1,'http://x')`, `(None,'http://y')`,
`(None,None)`, with TTL `2592000` on the first and `432000` on the other two.

**Done when** all three states round-trip, an absent key reads as `None`, and the two
TTLs are correct. **Rollback** — revert; no caller exists.

---

## T5 — Wire the cache into `get_tmdb_details`

**Implements** R1.2, R1.4, R1.5 · **Design** §3.1, §3.3 · This is the behaviour change.

**Steps**

1. Rename the existing `get_tmdb_details` body to `_fetch_tmdb_details`, **verbatim**,
   including the `-` recursion at lines 30-32. Its self-call must also be renamed.
2. Add the new cache-aware `get_tmdb_details(movie_name)` with the same signature:
   read → hit returns; miss fetches, writes, returns.
3. Leave `get_tmdb_score` (lines 37-38) alone — it delegates, so it is cached for free.
4. Keep the existing `print` on a live fetch and add a distinguishable one for a hit;
   T6's AC1 and AC5 are checked by counting those lines.

**Verify**

- Signature unchanged and no call site edited:
  ```bash
  grep -rn --include='*.py' "get_tmdb_details\|get_tmdb_score" src main.py
  ```
  Only `movies.py:25` and the two definitions in `tmdb_service.py` should appear.
- **AC8** — with the entry deleted, one live request happens and the entry is rewritten.

**Done when** a repeated lookup of the same title issues one request total.
**Rollback** — revert both functions together; T4's helpers can stay, unused.

---

## T6 — Acceptance pass

Runs the whole of plan §5 against the assembled change. Use a date with real sessions.

| AC | Check |
| --- | --- |
| AC1 | `python main.py <date> --force-refresh` twice → second prints **zero** `Fetching TMDB score for` lines |
| AC2 | Save both runs' stdout after the `****` separator → `diff` is empty |
| AC3 | Covered by AC2 — a dropped `TMDB:` link makes the diff non-empty |
| AC4 | `TTL movies:<date>` → `0 < ttl <= 64800` |
| AC5 | Nonsense title cached as unresolved → second run issues no request |
| AC6 | T0 fixture loads (already shown in T3) |
| AC7 | `TTL tmdb:<title>` unchanged across a `--force-refresh` |
| AC8 | `DEL tmdb:<title>`, rerun → one request, entry rewritten |

AC2 concretely:

```bash
python main.py 2026-08-13 --force-refresh | sed -n '/^\*\{20\}/,$p' > /tmp/miss.txt
python main.py 2026-08-13                 | sed -n '/^\*\{20\}/,$p' > /tmp/hit.txt
diff /tmp/miss.txt /tmp/hit.txt && echo "AC2/AC3 PASS"
```

**Done when** all eight pass. Any failure sends the specific task back, not the spec.

---

## T7 — README correction

**Implements** DoD 4

The README is **already wrong** before this change: it claims a 6-hour cache in two
places while the code has used 43200 s (12 h) since before this spec. Fix both to 18 h
rather than leaving a third stale value.

**Steps**

1. Features list: "Caches results in Redis for 6 hours" → 18 hours.
2. Cache Management: "expire after 6 hours (21600 seconds)" → 18 hours (64800 seconds).
3. Add TMDB caching: scores and links cached per title, 30 days resolved / 5 days
   unresolved.
4. Document `--force-refresh`, currently undocumented, with its D4 semantics — it
   re-scrapes venues but **keeps** cached TMDB scores. Note `DEL tmdb:<title>` as the
   way to force one score.

**Done when** no "6 hours" remains: `grep -n "6 hours\|21600" README.md` is empty.

---

## T8 — Commit

Per **E1**, this is the *only* commit. `docs/` is currently untracked; include it so the
spec is versioned alongside the code it describes.

**Steps**

1. Confirm T6 is green (E3). Do not commit otherwise.
2. Branch first — `main` is the default branch:
   `git checkout -b feat/tmdb-cache`
3. Stage code + `docs/redis-vs-mongodb.md` + `docs/specs/redis-tmdb-cache/*` +
   `tests/fixtures/movies_old_format.json`.
4. Do **not** stage `.idea/`, `venv/`, `__pycache__/`, or `.env`. Check `git status`
   before committing — `.gitignore` coverage is unverified for `docs/` and `tests/`.
5. Commit message: what changed and why, referencing the spec.

```
feat: cache TMDB lookups in Redis, extend list TTL to 18h

Adds a tmdb:<title> namespace so a score and its URL are fetched at
most once per title (30d resolved, 5d unresolved) instead of once per
title per date-blob expiry. Extends movies:<date> from 12h to 18h.

Fixes cache hits silently dropping tmdb_url and ticket_url: to_json()
now emits duration, so every serialized key is a Movie.__init__
parameter and rehydration is lossless.

Also in src/redis.py: setHash writes value+expiry in one pipeline,
deleteHash uses DELETE rather than a wrong-arity HDEL, and getHash is
annotated with what it actually returns.

Spec: docs/specs/redis-tmdb-cache/
```

---

## Execution order

```
T0 ─┐
T1 ─┼─→ T4 ─→ T5 ─┐
T2 ─→ T3 ────────┴─→ T6 ─→ T7 ─→ T8
```

T1, T2 and T4 are independent and can land in any order. T3 needs T2's invariant; T5
needs T4's helpers and T1's atomic write (otherwise a `tmdb:` key can be written with no
expiry). T6 needs everything. One commit at T8 per E1.

---

## Handoff checklist

For a fresh session or a different model picking this up cold:

1. Read [`plan.md`](plan.md) §3 (requirements), §4 (out of scope), §5 (acceptance),
   §6 (decisions D1–D6).
2. Read [`design.md`](design.md) — §2 key formats, §3 the TMDB module, §6 `main.py`.
3. Read the execution decisions and environment notes at the top of this file.
4. Work T0 → T8 in order. Verify each before moving on; the verify blocks are runnable
   as written.
5. Stop and ask if a verification fails twice for the same reason, or if a change
   requires touching a file outside the five named in design §1.

**Do not re-litigate the design.** D1 (module-level client) and D4 (`--force-refresh`
keeps scores) were chosen deliberately over alternatives that are documented in
`plan.md` §6. If something looks wrong, flag it rather than silently substituting a
different approach.

---

## Outcome (2026-08-12)

Executed T0–T8. Delivered as a single commit `06e8ad1` on `feat/tmdb-cache`, branched
from `main` @ `8c1ae5c`. Not pushed, not merged.

**Acceptance criteria — 8/8 pass.** AC1 (zero TMDB requests on a second
`--force-refresh`), AC2/AC3 (empty diff between cache-miss and cache-hit output),
AC4 (`TTL movies:2026-08-13` = 64660), AC5 (unresolved title not re-requested,
TTL 431998), AC6 (25-record old-format fixture loads, `duration` is `None`),
AC7 (`tmdb:` TTL decayed rather than reset across a forced refresh), AC8 (deleted
entry re-fetched once and rewritten at 2592000).

**Files changed:** the five in design §1 plus `tests/fixtures/movies_old_format.json`.
Nothing from plan §4 was touched.

### Corrections found in review

1. **T0's `--no-raw` was wrong** and is corrected above. It emits redis-cli's
   shell-escaped display form, which is not valid JSON.
2. **design.md §4 misdescribed redis-py pipelines** as not `MULTI`-wrapped by default.
   They are — `pipeline()` defaults to `transaction=True`. The code was already correct;
   only the prose was wrong. R4.1 therefore achieved real transactional atomicity, which
   is stronger than the requirement asked for.

### Verified independently of the executing agent

The three-state encoding from design §2.2 was re-tested with the network stubbed, since
the live acceptance run could not reliably exercise the middle state:

| Fetch result | Cached read-back | TTL | Live fetches |
| --- | --- | --- | --- |
| `(7.1, url)` resolved | `(7.1, url)` | 2592000 | 1 |
| `(None, url)` matched but unrated | `(None, url)` | 432000 | 1 |
| `(None, None)` no match | `(None, None)` | 432000 | 1 |

**Caveat on AC2:** it diffs two *live* scrapes of the same date. It passed, but a venue
updating its schedule between the two runs would have failed it for a legitimate reason.
Treat it as one good observation, not a proof of losslessness.

### Known-open, deliberately deferred

Per plan §4 — a failed source is still cached as an empty schedule for the full 18 h,
and that window is now 50% longer than before this change. This is the strongest
candidate for the next spec.
