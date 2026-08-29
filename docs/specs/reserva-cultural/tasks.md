# Tasks — add Cinema Reserva Cultural São Paulo as a source

**Spec:** `reserva-cultural` · **Phase:** 3 of 4 (Plan → Design → Tasks → Execution)
**Status:** approved — D1–D5 all resolved. No code written yet; ready to execute.
**Baseline:** `main` @ 236fa5f, branch `feat/reserva-cultural`

> Plan and design were folded into this document: the source is a single read-only
> HTTP endpoint returning JSON, and the project already has three scrapers
> establishing the shape. §1–§3 carry the decisions that would otherwise live in
> `plan.md` / `design.md`; §5 is the executable list.

---

## 1. Context

Reserva Cultural São Paulo (Av. Paulista 900, Bela Vista) sells through
**ingresso.com**, not Velox Tickets. Its own WordPress site
(`reservacultural.com.br/sao-paulo/`) renders posters but no session times — the
times come from ingresso.com's content API, which is also what the site's
`wp-plugin-reserva-cultural` proxies. We consume that API directly.

**Endpoint** (from the supplied curl, verified 2026-08-29):

```
https://api-content.ingresso.com/v0/sessions/city/1/theater/330
    /partnership/home/groupBy/sessionType?date=YYYY-MM-DD
```

`city=1` is São Paulo; `theater=330` is Reserva Cultural SP, confirmed against
`GET /v0/theaters/city/1` (`"id": "330"`, `"urlKey": "cinema-reserva-cultural-sao-paulo"`,
`"corporation": "Imovision"`).

### Findings that shape the work

Each was measured against the live API, not assumed.

| # | Finding | Consequence |
| --- | --- | --- |
| F1 | **A `User-Agent` header is mandatory.** `requests`' default UA gets **403 Forbidden**; any other UA — a browser string or even `curl/8.5.0` — gets 200. `Origin` alone still 403s. | The only header worth sending is `User-Agent`. The rest of the supplied curl (`Accept`, `Origin`, `DNT`, `Sec-GPC`, `Sec-Fetch-*`) is noise — verified identical 200 with and without. |
| F2 | `groupBy/sessionType` sets `rooms` to **`null`** and moves sessions to `sessionTypes[].sessions[]`. | Cannot copy Belas Artes' `rooms[0]...` access path. Each session carries its own `room` (`"Sala 3"`) and `time` (`"20:20"`). |
| F3 | A date with no programming returns **HTTP 204, empty body**. | `get_data` treats non-200 as failure and raises `RequestException("No Content")` before touching `.json()` — so the existing `except RequestException: return movies` already handles it. Correct outcome, but by accident; T4 makes it deliberate. |
| F4 | A malformed date returns **HTTP 400** with an RFC 9110 problem document. | Same path as F3 → empty list. No crash. |
| F5 | Omitting `date` returns **5 days** (`2026-08-29` … `2026-09-02`); passing it returns exactly 1. | Always pass `date`. Still index defensively — the response is a *list of days*. |
| F6 | Movies carry `duration` (`"172"`, minutes as a **string**), `originalTitle`, and `siteURLByTheater`; sessions carry a `siteURL` checkout link. | More data than any existing source provides. D4 declines `duration`; D3 keeps `siteURL` wired but disabled. |
| F7 | **`duration` cannot come from TMDB.** `/search/movie` — the only TMDB endpoint this project calls — returns no `runtime` field (verified: 15 keys, none of them `runtime`). Only `/movie/{id}` has it. | Runtime would cost a **second HTTP request per title**. Since only Reserva Cultural could supply it for free, D4 declines it outright. |
| F8 | On 2026-08-29 all 8 films play in exactly **one room each** (12 sessions total; 0 films span rooms). | Grouping "per venue" and "per venue+room" produce identical output today. The rule still has to be stated for the day a film moves rooms mid-day — D2 does. |

---

