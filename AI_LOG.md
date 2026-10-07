# I will be using AI tools such as
- Claude Web [ I don't have claude code :( ]

Switched to Deepseek

Prompt: "Need a brief plan before jumping on it, I have to maintain a log for chat also, like prompt so first breakdown the task in chunks assign goal subtask etc, and return it. check the readme file that it should follow"

## Chunk 0 — Setup
Goal: environment, repo, recording, initial notes
Prompt: "break the take-home into chunks with goals/subtasks; FastAPI + Uvicorn stack"
Outcome: used the chunk plan as-is; made no code changes
AI wrong here: (none yet — first correctness test comes in Chunk 2)


### Chunk 1 — Schema + config
Tool: Deepseek Web
Goal: idempotent SQLite schema + shared constants
Prompt: "schema with unique (as_of,store_id,sku_id) + config for retry/backoff/rate limits"
Outcome: kept as-is; removed REASON_PRE_LAUNCH after noticing BLR-007 pre-launch empty is a complete observation (mock behavior, not a failure)

AI wrong here: AI didn't flagged about upstream error when asked initially but I discovered while testing rate-limit




### AI Wrong
AI failed to predict the real world infinite pagination bug in which server keep returning n+1 page as count with same item,
I've added a max page limit to 15: each store has max 3 pages * 5 gives safe space

- AI initially calculated wrong data bucket for ist and it was counting 12:10 AM (29 Sept) in 28 Sept, which leads to wrong result, after a full sweep and db check it was already right just AI hallicunated

### IST 2026-09-28 has 3 sweeps, not 4
The six canonical sweeps mapped to IST days:
- 2026-09-27T04:30:00Z  →  IST 2026-09-27 10:00
- 2026-09-27T10:30:00Z  →  IST 2026-09-27 16:00
- 2026-09-27T19:00:00Z  →  IST 2026-09-28 00:30   ✓
- 2026-09-28T04:30:00Z  →  IST 2026-09-28 10:00   ✓
- 2026-09-28T10:30:00Z  →  IST 2026-09-28 16:00   ✓
- 2026-09-28T18:40:00Z  →  IST 2026-09-29 00:10   (next day)

So IST 2026-09-27 has 2 sweeps, IST 2026-09-28 has 3, IST 2026-09-29 has 1.

Delhi on IST 2026-09-28: 9 tracked stores × 3 sweeps = 27 expected,
26 complete (DEL-004's partial is on the 10:30Z sweep, which is in-scope).

Mumbai: 10 × 3 = 30 expected, all complete.
Bengaluru: 9 × 3 = 27 expected, all complete.