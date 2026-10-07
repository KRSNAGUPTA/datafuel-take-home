"""
Fixed:
  1. Mutable default `results=[]` — cross-store contamination. Now local.
  2. Infinite retry loop — now bounded (4 attempts), status-aware
     (4xx terminal, 429/5xx retryable), honors Retry-After, 8s timeout.
     Pagination flattened from recursion to iteration.

Not fixed (documented in REVIEW.md):
  - save(): f-string SQL interpolation (breaks on quotes; injection).
  - city_osa(): uses qty > 0 instead of in_stock.
  - city_osa(): averages per-store percentages instead of aggregating.
  - city_osa(): substr(observed_at,1,10) mixes UTC and IST formats.
  - __main__: stores table never populated; datetime.utcnow() is naive.

"""
import sqlite3
import time
from datetime import date, datetime, timedelta

import requests

PORTAL = "http://127.0.0.1:8765"
HEADERS = {"X-Api-Key": "dfhire-2026"}

def fetch_inventory(store_id, as_of, cursor="0"):
    """Fetch every page for a store, retrying transient failures with backoff."""
    results = [] # So stays within the function / not shared ( previously it was passed as param)
    max_retries = 4

    while True:                                       # outer loop: pages
        curr_attempt = 0                              # reset retry budget per page

        while True:                                   # inner loop: retries for this page
            try:
                r = requests.get(
                    f"{PORTAL}/v1/stores/{store_id}/inventory",
                    params={"as_of": as_of, "cursor": cursor},
                    headers=HEADERS,
                    timeout=8.0, # add timeout
                )
            except (requests.Timeout, requests.ConnectionError):
                curr_attempt += 1
                if curr_attempt >= max_retries:
                    raise
                time.sleep(0.5 * (2 ** curr_attempt))
                continue

            if r.status_code in (400, 401, 404):
                r.raise_for_status()

            if r.status_code in (429, 500, 502, 503, 504):
                curr_attempt += 1
                if curr_attempt >= max_retries:
                    r.raise_for_status()
                retry_after = r.headers.get("Retry-After")
                time.sleep(float(retry_after) if retry_after else 0.5 * (2 ** curr_attempt))
                continue

            r.raise_for_status()
            break                                     # this page succeeded

        body = r.json()
        results.extend(body["items"])

        if not body["next_cursor"]:
            return results

        cursor = body["next_cursor"]
        # outer loop continues with the new cursor

def save(conn, store_id, items):
    for it in items:
        conn.execute(
            f"INSERT INTO inventory VALUES ('{store_id}', '{it['sku_id']}', '{it['name']}', "
            f"{int(it['in_stock'])}, {it['qty']}, '{it['observed_at']}')"
        )
    conn.commit()


def city_osa(conn, city, day=None):
    """On-shelf availability for a city on a day. Defaults to yesterday."""
    day = day or (date.today() - timedelta(days=1)).isoformat()
    stores = [r[0] for r in conn.execute(
        "SELECT store_id FROM stores WHERE city = ?", (city,))]
    per_store = []
    for s in stores:
        rows = conn.execute(
            "SELECT qty FROM inventory WHERE store_id = ? AND substr(observed_at, 1, 10) = ?",
            (s, day),
        ).fetchall()
        in_stock = sum(1 for (qty,) in rows if qty > 0)
        per_store.append(in_stock / len(rows) if rows else 0.0)
    return round(100 * sum(per_store) / len(per_store), 2)


if __name__ == "__main__":
    conn = sqlite3.connect("osa.db")
    conn.execute("CREATE TABLE IF NOT EXISTS stores (store_id TEXT, city TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS inventory (store_id TEXT, sku_id TEXT, name TEXT, "
                 "in_stock INT, qty INT, observed_at TEXT)")
    for sid in ["MUM-001", "MUM-002"]:
        save(conn, sid, fetch_inventory(sid, datetime.utcnow().isoformat()))
    print(city_osa(conn, "Mumbai"))
