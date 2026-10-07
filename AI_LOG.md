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