# portal_client.py
"""Safe HTTP client for the QuickMart partner portal.

Design contract:
- The rest of the app never calls `requests` directly.
- Transient failures (429/5xx/timeouts) are retried with backoff.
- Terminal failures (400/401/404) raise immediately — never retry.
- A per-store inventory read NEVER raises for data-quality issues; it returns
  InventoryResult(complete=False, reason=...) so sweep.py can record honestly.
"""
import logging
import random
import threading
import time
from collections import deque
from dataclasses import dataclass

import requests

from config import (
    PORTAL_BASE, API_KEY, REQUEST_TIMEOUT_S,
    MAX_RETRIES, BACKOFF_BASE_S, BACKOFF_JITTER_S, RETRY_AFTER_FALLBACK_S,
    GLOBAL_MIN_INTERVAL_S, FAIR_USE_WINDOW_S, FAIR_USE_MAX_REQS,
    SOFT_BAN_BACKOFF_S,
    REASON_PARTIAL, REASON_SOFT_BAN, REASON_RETRIES, MAX_INVENTORY_PAGES, MAX_STORE_PAGES
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

class PortalError(Exception):
    """Unrecoverable portal failure — bad request, unknown store, exhausted retries."""


@dataclass
class InventoryResult:
    """Outcome of reading one store's inventory for one as_of.

    `complete=False` means: DO NOT trust these items as a full snapshot.
    `reason` is one of config.REASON_* and is meant to be surfaced in
    coverage.incomplete[] and written to sweep_store_status.
    """
    items: list[dict]
    complete: bool
    reason: str | None = None


# ---------------------------------------------------------------------------
# Transport: session, classifier, rate limiter, retry
# ---------------------------------------------------------------------------

_session = requests.Session()
_session.headers.update({"X-Api-Key": API_KEY}) # All endpoints except health reuire this header


def _get(path: str, params: dict | None = None) -> requests.Response:
    return _session.get(f"{PORTAL_BASE}{path}", params=params, timeout=REQUEST_TIMEOUT_S)


RETRYABLE_STATUS = {429, 500, 502, 503, 504}
TERMINAL_STATUS  = {400, 401, 404} # No retry if these status appear in res.status_code


def _classify(resp: requests.Response) -> str:
    """'ok' | 'retry' | 'terminal'.

    Terminal-by-default so we never loop on an unexpected status.
    """
    if resp.status_code == 200:
        return "ok"
    if resp.status_code in TERMINAL_STATUS:
        return "terminal"
    if resp.status_code in RETRYABLE_STATUS:
        return "retry"
    return "terminal"


_rl_lock = threading.Lock()
_last_request_at = [0.0]
_window: deque[float] = deque() # ts as weight for this priority queue window


def _rate_limit() -> None:
    """Block until it's safe to send another request.

    Two ceilings, whichever is tighter:
      - GLOBAL_MIN_INTERVAL_S between any two requests (burst cap)
      - FAIR_USE_MAX_REQS within FAIR_USE_WINDOW_S (sliding window)
    """
    while True:
        with _rl_lock:
            now = time.monotonic()
            gap = now - _last_request_at[0]
            if gap < GLOBAL_MIN_INTERVAL_S:
                wait = GLOBAL_MIN_INTERVAL_S - gap
            else:
                while _window and now - _window[0] > FAIR_USE_WINDOW_S:
                    _window.popleft()
                if len(_window) >= FAIR_USE_MAX_REQS:
                    wait = FAIR_USE_WINDOW_S - (now - _window[0]) + 0.01
                else:
                    _last_request_at[0] = now
                    _window.append(now)
                    return
        time.sleep(wait)


def _backoff_sleep(attempt: int, retry_after: float | None = None) -> None:
    if retry_after is not None:
        delay = retry_after
    else:
        delay = BACKOFF_BASE_S * (2 ** attempt) + random.uniform(0, BACKOFF_JITTER_S)
    log.debug("backing off %.2fs (attempt %d)", delay, attempt + 1)
    time.sleep(delay)


def _get_with_retries(path: str, params: dict | None = None) -> requests.Response:
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            _rate_limit()
            resp = _get(path, params)
        except (requests.Timeout, requests.ConnectionError) as e:
            last_exc = e
            if attempt >= MAX_RETRIES:
                raise PortalError(f"network failure after {MAX_RETRIES} retries: {e}") from e
            _backoff_sleep(attempt)
            continue

        kind = _classify(resp)
        if kind == "ok":
            return resp
        if kind == "terminal":
            raise PortalError(f"{resp.status_code} {resp.text[:200]}")
        if attempt >= MAX_RETRIES:
            raise PortalError(f"retries exhausted on {resp.status_code}: {resp.text[:200]}")
        retry_after = None
        if resp.status_code == 429:
            hdr = resp.headers.get("Retry-After")
            retry_after = float(hdr) if hdr else RETRY_AFTER_FALLBACK_S
        _backoff_sleep(attempt, retry_after)
    raise PortalError(f"unreachable (last exception: {last_exc})")


# ---------------------------------------------------------------------------
# Domain: stores, soft-ban detection, inventory
# ---------------------------------------------------------------------------

def fetch_stores() -> list[dict]:
    """All stores across every page, as returned by /v1/stores.
    
     Raises PortalError if the server returns more than MAX_STORE_PAGES pages a defensive cap against a misbehaving server that never sets next_page to null.
    """
    stores: list[dict] = []
    page = 1 # As per API.md -> Page Start at 1
    pages_fetched = 0 # As per API.md we have 3 pages with 12 with total 30 Stores, but 15 is for safety if server keep returning next with stale data
   
    while True:
        if pages_fetched >= MAX_STORE_PAGES:
            raise PortalError(
                f"store pagination exceeded {MAX_STORE_PAGES} pages; "
                "server may be misbehaving"
            )
        resp = _get_with_retries("/v1/stores", {"page": page})
        body = resp.json()
        stores.extend(body["stores"])
        pages_fetched+=1
        nxt = body.get("next_page")
        if not nxt:
            return stores
        page = nxt


def _is_soft_banned(body: dict, page_items: list) -> bool:
    """The mock returns HTTP 200 with meta.source == 'edge' when soft-banned.

    The tell is edge-source + (empty items OR truncated first page). A full
    first page is ~15 items. Requiring the conjunction keeps us from false
    positives on a legitimately short last page.
    """
    src = (body.get("meta") or {}).get("source")
    if src != "edge":
        return False
    if not page_items:
        return True
    if body.get("next_cursor") and len(page_items) < 15: #hardcoded because api.md state 15 items will return on each page
        return True
    return False


def fetch_inventory(store_id: str, as_of: str) -> InventoryResult:
    """Fetch every inventory page for (store_id, as_of).

    Never raises for data-quality problems: returns complete=False with a
    REASON_* constant instead. Raises PortalError only for terminal statuses
    we can't recover from at all (404 unknown store, 400 bad as_of) — the
    caller (sweep.py) decides whether that store is skipped for the sweep.
    """
    items: list[dict] = []
    seen_sku_ids: set[str] = set()
    cursor = "0"

    pages_fetched = 0

    while True:
        if(pages_fetched >= MAX_INVENTORY_PAGES):
            log.warning("inventory %s %s: page cap exceeded", store_id, as_of)
            return InventoryResult(items=items, complete=False, reason=REASON_RETRIES)
        try:
            resp = _get_with_retries(
                f"/v1/stores/{store_id}/inventory",
                {"as_of": as_of, "cursor": cursor},
            )
        except PortalError as e:
            log.warning("inventory %s %s: %s", store_id, as_of, e)
            return InventoryResult(items=items, complete=False, reason=REASON_RETRIES)

        body = resp.json()
        page_items = body.get("items") or []

        if _is_soft_banned(body, page_items):
            log.warning("soft ban detected on %s @ %s; backing off %.0fs",
                        store_id, as_of, SOFT_BAN_BACKOFF_S)
            time.sleep(SOFT_BAN_BACKOFF_S)
            return InventoryResult(items=items, complete=False, reason=REASON_SOFT_BAN)

        if body.get("partial"):
            return InventoryResult(items=items, complete=False, reason=REASON_PARTIAL)

        # Dedupe by sku_id: the mock repeats the previous page's last item
        # ~35% of the time when cursor > 0, and a sku_id can't legitimately
        # appear twice for one (store, as_of).
        for it in page_items:
            sid = it["sku_id"]
            if sid in seen_sku_ids:
                continue
            seen_sku_ids.add(sid)
            items.append(it)

        nxt = body.get("next_cursor")
        pages_fetched+=1
        if not nxt:
            # Complete: no partial flag, no ban, we drained every page.
            # NOTE: an empty list here is a *complete* observation of a store
            # carrying nothing (e.g. BLR-007 pre-launch) — NOT incompleteness.
            return InventoryResult(items=items, complete=True, reason=None)
        cursor = nxt