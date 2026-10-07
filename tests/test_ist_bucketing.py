# tests/test_ist_bucketing.py
"""Cases where a wrong timezone conversion gives wrong numbers."""
from app import sweeps_for_ist_day


def _insert_sweep(conn, as_of):
    conn.execute("""
        INSERT INTO sweeps (as_of, started_at, finished_at, tracked_stores, complete_stores)
        VALUES (?, ?, ?, 0, 0)
    """, (as_of, as_of, as_of))


def test_sweep_at_1900z_buckets_to_next_ist_day(conn):
    """18:30Z is the boundary — 19:00Z must be on the *next* IST day."""
    _insert_sweep(conn, "2026-09-27T19:00:00Z")

    assert sweeps_for_ist_day(conn, "2026-09-27") == []
    assert sweeps_for_ist_day(conn, "2026-09-28") == ["2026-09-27T19:00:00Z"]


def test_sweep_at_1840z_buckets_to_next_ist_day(conn):
    """18:40Z + 5:30 = 00:10 next day."""
    _insert_sweep(conn, "2026-09-28T18:40:00Z")

    assert sweeps_for_ist_day(conn, "2026-09-28") == []
    assert sweeps_for_ist_day(conn, "2026-09-29") == ["2026-09-28T18:40:00Z"]


def test_full_six_sweep_distribution(conn):
    """The six canonical sweeps split as 2 / 3 / 1 across IST days."""
    for ts in [
        "2026-09-27T04:30:00Z",   # IST 2026-09-27
        "2026-09-27T10:30:00Z",   # IST 2026-09-27
        "2026-09-27T19:00:00Z",   # IST 2026-09-28 (crosses midnight)
        "2026-09-28T04:30:00Z",   # IST 2026-09-28
        "2026-09-28T10:30:00Z",   # IST 2026-09-28
        "2026-09-28T18:40:00Z",   # IST 2026-09-29 (crosses midnight)
    ]:
        _insert_sweep(conn, ts)

    assert len(sweeps_for_ist_day(conn, "2026-09-27")) == 2
    assert len(sweeps_for_ist_day(conn, "2026-09-28")) == 3
    assert len(sweeps_for_ist_day(conn, "2026-09-29")) == 1