## 2. Requirements

### R1 — A new scraper module for Reserva Cultural

- **R1.1** `get_movies_reserva_cultural(date2search)` returns `List[Movie]`, matching
  the signature of `get_movies_ims` / `get_movies_belasartes`.
- **R1.2** It sends a `User-Agent` header (F1). Without one the source returns nothing
  and the failure is silent — an empty schedule is indistinguishable from a 403.
- **R1.3** A network error, a 204, or a 400 yields an empty list, never an exception
  escaping to `main` (F3, F4).
- **R1.4** A response whose shape does not match — no days, `movies` missing,
  `sessionTypes` empty — yields an empty list rather than an `IndexError`/`KeyError`.
- **R1.5** Sessions are **grouped**: one `Movie` per `(title, room)`, carrying *all*
  that room's showtimes for the date (D2). `As Cores Do Tempo` with sessions at 15:50,
  18:20 and 20:50 is **one** row reading `15:50, 18:20, 20:50`, not three rows.
- **R1.6** Showtimes are sorted ascending and joined with `", "`. Zero-padded `HH:MM`
  means the existing string sort at `main.py:80` still orders correctly on the first
  showtime.

### R2 — Wired into the run

- **R2.1** `main()` calls it alongside the other four sources.
- **R2.2** The dedupe key at `main.py:78` becomes **`(name.lower(), local)`** (D5).
  The current key is the lowercased name alone, which keeps one row per film per day
  and would silently drop a film showing at more than one venue.
- **R2.3** Results are cached in the same `movies:<date>` blob; no new key type.
- **R2.4** The existing time sort is unchanged.

### R3 — Output columns fit the grouped showtimes

- **R3.1** `Movie.__str__` formats `time` at `{:<8}` (`movies.py:45`), which fits one
  `HH:MM` and nothing more. It widens to hold a joined showtime list (R1.6).
- **R3.2** Rows from the other four sources — still a single time — stay aligned.
- **R3.3** `duration` stays `None` for every source, as it is today (D4). No column,
  no parse, no display.

### R4 — Documented

- **R4.1** `README.md` lists Reserva Cultural among the sources.
- **R4.2** The README records the D5 dedupe change — a film playing at two venues now
  prints twice. That is a visible change to every run, not just this venue's.

---

## 3. Decisions

All resolved 2026-08-29.

- **D1 — `local` is `"Reserva Cultural - Sala 3"`.** Venue plus room. Every existing
  source emits a bare room name, and Belas Artes also has a "Sala 3", so bare rooms
  collide in the merged list. This makes Reserva Cultural rows self-identifying.
- **D2 — One row per movie per venue, carrying all of that venue's showtimes.**
  *Diverges from the other four sources*, which keep only `rooms[0].schedules[0]` /
  `horarios[0]`. Grouping happens **in the scraper**, so a film with three showtimes
  is one `Movie` whose `time` reads `15:50, 18:20, 20:50` — not three `Movie`s.
  - **Grouping key: `(title, room)`.** F8 shows no film spans two rooms on the sampled
    date, so this is indistinguishable from grouping per venue today. Stated anyway:
    if a film ever plays Sala 2 and Sala 4 on one day it yields two rows, which is
    consistent with D1 putting the room in `local`.
  - Consequences, both real:
    1. It forces R2.2 — the dedupe key is shared with all four existing sources, so
       **this pulls `main.py:78` into scope**, which §4 of the `redis-tmdb-cache`
       spec had explicitly excluded. See D5.
    2. Output is asymmetric: Reserva Cultural shows all its showtimes, the other four
       still show one apiece. Bringing them to parity is per-scraper work, out of
       scope here (§4).
- **D3 — `ticket_url` is passed but commented out**, matching `velox_tickets.py:56`
  and `ims.py:56`. The line is written and disabled, so enabling tickets across all
  five sources later is a one-line change per source rather than new work.
