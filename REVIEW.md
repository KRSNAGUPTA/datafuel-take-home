## 1. Mutable default `results=[]` (FIXED)
The list is created once at import time and shared across every call. Running
the `__main__` loop: MUM-002's saved rows contain MUM-001's products, all
under MUM-002's store_id. Silent cross-store contamination.
Fix: `results` is now local.

## 2. Infinite retry loop (FIXED)
`except Exception: sleep(0.1); continue` retries 400/401/404 forever, ignores
`Retry-After`, and hides programming bugs. On the mock, 100ms retries blow
the soft-ban threshold (30 req / 10s) in seconds.
Fix: status classification (4xx terminal, 429/5xx retryable), bounded at 4
attempts, honoring `Retry-After`, 8s timeout.

## 3. SQL string interpolation (not fixed)
`save()` uses `f"INSERT ... VALUES ('{name}', ...)"`. A name like
`O'Brien's Bread 400g` breaks the SQL with a syntax error. Also an injection
pattern.
Would fix with parameterized queries.

## 4. `qty > 0` instead of `in_stock` (not fixed)
The mock has ghost rows with `in_stock=true, qty=0`. Counting by `qty > 0`
marks those as out of stock, biasing OSA downward. A store with 20 rows,
one ghost → this code returns 95% where reality is 100%.

## 5. Mean of per-store percentages (not fixed)
`sum(per_store)/len(per_store)` weights every store equally regardless of
observation count. Store A (2 rows, 100%) and store B (20 rows, 25%) →
this code returns 62.50%; correct is 31.82%.