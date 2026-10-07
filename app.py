"""GET /osa — on-shelf availability for a city on an IST calendar day.

    uvicorn app:app --reload
    curl "http://127.0.0.1:8000/osa?city=Mumbai&date=2026-09-28"
"""
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Query

from config import IST
from db import db

app = FastAPI(title="DataFuel OSA API")

CITIES = {"Mumbai", "Delhi", "Bengaluru"}


# ---------------------------------------------------------------------------
# IST-day → sweeps mapping
# ---------------------------------------------------------------------------

def sweeps_for_ist_day(conn, ist_date: str) -> list[str]:
    """UTC as_of strings whose IST calendar day equals ist_date."""
    rows = conn.execute("SELECT as_of FROM sweeps ORDER BY as_of").fetchall()
    out = []
    for (as_of,) in rows:
        utc = datetime.fromisoformat(as_of.replace("Z", "+00:00")) # Replace Z because python 3.10 (Project's min veersion doen't handle Z)
        if utc.astimezone(IST).strftime("%Y-%m-%d") == ist_date:
            out.append(as_of)
    return out


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def osa_for_city(conn, city: str, ist_date: str) -> dict:
    sweep_as_ofs = sweeps_for_ist_day(conn, ist_date)
    if not sweep_as_ofs:
        return {"status": "no_data", "observations": 0}

    ph = ",".join("?" * len(sweep_as_ofs))
    rows = conn.execute(f"""
        SELECT i.sku_id, i.in_stock
        FROM inventory i
        JOIN stores s ON s.store_id = i.store_id
        WHERE s.city = ? AND i.as_of IN ({ph})
    """, [city, *sweep_as_ofs]).fetchall()

    if not rows:
        return {"status": "no_data", "observations": 0}

    total = len(rows)
    in_stock = sum(1 for r in rows if r["in_stock"])

    per_sku: dict[str, dict] = {}
    for r in rows:
        d = per_sku.setdefault(r["sku_id"], {"observations": 0, "in_stock": 0})
        d["observations"] += 1
        d["in_stock"] += int(r["in_stock"])

    names = dict(conn.execute(
        "SELECT sku_id, name FROM sku_names WHERE sku_id IN (%s)"
        % ",".join("?" * len(per_sku)),
        list(per_sku.keys()),
    ).fetchall())

    skus = []
    for sku_id, d in sorted(per_sku.items()):
        skus.append({
            "sku_id": sku_id,
            "name": names.get(sku_id),
            "observations": d["observations"],
            "in_stock": d["in_stock"],
            "osa_pct": round(100 * d["in_stock"] / d["observations"], 2),
        })

    return {
        "osa_pct": round(100 * in_stock / total, 2),
        "observations": total,
        "skus": skus,
    }


def coverage_for(conn, city: str, ist_date: str) -> dict:
    sweep_as_ofs = sweeps_for_ist_day(conn, ist_date)
    if not sweep_as_ofs:
        return {"stores_expected": 0, "stores_complete": 0, "incomplete": []}

    ph = ",".join("?" * len(sweep_as_ofs))
    base = f"""
        FROM sweep_store_status ss
        JOIN stores s ON s.store_id = ss.store_id
        WHERE s.city = ? AND ss.as_of IN ({ph})
    """

    expected = conn.execute(f"SELECT COUNT(*) {base}",
                            [city, *sweep_as_ofs]).fetchone()[0]
    complete = conn.execute(f"SELECT COUNT(*) {base} AND ss.complete = 1",
                            [city, *sweep_as_ofs]).fetchone()[0]
    incomplete = conn.execute(
        f"SELECT ss.store_id, ss.as_of, ss.reason {base} AND ss.complete = 0",
        [city, *sweep_as_ofs],
    ).fetchall()

    return {
        "stores_expected": expected,
        "stores_complete": complete,
        "incomplete": [
            {"store_id": r["store_id"], "sweep": r["as_of"], "reason": r["reason"]}
            for r in incomplete
        ],
    }


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@app.get("/osa")
def get_osa(
    city: str = Query(..., description="Mumbai, Delhi or Bengaluru"),
    date_: str | None = Query(None, alias="date",
                              description="IST calendar day YYYY-MM-DD; defaults to yesterday IST"),
    sku_id: str | None = Query(None, description="Optional: filter to one SKU"),
):
    if city not in CITIES:
        raise HTTPException(status_code=400,
                            detail=f"city must be one of {sorted(CITIES)}")

    if date_ is None:
        ist_date = (datetime.now(IST).date() - timedelta(days=1)).isoformat()
    else:
        try:
            datetime.strptime(date_, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
        ist_date = date_

    with db() as conn:
        osa = osa_for_city(conn, city, ist_date)
        cov = coverage_for(conn, city, ist_date)

    if osa.get("status") == "no_data":
        return {
            "city": city,
            "date": ist_date,
            "status": "no_data",
            "observations": 0,
            "coverage": cov,
        }

    skus = osa["skus"]
    if sku_id is not None:
        skus = [s for s in skus if s["sku_id"] == sku_id]
        if not skus:
            raise HTTPException(
                status_code=404,
                detail=f"sku {sku_id} not observed in {city} on {ist_date}",
            )

    return {
        "city": city,
        "date": ist_date,
        "osa_pct": osa["osa_pct"],
        "observations": osa["observations"],
        "coverage": cov,
        "skus": skus,
    }