- **D4 — `duration` is NOT populated. Reverted 2026-08-29; the field stays `None`
  everywhere, exactly as today.** The API offers it for free (F6), but F7 shows no
  other source can ever match: TMDB's search endpoint carries no runtime, so the other
  four could only be filled by a second HTTP request per title. That leaves a column
  populated for one venue in five — and it does not exist in the output at all today,
  so displaying it means new formatting work in `Movie.__str__` plus a decision about
  what four-fifths of the rows show. **Not worth the cost for a single venue.**
  `Movie` already declares the field and `to_json()` already serializes it, so nothing
  needs removing — we simply do not fill it.

- **D5 — Dedupe key becomes `(name.lower(), local)` — option A.** One row per film
  per venue; the same film at Belas Artes and at Reserva Cultural now shows twice,
  once per venue, instead of one of them being silently dropped.
  `time` is **not** in the key, because D2 already grouped showtimes inside the
  scraper — one row per `(film, venue)` is exactly what the key expresses.
  *This changes output for all four existing sources*, which is why T5 carries a
  warning and AC7 demands a before/after diff rather than a spot check. The old key
  meant "one row per film per day" and hid cross-venue repeats; that was the thing
  worth losing.

---

## 4. Out of scope

| Excluded | Why |
| --- | --- |
| Making the other four sources emit all their sessions | D2 creates the asymmetry knowingly. Each scraper needs its own change; the API shapes differ. Own spec. |
| Reserva Cultural **Niterói** (`reservacultural.com.br/niteroi/`) | Different city id; this project is São Paulo only. |
| Re-enabling `ticket_url` at any call site | D3 keeps all five consistent and disabled. Enabling them is one deliberate change. |
| A generic ingresso.com scraper covering all 48 SP theaters | The API supports it and it is tempting. Volume, dedupe, and TMDB cost all shift. Own spec. |
| `duration` — capturing it, displaying it, or backfilling it via TMDB `/movie/{id}` | D4: one venue in five can supply it for free; the rest would need a second HTTP request per title, doubling TMDB traffic. A column that is blank four times out of five is not worth the display work. |
| Moving the hardcoded `User-Agent` into shared config | One consumer today. Revisit at the second. |
| Per-`(source, date)` cache keys | Still open from `redis-tmdb-cache` §4. A fifth source in the same all-or-nothing blob makes that gap marginally worse. Noted, not fixed. |

---

## 5. Task list

Ordered, and the order matters in two places:

- **T1 before T5.** The dedupe change rewrites output for sources that already exist;
  without a baseline captured first, AC7 has nothing to diff against.
- **T5 before T7.** Changing the dedupe key *before* wiring in the new source isolates
  the two effects. T5's diff then shows only what the key change did to the existing
  four; T7's diff shows only what Reserva Cultural added. Wired in the other order,
  a regression in either one hides inside the other.

### T0 — Capture a fixture
Save a live response for `2026-08-29` (8 movies, 12 sessions, times 15:50–21:00) to
`tests/fixtures/reserva_cultural_sessions.json`. Do this **first** — programming
changes daily and later tasks need a stable comparison point.
*Done when:* file exists, parses, contains 8 movies.

### T1 — Capture the pre-change baseline
Run the full pipeline for a date with programming and save the output verbatim. T5
changes the dedupe key for **all** sources; without a baseline captured *before* that,
AC7 cannot be checked.
*Done when:* baseline output is saved and the date is noted here.

### T2 — Write `src/movies/services/reserva_cultural.py`
Module constants for the URL template, the `User-Agent`, and city/theater ids.
`get_movies_reserva_cultural(date2search)` mirrors `_get_movies_from_url`'s structure:
print the banner and URL, `get_data(url, header=...)`, `except RequestException: return []`.
Walk `response[0]["movies"][*]["sessionTypes"][*]["sessions"][*]` (F2), guarding each
level (R1.4). Group sessions by `(title, room)` (R1.5) and join their sorted times
with `", "` (R1.6). `local` per D1, `ticket_url` commented out per D3. `duration` is
left unset (D4).
*Done when:* returns **8** Movies for the fixture's date (12 sessions grouped), with
`As Cores Do Tempo` reading `15:50, 18:20, 20:50`.

