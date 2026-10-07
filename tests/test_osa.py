# tests/test_osa.py
"""Cases where an incomplete store or the wrong field would give a wrong OSA."""
from app import coverage_for, osa_for_city


def _setup_city(conn):
    """Two stores in one city, both tracked, on one sweep."""
    conn.executemany("""
        INSERT INTO stores (store_id, city, name, is_active, is_serviceable,
                            first_seen_as_of, last_seen_as_of)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, [
        ("MUM-001", "Mumbai", "Store 1", 1, 1, "2026-09-28T04:30:00Z", "2026-09-28T04:30:00Z"),
        ("MUM-002", "Mumbai", "Store 2", 1, 1, "2026-09-28T04:30:00Z", "2026-09-28T04:30:00Z"),
    ])
    conn.execute("""
        INSERT INTO sweeps (as_of, started_at, finished_at, tracked_stores, complete_stores)
        VALUES ('2026-09-28T04:30:00Z', '2026-09-28T04:30:00Z',
                '2026-09-28T04:31:00Z', 2, 1)
    """)
    conn.executemany("""
        INSERT INTO sweep_store_status (as_of, store_id, complete, reason, items_seen)
        VALUES (?, ?, ?, ?, ?)
    """, [
        ("2026-09-28T04:30:00Z", "MUM-001", 1, None, 2),          # complete
        ("2026-09-28T04:30:00Z", "MUM-002", 0, "partial_flag", 0),  # incomplete
    ])
    conn.executemany("""
        INSERT INTO inventory
            (as_of, store_id, sku_id, name, in_stock, qty, price, observed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        ("2026-09-28T04:30:00Z", "MUM-001", "SKU-0001", "A", 1, 5, "10.0", "2026-09-28T04:37:00Z"),
        ("2026-09-28T04:30:00Z", "MUM-001", "SKU-0002", "B", 0, 0, "20.0", "2026-09-28T04:37:00Z"),
    ])
    conn.commit()


def test_incomplete_store_shows_in_coverage(conn):
    _setup_city(conn)
    cov = coverage_for(conn, "Mumbai", "2026-09-28")

    assert cov["stores_expected"] == 2
    assert cov["stores_complete"] == 1
    assert cov["incomplete"] == [
        {"store_id": "MUM-002", "sweep": "2026-09-28T04:30:00Z",
         "reason": "partial_flag"}
    ]


def test_partial_store_does_not_appear_in_inventory(conn):
    _setup_city(conn)
    (n,) = conn.execute(
        "SELECT COUNT(*) FROM inventory WHERE store_id='MUM-002'"
    ).fetchone()
    assert n == 0, "partial store must not have any inventory rows"


def test_osa_uses_in_stock_not_qty(conn):
    """Mock has 'ghost' rows: in_stock=true, qty=0. Must count as in stock."""
    conn.executemany("""
        INSERT INTO stores (store_id, city, name, is_active, is_serviceable,
                            first_seen_as_of, last_seen_as_of)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, [("MUM-001", "Mumbai", "S", 1, 1, "2026-09-28T04:30:00Z", "2026-09-28T04:30:00Z")])
    conn.execute("""
        INSERT INTO sweeps VALUES ('2026-09-28T04:30:00Z','x','y',1,1)
    """)
    conn.execute("""
        INSERT INTO sweep_store_status VALUES ('2026-09-28T04:30:00Z','MUM-001',1,NULL,2)
    """)
    conn.executemany("""
        INSERT INTO inventory VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        # In stock with qty > 0
        ("2026-09-28T04:30:00Z","MUM-001","SKU-0001","A",1,10,"1.0","2026-09-28T04:37:00Z"),
        # "Ghost" row: in_stock=true, qty=0 — must still count as in stock
        ("2026-09-28T04:30:00Z","MUM-001","SKU-0002","B",1,0,"1.0","2026-09-28T04:37:00Z"),
    ])
    conn.commit()

    osa = osa_for_city(conn, "Mumbai", "2026-09-28")
    assert osa["observations"] == 2
    # If the wrong field (qty > 0) were used, this would be 1/2 = 50.00
    assert osa["osa_pct"] == 100.00, "must use in_stock, not qty"