# AI_LOG

## Tools used
- **Claude Web** (free tier) — initial planning, file-by-file reviews, explanations of unfamiliar code.
- **DeepSeek Web** — continuation after Claude's free-tier limit; same prompt style.

Both were used for exploration and review, not for producing final code without verification. Every AI-suggested change was either tested against the mock or cross-checked with a Python snippet before being kept.

## Prompts that mattered

**1. Project plan**
> "Need a brief plan before jumping on it, I have to maintain a log for chat also, like prompt so first breakdown the task in chunks assign goal subtask etc, and return it. check the readme file that it should follow"

Produced the six-chunk plan (setup, schema, client, sweep, API, docs) that structured the entire project.

**2. Schema and constants**
> "schema with unique (as_of,store_id,sku_id) + config for retry/backoff/rate limits"

Produced the initial `db.py` schema and `config.py` skeleton. Kept the schema as-is; extended and tuned the config by hand.

**3. Rate limiter deep dive**
> "explain the _rate_limit in more deep before going forward in depth with dry run"

Forced a proper understanding of the two-ceiling limiter. The AI's explanation was correct, but its initial parameter suggestion (`FAIR_USE_MAX_REQS = 25`) was too aggressive; I tuned it empirically.

## Chunk log

### Chunk 0 — Setup
Goal: environment, repo, screen recording, initial notes.
Outcome: used the chunk plan as-is.

### Chunk 1 — Schema + config
Goal: idempotent SQLite schema + shared constants.
Outcome: kept schema. Removed the AI's proposed `REASON_PRE_LAUNCH` constant
after probing BLR-007: a pre-launch store returning `items: []` with
`partial: false` and `meta.source: "origin"` is a *complete* observation
of an empty store, not incompleteness. Adding a reason for it would have
marked complete reads as incomplete in `coverage.incomplete[]`.

### Chunk 2 — Portal client
Goal: safe HTTP client with retry, rate limiting, soft-ban detection.
Outcome: kept the retry/backoff structure; replaced the AI's per-call sleep
with a shared module-level rate limiter (a sliding window is what actually
protects against the soft ban — per-call sleeps don't bound the sustained
rate). Split soft-ban detection into `_is_soft_banned` so it can be unit
tested in isolation.

### Chunk 3 — sweep.py
Goal: idempotent orchestrator with per-store completeness.
Outcome: kept the upsert strategy. Changed the tracking filter from the AI's
`is_active`-only suggestion to `is_active OR is_serviceable` after seeing the
mock's four flag combinations (inactive-but-serviceable and
active-but-non-serviceable both exist).

### Chunk 4 — app.py
Goal: `/osa` endpoint with IST-day bucketing, coverage, per-SKU breakdown.
Outcome: kept the IST-convert-at-read approach. Added the `no_data` branch
explicitly (the AI's initial sketch returned `osa_pct: 0`, which the README
forbids).

## Where the AI was wrong

### 1. Missed the infinite-pagination failure mode
When asked about pagination, the AI treated `next_page: null` as a guaranteed
terminator. In production, servers can return a never-ending page chain
(off-by-one in the "is there more?" check, cached responses, cursor cycles).
Noticed during a code review pass; added `MAX_STORE_PAGES` and
`MAX_INVENTORY_PAGES = 15` (5× the expected maximum of 3), with `fetch_stores`
raising and `fetch_inventory` returning incomplete on cap exceeded.

### 2. Miscounted the IST day for 2026-09-28T18:40:00Z
While reviewing `/osa` output, the AI claimed the sweep
`2026-09-28T18:40:00Z` belongs to IST 2026-09-28. It does not:
18:40 + 5:30 = 24:10, which rolls into IST 2026-09-29. This led the AI to
flag the correct `stores_expected: 27` for Delhi as suspicious, when the API
was in fact right.

Caught by running the conversion in Python and diffing against the AI's claim:

    python3 -c "
    import sqlite3
    from datetime import datetime
    from config import IST
    conn = sqlite3.connect('osa.db')
    for (as_of,) in conn.execute('SELECT as_of FROM sweeps ORDER BY as_of'):
        ist = datetime.fromisoformat(as_of.replace('Z','+00:00')).astimezone(IST)
        print(as_of, '->', ist.strftime('%Y-%m-%d'))
    "

Output:
    2026-09-27T04:30:00Z -> 2026-09-27
    2026-09-27T10:30:00Z -> 2026-09-27
    2026-09-27T19:00:00Z -> 2026-09-28
    2026-09-28T04:30:00Z -> 2026-09-28
    2026-09-28T10:30:00Z -> 2026-09-28
    2026-09-28T18:40:00Z -> 2026-09-29    ← not the 28th

Lesson: LLM mental arithmetic is not a source of truth. Boundary cases
(midnight crossings, month ends, DST) must be verified in code, not by
asking the model.

### 3. Missed the mock's 503 failure mode in its initial problem list
The AI's first explanation of the mock's failure modes covered the soft ban
and 429 burst limit but omitted the ~7% random 503. Discovered while testing:
a sweep logged repeated 503s and I had to ask the AI to explain. The client's
retry-and-backoff path handles it, but the AI's initial failure-mode list
was incomplete.


## How the AI was used

- **Exploration:** reading unfamiliar parts of `mock_portal.py`, explaining
  why the mock behaves the way it does.
- **Drafting:** initial versions of `db.py`, `portal_client.py`, and `app.py`.
  Every draft was then adjusted by hand.
- **Review:** walking through files as if reviewing someone else's code,
  catching things like the fetch_inventory docstring mismatch and the
  `datetime.utcnow()` naive timestamp.