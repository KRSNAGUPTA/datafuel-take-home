# tests/test_idempotency.py
"""Cases where duplicates or reruns would produce wrong numbers."""
import pytest


def _insert_inventory(conn, rows):
    conn.executemany("""
        INSERT OR IGNORE INTO inventory
            (as_of, store_id, sku_id, name, in_stock, qty, price, observed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()


def test_duplicate_sku_does_not_double_count(conn):
    """Same (as_of, store_id, sku_id) inserted twice must produce one row."""
    row = ("2026-09-28T04:30:00Z", "MUM-001", "SKU-0002",
           "Britannia Brown Bread 400g", 1, 12, "237.5",
           "2026-09-28T04:37:00Z")

    _insert_inventory(conn, [row, row])          # same row twice

    (n,) = conn.execute(
        "SELECT COUNT(*) FROM inventory WHERE store_id='MUM-001' AND sku_id='SKU-0002'"
    ).fetchone()
    assert n == 1, "duplicate (as_of,store_id,sku_id) must collapse to one row"


def test_rerunning_same_sweep_does_not_grow_table(conn):
    """Simulates a sweep that writes the same batch twice."""
    rows = [
        ("2026-09-28T04:30:00Z", "MUM-001", "SKU-0001", "A", 1, 5, "10.0",
         "2026-09-28T04:37:00Z"),
        ("2026-09-28T04:30:00Z", "MUM-001", "SKU-0002", "B", 0, 0, "20.0",
         "2026-09-28T04:37:00Z"),
    ]
    _insert_inventory(conn, rows)
    (n1,) = conn.execute("SELECT COUNT(*) FROM inventory").fetchone()

    _insert_inventory(conn, rows)                # rerun
    (n2,) = conn.execute("SELECT COUNT(*) FROM inventory").fetchone()

    assert n1 == n2 == 2