### T3 — Verify against the live API
Run for today, a far-future date (expect 204 → `[]`), and a malformed date
(expect 400 → `[]`).
*Done when:* all three behave as F3/F4 predict, no traceback.

### T4 — Make the 204 path deliberate
F3 works only because `get_data` rejects every non-200. Add a comment at the
`except RequestException` naming 204-as-empty-schedule, so a later change to
`get_data` that starts accepting 2xx does not silently turn "no programming" into a
crash on `response.json()` of an empty body.
*Done when:* the comment states the 204 contract. **No behaviour change** — do not
edit `requests_service.py`; four other call sites depend on it.

### T5 — Change the dedupe key in `main.py` — ⚠ affects all sources
Change the key at `main.py:78` from `movie.name.lower()` to
`(movie.name.lower(), movie.local)` (D5). This is the riskiest task in the list: the
only one that changes what the four existing sources print.
*Done when:* diffing a full run against T1's baseline shows **only** newly-appearing
rows for films that play at more than one venue — no row lost, no row altered.

### T6 — Widen the `time` column
`Movie.__str__` formats `time` at `{:<8}` (`movies.py:45`), which cannot hold
`15:50, 18:20, 20:50` (R3.1). Widen it and confirm single-time rows from the other
four sources stay aligned (R3.2). No `duration` work — D4 declined it.
*Done when:* a multi-showtime row and a single-showtime row both align.

### T7 — Wire into `main.py`
Add the import and one `movies.extend(...)` after `get_movies_ims`.
*Done when:* `python main.py 2026-08-29 --force-refresh` shows Reserva Cultural titles.

### T8 — Check TMDB matching on real titles
The fixture includes `"Akira (Remasterizado Em 4k)"` and
`"La La Land - Cantando Estações (Relançamento)"`. Suffixes like `(Relançamento)` and
`(Remasterizado Em 4k)` are exactly the shape that defeats a title search — and a miss
is now cached for 5 days (`redis-tmdb-cache` D3), so a bad match persists.
*Done when:* each of the 8 titles is checked for a score, and any systematic failure is
either fixed in `Movie._sanitize_moviename` or written up here as accepted.
*Along with T5, this is where the real work is* — the rest is mechanical.

### T9 — Full-run regression
`--force-refresh` then a cache-hit run, same date. Confirm the two runs agree, all
five sources appear, and the T5 diff is exactly what D5 predicted.
*Done when:* both runs produce identical output and the diff is explained.

### T10 — README
Add Reserva Cultural to the source list (R4.1). Document the D5 dedupe change: a film
playing at two venues now prints twice (R4.2).
*Done when:* the list names all five and the output change is described.

### T11 — Commit
One commit on `feat/reserva-cultural`. Do not push; do not open a PR.
*Done when:* tree clean, branch unpushed.

---

## 6. Acceptance criteria

| # | Criterion |
| --- | --- |
| AC1 | For a date with programming, at least one Reserva Cultural movie appears in output. |
| AC2 | Titles and times match the ingresso.com listing for that date. |
| AC3 | A film with three showtimes produces **one** row listing all three (D2/R1.5). |
| AC4 | A date with no programming (204) produces an empty list and no traceback. |
| AC5 | A malformed date (400) produces an empty list and no traceback. |
| AC6 | With the `User-Agent` removed, the run still completes — degraded to zero Reserva Cultural results, not crashed. |
| AC7 | Diffed against T1's baseline, the other four sources gain rows only for films playing at more than one venue; none is lost or altered. |
| AC8 | A cache-hit run and a cache-miss run for the same date produce identical output. |
| AC9 | `local` distinguishes Reserva Cultural from a same-numbered room at another venue. |
| AC10 | Column alignment holds for both a multi-showtime row and a single-showtime row. |

