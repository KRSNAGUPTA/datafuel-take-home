"""Constants shared across sweep.py, app.py and tests."""
import os
from zoneinfo import ZoneInfo

# --- Portal ---
PORTAL_BASE = f"http://127.0.0.1:{os.environ.get('PORT', '8765')}"
API_KEY = "dfhire-2026"

# --- Time ---
IST = ZoneInfo("Asia/Kolkata")            # UTC+5:30
SWEEP_TIMES_UTC = [
    "2026-09-27T04:30:00Z",
    "2026-09-27T10:30:00Z",
    "2026-09-27T19:00:00Z",
    "2026-09-28T04:30:00Z",
    "2026-09-28T10:30:00Z",
    "2026-09-28T18:40:00Z",
]

# --- HTTP ---
REQUEST_TIMEOUT_S = 8.0
MAX_RETRIES = 4
BACKOFF_BASE_S = 0.5                      # 0.5, 1, 2, 4
BACKOFF_JITTER_S = 0.25
RETRY_AFTER_FALLBACK_S = 2.0

# Rate limiting: keep under ~8 req/s burst and under the 10s / 30-req window.
GLOBAL_MIN_INTERVAL_S = 0.15              # ~6.7 req/s burst cap
FAIR_USE_WINDOW_S = 10.0
FAIR_USE_MAX_REQS = 15                    

# --- Soft ban ---
SOFT_BAN_BACKOFF_S = 30.0
SOFT_BAN_MAX_BACKOFF_S = 90.0
SOFT_BAN_COOLDOWN_S = 15.0                # sleep between sweeps after a ban

# --- Completeness reasons ---
# NOTE: pre-launch empty is NOT here. A store that legitimately carries zero
# products is a *complete* observation, not a read failure.
REASON_PARTIAL  = "partial_flag"
REASON_SOFT_BAN = "soft_ban"
REASON_RETRIES  = "retries_exhausted"
REASON_UNKNOWN  = "unknown"

# --- DB ---
DB_PATH = "osa.db"