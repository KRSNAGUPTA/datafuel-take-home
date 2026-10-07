# DataFuel Take-Home — Inventory Scraper & OSA API

Scrapes the QuickMart partner portal (`mock_portal.py`) into SQLite and exposes
an on-shelf availability (OSA) report via FastAPI.

## Requirements
- Python 3.10+
- SQLite (bundled with Python)

## Setup

    python3 -m venv .venv
    source .venv/bin/activate          # Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    cp .env.example .env               # fills in API_KEY and PORT (defaults 8765)

## Running the mock portal

The mock is third-party and must not be modified. Start it in its own terminal:

    python3 mock_portal.py
    # → QuickMart mock portal on http://127.0.0.1:8765  (Ctrl+C to stop)

If port 8765 is taken, use 9000 and update `.env` to match:

    PORT=9000 python3 mock_portal.py
    # then set PORT=9000 in .env

Note: `mock_portal.py` reads PORT from the shell environment, not from `.env`.
The `config.py` module reads `.env`. Keep the two in sync.

## Running the sweeps

One sweep per timestamp. Run all six (order matters for `first_seen_as_of`):

    for ts in 2026-09-27T04:30:00Z 2026-09-27T10:30:00Z 2026-09-27T19:00:00Z \
              2026-09-28T04:30:00Z 2026-09-28T10:30:00Z 2026-09-28T18:40:00Z; do
        python3 sweep.py --as-of $ts
    done

Expected: 5 sweeps clean, one with `DEL-004: partial_flag`. Zero soft bans.
Each sweep takes ~45–60s.

Safe to re-run — writes are idempotent (row counts don't change).

## Running the API

    uvicorn app:app --reload

Then:

    curl "http://127.0.0.1:8000/osa?city=Mumbai&date=2026-09-28"
    curl "http://127.0.0.1:8000/osa?city=Delhi&date=2026-09-28"
    curl "http://127.0.0.1:8000/osa?city=Bengaluru&date=2026-09-28"

Interactive docs at `http://127.0.0.1:8000/docs`.

Optional SKU filter:

    curl "http://127.0.0.1:8000/osa?city=Mumbai&date=2026-09-28&sku_id=SKU-0002"

Error and no-data cases:

    curl "http://127.0.0.1:8000/osa?city=Chennai&date=2026-09-28"       # 400
    curl "http://127.0.0.1:8000/osa?city=Mumbai&date=2026-13-99"        # 400
    curl "http://127.0.0.1:8000/osa?city=Mumbai&date=2026-10-01"        # no_data
    curl "http://127.0.0.1:8000/osa?city=Mumbai"                        # yesterday IST

## Tests

    pytest

## File layout

    README.md             this file
    API.md                partner portal contract (given)
    mock_portal.py        mock server (given, unchanged)
    review_me.py          AI-written file under review (fixed)
    REVIEW.md             review write-up
    NOTES.md              decisions and problem-handling notes
    AI_LOG.md             AI tool usage log
    RECORDING.md          screen recording links
    config.py             constants
    db.py                 SQLite schema and helpers
    portal_client.py      HTTP client (retry, rate limit, soft ban)
    sweep.py              orchestrator
    app.py                FastAPI /osa endpoint
    tests/                pytest suite
    requirements.txt
    .env.example          template — copy to .env
    .gitignore

## Notes

- The mock portal is not modified.
- The API key and port are read from `.env` via `python-dotenv`.
- The SQLite file (`osa.db`) is gitignored; a fresh clone creates it on first sweep.
- `NOTES.md` explains store-tracking rules, soft-ban handling, IST bucketing,
  and the pagination safety cap.