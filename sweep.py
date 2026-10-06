#!/usr/bin/env python3
"""One sweep = inventory of every tracked store at one timestamp.

    python3 sweep.py --as-of 2026-09-28T04:30:00Z

Writes to osa.db: stores, sweeps, sweep_store_status, inventory.
Safe to re-run for the same --as-of: writes are idempotent.
"""
import argparse
import sys
import time
from datetime import datetime, timezone

import portal_client as pc
from config import REASON_UNKNOWN, REASON_SOFT_BAN, SOFT_BAN_COOLDOWN_S
from db import db


# Timestamp of the most recent soft ban in this process. Used to insert a
# cooldown between sweeps so back-to-back runs don't compound the ban.
_last_soft_ban_at: float = 0.0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_as_of(s: str) -> str:
    """Validate ISO-8601 with tz; return normalized UTC 'YYYY-MM-DDTHH:MM:SSZ'."""
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("--as-of must include a timezone, e.g. 2026-09-28T04:30:00Z")
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", required=True,
                    help="ISO-8601 timestamp with timezone, e.g. 2026-09-28T04:30:00Z")
    args = ap.parse_args()

    try:
        as_of = parse_as_of(args.as_of)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    started = time.time()
    with db() as conn:
        summary = run_sweep(conn, as_of)
    elapsed = time.time() - started
    print_summary(summary, elapsed)
    return 0


# ---------------------------------------------------------------------------
# DB writers
# ---------------------------------------------------------------------------

def upsert_stores(conn, as_of: str, stores: list[dict]) -> None:
    """Insert new stores; refresh mutable fields; keep first_seen_as_of."""
    conn.executemany("""
        INSERT INTO stores (store_id, city, name, is_active, is_serviceable,
                            first_seen_as_of, last_seen_as_of)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(store_id) DO UPDATE SET
            city            = excluded.city,
            name            = excluded.name,
            is_active       = excluded.is_active,
            is_serviceable  = excluded.is_serviceable,
            last_seen_as_of = excluded.last_seen_as_of
    """, [
        (s["store_id"], s["city"], s["name"],
         int(s["is_active"]), int(s["is_serviceable"]),
         as_of, as_of)
        for s in stores
    ])
    conn.commit()


def _save_inventory(conn, as_of: str, store_id: str, items: list[dict]) -> None:
    """Persist items for (as_of, store_id). INSERT OR IGNORE = idempotent re-runs."""
    rows = [
        (as_of, store_id, it["sku_id"], it.get("name"),
         int(bool(it.get("in_stock"))),
         it.get("qty"),
         str(it["price"]) if it.get("price") is not None else None,
         it.get("observed_at"))
        for it in items
    ]
    conn.executemany("""
        INSERT OR IGNORE INTO inventory
            (as_of, store_id, sku_id, name, in_stock, qty, price, observed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)

    conn.executemany("""
        INSERT INTO sku_names (sku_id, name) VALUES (?, ?)
        ON CONFLICT(sku_id) DO UPDATE SET name = excluded.name
    """, [(it["sku_id"], it.get("name")) for it in items])
    conn.commit()


def _record_status(conn, as_of: str, store_id: str, *,
                   complete: bool, reason: str | None, items_seen: int) -> None:
    conn.execute("""
        INSERT INTO sweep_store_status (as_of, store_id, complete, reason, items_seen)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(as_of, store_id) DO UPDATE SET
            complete   = excluded.complete,
            reason     = excluded.reason,
            items_seen = excluded.items_seen
    """, (as_of, store_id, int(complete), reason, items_seen))
    conn.commit()


def _finish_sweep(conn, as_of: str, *, tracked: int, complete: int,
                  started_at: str, finished_at: str) -> None:
    conn.execute("""
        INSERT INTO sweeps (as_of, started_at, finished_at, tracked_stores, complete_stores)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(as_of) DO UPDATE SET
            finished_at     = excluded.finished_at,
            tracked_stores  = excluded.tracked_stores,
            complete_stores = excluded.complete_stores
    """, (as_of, started_at, finished_at, tracked, complete))
    conn.commit()


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_sweep(conn, as_of: str) -> dict:
    global _last_soft_ban_at

    # If a recent sweep in this process hit a soft ban, wait out the window
    # so consecutive sweeps don't compound it.
    if _last_soft_ban_at:
        since = time.monotonic() - _last_soft_ban_at
        if since < SOFT_BAN_COOLDOWN_S:
            wait = SOFT_BAN_COOLDOWN_S - since
            print(f"cooldown {wait:.0f}s after recent soft ban")
            time.sleep(wait)

    started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    stores = pc.fetch_stores()
    upsert_stores(conn, as_of, stores)

    # Track a store if the API says it exists OR can serve a customer right now.
    # - decommissioned-but-serviceable → still orderable → include
    # - active-but-non-serviceable → temporarily down → include (excluding it
    #   would bias OSA upward, since a non-serviceable store is likelier empty)
    tracked = [s for s in stores if s["is_active"] or s["is_serviceable"]]
    complete = 0
    incomplete: list[dict] = []

    for s in tracked:
        sid = s["store_id"]
        result = pc.fetch_inventory(sid, as_of)

        if result.complete:
            _save_inventory(conn, as_of, sid, result.items)
            _record_status(conn, as_of, sid, complete=True, reason=None,
                           items_seen=len(result.items))
            complete += 1
        else:
            reason = result.reason or REASON_UNKNOWN
            if reason == REASON_SOFT_BAN:
                _last_soft_ban_at = time.monotonic()
            _record_status(conn, as_of, sid, complete=False, reason=reason,
                           items_seen=len(result.items))
            incomplete.append({"store_id": sid, "reason": reason})
            # Deliberately do NOT save partial items — see NOTES.md.

    finished_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _finish_sweep(conn, as_of, tracked=len(tracked), complete=complete,
                  started_at=started_at, finished_at=finished_at)

    return {"tracked": len(tracked), "complete": complete, "incomplete": incomplete}


def print_summary(summary: dict, elapsed: float) -> None:
    n = summary["tracked"]
    c = summary["complete"]
    inc = summary["incomplete"]
    if inc:
        parts = ", ".join(f"{x['store_id']}: {x['reason']}" for x in inc)
        inc_str = f"{len(inc)} incomplete ({parts})"
    else:
        inc_str = "0 incomplete"
    print(f"{n} stores: {c} complete, {inc_str} · {elapsed:.0f}s")


if __name__ == "__main__":
    sys.exit(main())