# NOTES

## Store tracking

Track a store in a sweep if `is_active OR is_serviceable` is true.

- `is_active=false AND is_serviceable=false` → decommissioned and cannot serve;
  exclude. (DEL-010, BLR-010)
- `is_active=false AND is_serviceable=true` → decommissioned but still accepting
  orders; include, because a customer can order from it right now. (MUM-009, BLR-004)
- `is_active=true AND is_serviceable=false` → active but temporarily unable to
  serve (maintenance, rain). Include — excluding it would bias OSA upward, since
  a non-serviceable store is likelier to be out of stock. (DEL-006)

Rationale: availability means "could a customer order this from a store that
exists operationally, right now." `is_active` is structural; `is_serviceable`
is real-time. The union captures both meanings. Pure `is_active` drops stores
still serving; pure `is_serviceable` drops active stores mid-maintenance.
Both bias the number in a specific direction; the union doesn't.

Consequence: the tracked set can differ sweep-to-sweep. Intentional —
availability is a per-sweep observation.

Per-city tracked stores: Mumbai 10, Delhi 9, Bengaluru 9 = 28 total.

## Idempotency

- `inventory` PK is `(as_of, store_id, sku_id)`; writes use `INSERT OR IGNORE`.
  Re-running a sweep doesn't duplicate rows (verified: 800 → 800).
- `stores`, `sweeps`, `sweep_store_status`, `sku_names` use `ON CONFLICT DO
  UPDATE`. `first_seen_as_of` and `sweeps.started_at` are deliberately excluded
  from the UPDATE clause so they persist across reruns.

## Soft-ban detection

`_is_soft_banned(body, page_items)` returns True only when the response has the
mock's ban signature.

| `meta.source` | items empty | `next_cursor` set | items < 15 | Verdict |
|---|---|---|---|---|
| `origin` | any | any | any | Not banned |
| `edge` | yes | any | any | Banned |
| `edge` | no | no | any | Not banned |
| `edge` | no | yes | yes | Banned |
| `edge` | no | yes | no | Not banned |

Two ban signals:
- Empty items from an `edge` source.
- Truncated first page (`next_cursor` set but page is short).

Conjunction, not a single signal, because `edge` alone could in principle be a
legitimate CDN response, and a short page alone could be a legitimate last page.
The mock's soft-ban response sets `"partial": false`, so partial-flag cannot be
used as the ban signal — `meta.source` is the only reliable tell.

**Known limitation:** the truncation check hardcodes `15`, matching the mock's
`INV_PAGE = 15`. Real APIs vary page size by endpoint, tier, or CDN layer. A
production client would read the page size from the API contract, derive it from
a known-healthy first page, or use a server-provided field. Documented, not
generalized here.

## Rate limiting and soft-ban handling

Two ceilings in `_rate_limit()`, whichever is tighter:

| Constant | Value | Enforces | Guards against |
|---|---|---|---|
| `GLOBAL_MIN_INTERVAL_S` | 0.15 | ~6.7 req/s instantaneous | 429 burst limit |
| `FAIR_USE_MAX_REQS` / `FAIR_USE_WINDOW_S` | 15 / 10s | 1.5 req/s sustained | soft ban (30 req / 10s) |