---

## 7. Risks

| Risk | Mitigation |
| --- | --- |
| **T5 regresses the four existing sources** | The one genuinely dangerous change here. AC7 requires a before/after diff of a full run, not a spot check. Capture the baseline before touching `main.py`. |
| The UA check (F1) tightens into a real bot defence | R1.3/AC6: a 403 degrades to an empty list. The run survives; the venue silently disappears. Accepted — no scraper here is more robust than this. |
| D2 makes one venue's listing look richer | 8 Reserva Cultural rows carrying 12 showtimes, against one showtime per film elsewhere. If it reads badly, the fix is bringing the other four up to parity, not walking D2 back. |
| `theater=330` changes | Recoverable from `/v0/theaters/city/1` by `urlKey`. Left hardcoded; a lookup is more moving parts than the risk warrants. |
| `groupBy/sessionType` is dropped and `rooms` comes back | T0's fixture pins the shape we built against; R1.4's guards degrade to empty rather than crash. |
| A joined showtime list breaks column alignment | T6 checks it against single-time rows from the other four sources (AC10). |
| `Movie.to_dict()` mis-splits a joined showtime string | It splits `time` on a space to derive a date (`movies.py:34-35`), which a list like `15:50, 18:20` would confuse. **Dead code — no caller anywhere in the repo**, verified by grep. Left alone; noted so it is not mistaken for working. |
| A fifth source lengthens every cache-miss run | Bounded by the TMDB cache: repeat titles across venues are now free. |
| Undocumented API, no stability contract | Same posture as the other three sources. |

---

## 8. Definition of done

1. R1–R4 implemented.
2. AC1–AC10 demonstrated.
3. Nothing from §4 in the diff.
4. D1–D5 recorded in §3 with the values actually built.
5. This file updated to say what was built, including any deviation.

---

## 9. Execution record (2026-08-29)

T0–T11 executed as ordered. Built exactly as D1–D5 specify:
`src/movies/services/reserva_cultural.py` added; `local` is
`"Reserva Cultural - Sala N"` (D1); grouping key `(title, room)` (D2);
`ticket_url` wired but commented out (D3); `duration` left unset (D4);
`main.py`'s dedupe key changed to `(name.lower(), local)` (D5).

**One deviation, inside T8's stated latitude.** T8 says a systematic
TMDB miss is "either fixed in `Movie._sanitize_moviename` or written
up here as accepted." Both of the fixture's suffixed titles —
`Akira (Remasterizado Em 4k)` and
`La La Land - Cantando Estações (Relançamento)` — returned **zero**
TMDB search results verbatim (confirmed live), while the same query
minus the trailing parenthetical matched correctly. `_sanitize_moviename`
now strips a trailing `(...)` annotation for every title, not only
Reserva Cultural's:

```python
without_tag = re.sub(r'\s*\([^)]*\)\s*$', '', moviename).strip()
return without_tag or moviename
```

This also fixed a pre-existing miss on `Akira (relançamento)` /
`A Professora de Piano (Relançamento)` from the other sources (both
went from `N/A` to a resolved score) — an accepted side effect, not
new scope, since the fix lives in the one shared function T8 named.
Stale TMDB miss cache entries under the old (unstripped) key are
orphaned, not deleted — they are simply never looked up again and
expire on their existing 5-day TTL.

`A Odisseia` (no parenthetical suffix) still returns no usable score:
TMDB's top result for that exact string is an unrelated zero-vote
title. This is a generic Portuguese-title-search ambiguity, not a
suffix problem, and is accepted as out of scope per D4/§4's posture
on title-matching quality.

All other tasks (T0, T1, T3–T7, T9–T11) ran with no deviation from
what §5 describes.
