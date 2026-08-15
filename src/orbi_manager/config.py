"""Static configuration: hosts, timing rules and safety limits.

Everything here is intentionally conservative.
"""

from __future__ import annotations

from pathlib import Path

# --- Hosts / URLs -----------------------------------------------------------

SITE = "https://orbi.kr"

# --- Timing / limits --------------------------------------------------------

#: Seconds to back off after the site answers 429 (rate limited).
DELETE_COOLDOWN_SEC = 60
#: Hard floor for the cooldown, even if the user lowers it in the UI.
MIN_COOLDOWN_SEC = 5
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
#: Pause between ordinary rows (deleted, skipped, failed) — no rate limit was
#: signalled, but do not hammer the server either.
SKIPPED_ROW_DELAY_SEC = 2

#: Per-request timeout for the plain HTTP client.
HTTP_TIMEOUT_SEC = 20

#: Defensive cap so a pagination bug cannot loop forever.
MAX_PAGES = 200
#: How many rows one 불러오기 collects before stopping.
MAX_FETCH_POSTS = 300
#: Pause between list-page fetches (reading is cheap, but stay polite).
LIST_PAGE_DELAY_SEC = 0.5

# --- Paths ------------------------------------------------------------------


def default_backup_dir() -> Path:
    return Path.home() / "orbi-backups"
