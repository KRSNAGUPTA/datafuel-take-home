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