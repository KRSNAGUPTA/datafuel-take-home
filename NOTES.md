# NOTES

## Decisions
- Stores I track and why: <draft — e.g. track if is_active; decide how to treat is_serviceable flips and new stores>
- Soft-ban detection: <draft — meta.source == "edge" AND (empty/truncated)>
- Backoff / rate limits: <draft — stay under 8 req/s, respect Retry-After, global limiter>
- IST bucketing: <draft — sweep → IST day via UTC+5:30>
- Idempotency: <draft — unique (as_of, store_id, sku_id), INSERT OR IGNORE>

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