Why `FAIR_USE_MAX_REQS = 15` and not 30 (the server's documented limit): our cap
is not our rate. The server counts retries, MUM-007's two deterministic 500s, and
every request made while banned. Effective rate ≈ cap + 5–10. At cap 15 →
effective ~20–25, under 30. At cap 25 → effective ~33, over 30. Empirically
tuned: 25 → 2 bans over a 6-sweep run; 20 (with 15s cooldown) → 1 ban; 15 → 0
bans across three consecutive 6-sweep runs.

`fetch_inventory` response handling:
- Detects ban via `_is_soft_banned`; sleeps `SOFT_BAN_BACKOFF_S` (30s) and
  returns incomplete. Every request made while banned extends the ban by 5s
  server-side, so we stop making them.
- The sweep records `_last_soft_ban_at`; the next sweep sleeps
  `SOFT_BAN_COOLDOWN_S` (15s) before starting, so back-to-back sweeps don't
  compound the ban.

## IST bucketing

Sweeps are stored keyed by UTC `as_of`. The API's `date` parameter means the IST
calendar day. `sweeps_for_ist_day()` converts each stored `as_of` to IST via
`astimezone(ZoneInfo("Asia/Kolkata"))` and returns the ones whose IST date
matches. OSA aggregates over those sweeps.

The six canonical sweeps map to IST days:

- 2026-09-27T04:30:00Z → IST 2026-09-27 10:00
- 2026-09-27T10:30:00Z → IST 2026-09-27 16:00
- 2026-09-27T19:00:00Z → IST 2026-09-28 00:30 ✓ (crosses midnight)
- 2026-09-28T04:30:00Z → IST 2026-09-28 10:00 ✓
- 2026-09-28T10:30:00Z → IST 2026-09-28 16:00 ✓
- 2026-09-28T18:40:00Z → IST 2026-09-29 00:10 (crosses midnight)

So IST 2026-09-27 has 2 sweeps, IST 2026-09-28 has 3, IST 2026-09-29 has 1.

Why not store the IST date: one source of truth. UTC `as_of` is canonical; IST is
a view computed at read time. No drift, no backfill.

Coverage consequence on IST 2026-09-28: Mumbai 10 × 3 = 30 expected; Delhi 9 × 3
= 27 expected, 26 complete (DEL-004 partial at 10:30Z); Bengaluru 9 × 3 = 27
expected.

## OSA aggregation

`osa_pct = sum(in_stock) / count(observations) × 100`, across all inventory rows
for the city's stores on that IST day.

- Uses the server's `in_stock` field, **not `qty > 0`**. The mock has "ghost"
  rows where `in_stock=true` and `qty=0`; using `qty` would understate OSA.
- The city-level number is the aggregate, not a mean of per-SKU percentages. The
  README specifies total in-stock ÷ total seen, which weights each SKU by how
  often it was observed. A mean of per-SKU percentages would overweight rarely
  stocked SKUs.
- `no_data` is returned (not `osa_pct: 0`) when the IST day has no sweeps or no
  observations.

## Problems from the mock, and how each is handled

**Random 503s (~7%):** retried with exponential backoff (0.5, 1, 2, 4s) +
jitter, max 4 retries. With p=0.07 per attempt, the chance of 5 consecutive
failures is ~1.7×10⁻⁶.

**Random 500s (deterministic for MUM-007):** MUM-007 returns 500 twice per
`(store, as_of)` before succeeding. Absorbed by the same retry logic.

**Slow responses (~3%, 8s sleep):** `REQUEST_TIMEOUT_S = 8.0`. A timeout is
treated as transient and retried; the retry almost always hits a fast path.

**429 burst limit (8 req/s):** reproduced with 20 parallel unthrottled requests
to `/v1/stores` — first ~6 succeed, the rest return 429 with `Retry-After: 2`.
Prevented in normal operation by `_rate_limit()`; when it fires,
`_get_with_retries` honors `Retry-After`.

**Soft ban (30 req / 10s):** see above.

**Mixed timestamp formats:** DEL stores return IST ISO; others return UTC `Z`.
Stored raw; interpretation is the reader's job.

**Mixed price types:** BLR returns strings (`"237.50"`), other cities return
floats (`237.5`). Stored as TEXT; parsed on read.

**Pre-launch empty (BLR-007 before 2026-09-27T12:00:00Z):** returns `items: []`,
`partial: false`, `meta.source: "origin"`. This is a **complete** observation of
a store carrying nothing — not incompleteness. No `REASON_PRE_LAUNCH` constant
exists for this reason.

**Duplicate rows on pagination:** the mock repeats the previous page's last item
~35% of the time when `cursor > 0`. Deduped by `sku_id` per `(store, as_of)`.

**Partial flag (DEL-004 @ 2026-09-28T10:30:00Z):** `partial: true`. Recorded as
incomplete; items discarded; surfaced in `coverage.incomplete[]`.

**SKU-0001 renamed at 2026-09-28T00:00:00Z:** `inventory.name` preserves the
name at observation time; `sku_names` holds the latest. `app.py` reads from
`sku_names` for display.

**Store flag combinations (see Store tracking):** union rule handles
inactive-but-serviceable and active-but-non-serviceable consistently.

## Pagination safety

`fetch_stores` and `fetch_inventory` cap iterations at `MAX_*_PAGES` (both 15).
Against this mock the cap never fires: 3 pages for the roster, ~3 per store for
inventory. The cap exists to fail fast if a server ever returns a never-ending
`next_page`/`next_cursor` chain.

Set to 15 = 5× the expected maximum of 3. A production client would derive the
cap from the API's documented maximum, or from observed metrics.

Failure mode is deliberately asymmetric:
- `fetch_stores` raises `PortalError` (roster failure is fatal — nothing to sweep).
- `fetch_inventory` returns `complete=False` (per-store failure is isolated; the
  sweep continues with other stores).

## Reflection

**1. A brand says: "Your dashboard shows our Delhi availability fell from 92% to
41% yesterday." What do I check first, before replying?**

Coverage first. Was a store soft-banned, partial-flagged, or unreadable?
`coverage.incomplete[]` names the specific store/sweep/reason, and comparing
today's `observations` count to yesterday's tells me whether the number is
computed over less data than usual. Then the store roster — did stores open,
close, or flip `is_serviceable`? A temporary non-serviceable store is likelier
to have empty shelves; if the tracked set changed, the denominator changed.
Then the per-SKU breakdown — is the fall concentrated in a few SKUs (a supply
issue for the brand) or broad (a systemic issue at QuickMart's end)? Only after
ruling those out would I confirm the drop to the brand.

**2. The app's own dashboard says a city sold ₹4.20 lakh yesterday, but adding up
its store-level numbers gives ₹4.61 lakh. Which number would I show the brand,
and why?**

The dashboard number. It's the system of record with consistent filters
(cancellations, refunds, GST, attribution rules). The store-level sum is a
diagnostic; when two views of the same quantity disagree, the raw aggregation
is more likely wrong — commonly from double-counting (an order attributed to
two stores) or missing joins (orders that don't match a store row). I'd reply
with the dashboard number and separately file the discrepancy as a data-quality
ticket: a 10% gap between two views of "sales" is a bug that needs fixing even
if the brand never asks.

**3. Where in this project would I not use an AI/LLM, and why?**

Three places:
- **Deciding the store-tracking rule.** That's a policy decision about what
  "availability" means to a customer. It needs to be owned by someone
  accountable for the metric, not by a model that will produce a plausible
  answer without knowing the business.
- **IST-day bucketing.** Fixed arithmetic (UTC + 5:30, with midnight crossings).
  Models are unreliable at boundary arithmetic — this project had a concrete
  instance where the AI miscounted which sweeps belonged to IST 2026-09-28. It
  should be code + tests, never a prompt.
- **Any number a brand sees.** The `/osa` response is a data contract. Every
  value must be traceable to a row in the database. An LLM that hallucinates an
  extra digit, a plausible SKU, or a slightly-off percentage corrupts the
  product.

The pattern: use LLMs for exploration, drafting, and review. Do not use them for
decisions that need owners or computations that need to be reproducible.

## Bonus: 20,000 stores every 30 min

- **Parallelism.** A single-threaded sweep with the rate limiter is ~0.6s per
  store. 20k stores = ~3.3 hours. Production would use multiple workers, each
  with its own API key or budget, splitting the store list. The rate limiter
  moves from per-process to per-key.
- **Storage.** SQLite can't handle 20k × ~30 SKUs × 48 sweeps/day ≈ 29M rows/day.
  Move to Postgres or a columnar store (DuckDB, ClickHouse); partition
  `inventory` by date.
- **Coverage becomes a live metric.** At 20k stores, some store always fails.
  Coverage stops being a list of failures and becomes a time series with
  alerting thresholds ("miss rate > 5% for 3 consecutive sweeps").
- **Idempotency at scale.** 48 sweeps/day means crash-recovery reruns must be
  cheap. Partial-page commits (write each store's rows as they arrive) become
  necessary — the current design commits per-store, which is fine at 28 stores
  but expensive at 20k.
- **Query performance.** `/osa` at 29M rows can't scan on demand. Index
  `(city, as_of)` or materialize a daily rollup table; the API reads from the
  rollup.
- **Scheduling.** Six sweeps per day becomes 48. A scheduler (cron, Airflow)
  triggers each sweep and retries failures with backoff.