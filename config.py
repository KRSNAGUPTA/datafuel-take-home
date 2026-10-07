"""Constants shared across sweep.py, app.py and tests."""
import os
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
load_dotenv()

# --- Portal ---
PORTAL_BASE = f"http://127.0.0.1:{os.environ.get('PORT', '8765')}"
API_KEY = os.environ.get('API_KEY') # Header key required for authorization

if not API_KEY:
    raise RuntimeError("API Key is not set in .env")

# --- Time ---
IST = ZoneInfo("Asia/Kolkata")            # UTC+5:30

#As per the readme file given
# here for the doc purpose only, we directly run the cli not this
SWEEP_TIMES_UTC = [ 
    "2026-09-27T04:30:00Z",
    "2026-09-27T10:30:00Z",
    "2026-09-27T19:00:00Z",
    "2026-09-28T04:30:00Z",
    "2026-09-28T10:30:00Z",
    "2026-09-28T18:40:00Z",
]

# --- HTTP ---
REQUEST_TIMEOUT_S = 8.0 # max time a request wait before timeout
MAX_RETRIES = 4 # total retry allowed: 1 initial + 4 retry = 5 total requests in worst case
BACKOFF_BASE_S = 0.5                      # 0.5, 1, 2, 4
BACKOFF_JITTER_S = 0.25 #to prevent every request hammering server after same sleep: if eg. 5 request got sleep and again hit server will give 429, so this jitter helps to spread the timing diff, so each wake at diff time and do the call
RETRY_AFTER_FALLBACK_S = 2.0 #fall back when header missing the retry-after

# Rate limiting: keep under ~8 req/s burst and under the 10s / 30-req window.
GLOBAL_MIN_INTERVAL_S = 0.15      # Gap beteen each req. 1s / 0.15s = ~6.7 req/s burst cap
FAIR_USE_WINDOW_S = 10.0    # From server /  but can be changed as per tuning
FAIR_USE_MAX_REQS = 15      #  25 -> 20 -> 15 (curr) | server limit is 30 : 15+reties = 20-25 <= 30              

# --- Soft ban ---
SOFT_BAN_BACKOFF_S = 30.0 # server ban for 20s + 5sec if retry when banned -> 30 gives 10 sec margin
SOFT_BAN_COOLDOWN_S = 15.0                # sleep between sweeps after a ban, server SOFT_WINDOW = 10 sec


# --- Pagination safety ---
# The mock returns ≤3 pages for /v1/stores (30 stores / 12 per page) and
# ≤3 per store for /inventory (~30 items / 15 per page). Caps are ~5× the
# expected maximum: enough for real growth, small enough that a misbehaving
# server fails fast instead of looping forever. A production client would
# derive these from documented API limits.
MAX_STORE_PAGES = 15 
MAX_INVENTORY_PAGES = 15


# --- Completeness reasons ---
# NOTE: pre-launch empty is NOT here. A store that legitimately carries zero
# products is a *complete* observation, not a read failure.
REASON_PARTIAL  = "partial_flag"
REASON_SOFT_BAN = "soft_ban"
REASON_RETRIES  = "retries_exhausted"
REASON_UNKNOWN  = "unknown"

# --- DB ---
DB_PATH = "osa.db"