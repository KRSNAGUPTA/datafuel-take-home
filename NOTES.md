# NOTES

## Decisions
- Stores I track and why: <draft — e.g. track if is_active; decide how to treat is_serviceable flips and new stores>
- Soft-ban detection: <draft — meta.source == "edge" AND (empty/truncated)>
- Backoff / rate limits: <draft — stay under 8 req/s, respect Retry-After, global limiter>
- IST bucketing: <draft — sweep → IST day via UTC+5:30>
- Idempotency: <draft — unique (as_of, store_id, sku_id), INSERT OR IGNORE>

### Store tracking
Track a store in a sweep if `is_active == true` in that sweep's store list.
`is_active=false` means the store is decommissioned — it should not count
toward availability. `is_serviceable` reflects real-time order acceptance and
flips intra-day (rain, maintenance, staffing); excluding non-serviceable
stores would bias OSA upward because a store can be non-serviceable *because*
it's out of stock. We record both flags per sweep but only `is_active` gates
tracking.

Consequence: a store can be tracked in one sweep and not in another. That's
intentional — availability is a per-sweep observation.

## Problems from Step 2 and how I handle them
<leave placeholder, fill in Chunk 2/3>

## Reflection
1. Delhi OSA fell 92% → 41%. What do I check first?
2. Dashboard says ₹4.20L, store-level sums to ₹4.61L. Which do I show?
3. Where I would NOT use an LLM in this project.

## Bonus: 20,000 stores every 30 min
<placeholder>





Error faced: 
1. upstream error
{{base_url}}/v1/stores?page=2
{"error": "upstream unavailable, try again"}

503


Price can be string
observed_at: string



DB State:

// Each Store

store_id TEXT PRIMARY KEY
city TEXT NOT NULL
name TEXT
is_active INTEGER NOT NULL
is_serviceable INTEGER
first_seen_as_of TEXT
last_seen_as_of TEXT


sweeps

// one row per sweep

as_of TEXT PRIMARY KEY          -- ISO UTC, the --as-of argument
started_at TEXT
finished_at TEXT
tracked_stores INTEGER
complete_stores INTEGER

sweep_store_status //per-store completeness.

as_of TEXT NOT NULL
store_id TEXT NOT NULL
complete INTEGER NOT NULL       -- 0/1
reason TEXT                     -- NULL when complete
items_seen INTEGER
PRIMARY KEY (as_of, store_id)


inventory
as_of TEXT NOT NULL
store_id TEXT NOT NULL
sku_id TEXT NOT NULL
name TEXT
in_stock INTEGER NOT NULL       -- from server's in_stock
qty INTEGER
price TEXT                      -- TEXT because BLR returns strings, others floats
observed_at TEXT NOT NULL       -- raw string; parse on read
PRIMARY KEY (as_of, store_id, sku_id)


sku_names:
sku_id TEXT PRIMARY KEY
name TEXT


Indices
CREATE INDEX idx_inv_store_asof ON inventory (store_id, as_of);
CREATE INDEX idx_inv_sku        ON inventory (sku_id);





PK: (as_of, store_id, sku_id)
Price: Normally int but can be string -> BLR

Pre Launch Empty: BLR-007 before 2026-09-27T12:00:00Z returns []



## Problems from Step 2

```
python3 -c "
import concurrent.futures as cf, requests
H = {'X-Api-Key': 'dfhire-2026'}
def hit(i):
    try:
        r = requests.get('http://127.0.0.1:8765/v1/stores',
                         params={'page': 1}, headers=H, timeout=10)
        return i, r.status_code, r.headers.get('Retry-After')
    except Exception as e:
        return i, type(e).__name__, None
with cf.ThreadPoolExecutor(max_workers=20) as ex:
    for row in ex.map(hit, range(20)):
        print(row)
"

```
429 burst limit (8 req/s): reproduced by 20 parallel unthrottled requests to /v1/stores — first ~6 succeeded, the rest returned 429 with Retry-After: 2. Our client's _rate_limit() prevents this in normal operation; when a 429 does occur, _get_with_retries honors Retry-After rather than using its own backoff.





total 4 stores are is_active: false but servicable!
total 3 stores are is_servicable: false

### Decommissioned-but-serviceable stores (MUM-009, BLR-004)
`is_active=false` means the store is decommissioned from QuickMart's roster.
`is_serviceable=true` means the store is still accepting orders right now.

These two flags contradict in principle. My rule: if the partner API says a
store is serviceable, a customer can order from it, and it belongs in OSA.
OSA is a customer-facing metric, not a policy metric. I do not override the
API's own claim because doing so would be a silent data-quality decision
dressed up as filtering.

Decision: include the store. (Optional: surface the anomalous flag
combination in coverage.anomalies[] so the partner team can investigate.)

The moment a scraper starts editing what it collects, the metric stops being
"what the partner said" and becomes "what I decided to believe."


### Soft ban — observed and handled
Ran all 6 sweeps back-to-back on 3 occasions. First run: 2 bans.
After lowering FAIR_USE_MAX_REQS (25 → 20) and adding a 15s inter-sweep
cooldown: 1 ban. After lowering to 15: 0 bans.

The remaining ban in the middle run was caused by MUM-007, which the mock
serves as two deterministic 500s before returning real data — 3 requests
against the inventory window for one store. Combined with normal retry
traffic, that pushed a sweep over the mock's 30-per-10s threshold.

Detection signal: HTTP 200 with meta.source == "edge" and truncated or
empty items. Response: mark the store incomplete (reason=soft_ban),
discard its items (never save a partial slice), back off, continue.

Items from banned responses are never written to inventory — the sweep is
honest about what it could and couldn't read.

grep FAIR_USE_MAX_REQS config.py
python3 sweep.py --as-of 2026-09-27T19:00:00Z


45 -> 2 DEl-007 & BLR-001 total time: 78s
44 -> 1 DEL-008 total time: 59s
43 -> No softban total time: 27s
40 -> No softban total time: 52s
