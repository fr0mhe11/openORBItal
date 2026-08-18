"""Static configuration: hosts, timing rules and safety limits.

Everything here is intentionally conservative.
"""

from __future__ import annotations

from pathlib import Path

# --- Hosts / URLs -----------------------------------------------------------

SITE = "https://orbi.kr"

# --- Timing / limits --------------------------------------------------------

#: Seconds to back off after the site answers 429 (rate limited). Only the
#: fallback: a 429 carrying its own ``Retry-After`` is waited out for the time
#: the site actually asked for, clamped to the two bounds below.
DELETE_COOLDOWN_SEC = 60
#: Clamp for programmatic callers — ``Cooldown(0)`` waits 5 seconds, not none.
#: Doubles as the UI spinbox minimum, so the UI cannot produce a value below
#: this and the clamp never fires on that path. Not a guard against the UI.
MIN_COOLDOWN_SEC = 5
#: Ceiling for a ``Retry-After`` the site sends. A header asking for an hour
#: is far likelier to be a misconfiguration than a real instruction, and the
#: user can always start the batch again.
MAX_COOLDOWN_SEC = 300
#: How many times a row answering 429 is retried, each attempt preceded by the
#: cooldown. Exhausting them ends the batch: a rate limit applies to the whole
#: session, not to one row, so the next row would only be told the same thing.
#: This also bounds the wait — at most (1 + retries) attempts per row.
RATE_LIMIT_RETRIES = 2
#: Maximum rows that may be selected for a single destructive run.
MAX_BATCH = 300
#: Abort a batch after this many consecutive *real* failures (auth lost,
#: server error, network down). Rows the site refuses are skipped, not
#: counted, so one bad row never ends a run.
MAX_CONSECUTIVE_FAILURES = 3

# --- Pacing between ordinary rows -------------------------------------------
#
# No rate limit was signalled, but do not hammer the server either. These
# feed `pacing.Pacer`, which spaces requests by *rate* — the interval is
# counted from when the previous request started, so a request that took
# 400ms of its own does not then also wait a full interval on top.

#: Interval a fresh batch starts at, and the fastest it is ever allowed to
#: go: 0.5s is 2 requests/second, about the pace of someone clicking through
#: the site's own delete buttons quickly.
PACE_START_SEC = 0.5
PACE_FLOOR_SEC = 0.5
#: Slowest the interval backs off to after repeated 429s.
PACE_CEILING_SEC = 8.0
#: Clean rows in a row before the interval steps back down toward the floor.
PACE_SPEEDUP_AFTER = 5
#: A 429 multiplies the interval by this. Backing off fast and recovering
#: slowly is what keeps a fixed guess from being the thing pacing the batch.
PACE_BACKOFF_FACTOR = 4.0
#: 안전 모드: the old fixed interval, kept as a one-click way back to the
#: behaviour this tool shipped with.
SAFE_MODE_DELAY_SEC = 2

#: The read side gets a much lower floor than deletes: a GET against the
#: profile timeline is what a browser's own infinite scroll already fires,
#: and a failed read costs nothing but a retry — there is no row it could
#: half-delete. 0.15s is close to 7 requests/second; the ceiling, speed-up
#: count and backoff factor above are shared with the delete pacer.
LIST_PACE_START_SEC = 0.15
LIST_PACE_FLOOR_SEC = 0.15
#: A 429 during a read is retried in place rather than failing the whole
#: fetch; this bounds how many times before giving up and surfacing an error.
LIST_RATE_LIMIT_RETRIES = 5

#: Per-request timeout for the plain HTTP client.
HTTP_TIMEOUT_SEC = 20

#: Defensive cap so a pagination bug cannot loop forever.
MAX_PAGES = 200
#: How many rows one 불러오기 collects before stopping.
MAX_FETCH_POSTS = 300
#: Rows to ask the timeline for per response. The site's own JS sends no such
#: parameter and the server's default is 10; asking for more is a request to
#: make *fewer* round trips, and is dropped if the server refuses it.
TIMELINE_PAGE_SIZE = 30
#: 안전 모드: the fixed interval this tool used before the adaptive read pacer
#: existed, and the `limit` probe is skipped too — 안전 모드 asks the timeline
#: exactly the way it always did, not just at the old speed.
LIST_SAFE_MODE_DELAY_SEC = 0.5

# --- Paths ------------------------------------------------------------------


def default_backup_dir() -> Path:
    return Path.home() / "orbi-backups"
