"""Deletion of the user's own posts.

The site's own AngularJS controller does this:

    deletePost: window.confirm(…) && httpUnited.delete('/delete/79187183')

`httpUnited.delete` is named delete but its body is `$http.post(url)`, so
this is an HTTP POST, not DELETE (a real DELETE gets a 405). It returns
JSON, and the session cookie is the only credential — there is no CSRF
token to carry, so replaying that request directly is all deletion takes.

That last part cuts both ways: because the cookie is the only credential,
losing it mid-batch is invisible at the status-code level. The site answers a
logged-out delete with a redirect to the login page, and a client that
follows redirects lands on a perfectly ordinary 200 having deleted nothing.
:func:`_delete_http` therefore refuses to follow them.

Two rules hold everywhere in this module:

* ``dry_run=True`` does every step except issuing the request, and reports the
  exact request it would have sent.
* A single failure never raises out of a batch; it becomes a FAILED
  :class:`ActionResult` so the remaining rows still get their turn.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence

import httpx

from . import config, selectors
from .models import ActionResult, BatchSummary, Status
from .ratelimit import Cooldown

TickCallback = Callable[[int], None]
ResultCallback = Callable[[ActionResult], None]

#: The site's own XHRs carry this; sending it keeps us on the same code path.
XHR_HEADERS = {"X-Requested-With": "XMLHttpRequest"}


#: Statuses where the row itself is the problem and a retry cannot help:
#: 404 already gone, 409 conflict, and similar site-side refusals. These are
#: skipped, not counted as failures.
ROW_REFUSED_CODES = frozenset({400, 404, 409, 410, 422})


def _error_message(response: httpx.Response) -> str:
    """Pull the site's own error text out of a JSON error response."""
    try:
        payload = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    message = payload.get("message") if isinstance(payload, dict) else None
    return f"HTTP {response.status_code}: {message}" if message else (
        f"HTTP {response.status_code}"
    )


def _delete_http(
    client: httpx.Client,
    url: str,
    method: str,
    item_id: str,
    dry_run: bool,
) -> ActionResult:
    if dry_run:
        return ActionResult(
            item_id, Status.SKIPPED_DRY_RUN, f"모의 실행: {method} {url}"
        )

    try:
        # The session client follows redirects; this request must not. See the
        # module docstring: a followed redirect turns a lost session into a 200.
        response = client.request(
            method, url, headers=XHR_HEADERS, follow_redirects=False
        )
    except httpx.HTTPError as err:
        return ActionResult(item_id, Status.FAILED, f"요청 오류: {err}")

    if 300 <= response.status_code < 400:
        # Checked by range rather than `response.is_redirect`, which also wants
        # a Location header — a 3xx without one still did not delete anything.
        #
        # FAILED, not SKIPPED: the session is gone for every remaining row too,
        # so this must count toward MAX_CONSECUTIVE_FAILURES and end the batch
        # rather than ask the login page 300 times.
        return ActionResult(
            item_id, Status.FAILED, "세션이 만료되었습니다. 다시 로그인하세요."
        )
    if response.status_code == 429:
        return ActionResult(item_id, Status.RATE_LIMITED, "429 Too Many Requests")
    if response.status_code in ROW_REFUSED_CODES:
        # The site refuses this row specifically; the next row may still work.
        return ActionResult(item_id, Status.SKIPPED, _error_message(response))
    if response.status_code >= 400:
        return ActionResult(item_id, Status.FAILED, _error_message(response))
    return ActionResult(item_id, Status.DELETED, f"HTTP {response.status_code}")


def delete_post(
    client: httpx.Client,
    post_id: str,
    post_url: str,
    dry_run: bool = True,
) -> ActionResult:
    """Delete one post. ``post_id`` may be padded (`00079187183`) or not."""
    numeric_id = selectors.unpadded(post_id)
    return _delete_http(
        client,
        selectors.DELETE_POST_URL.format(post_id=numeric_id),
        selectors.DELETE_POST_METHOD,
        post_id,
        dry_run,
    )


def _delete_with_retries(
    row,
    delete_one: Callable[[object], ActionResult],
    retries: int,
    pause: Cooldown,
    on_cooldown_tick: TickCallback | None,
) -> tuple[ActionResult, bool]:
    """Delete one row, waiting out the cooldown and trying again after a 429.

    The cooldown only earns its 60 seconds if the request it was waiting for is
    actually re-sent, so a rate-limited row is retried rather than dropped.

    Returns the last result and whether the wait was cancelled. Only the final
    result is reported to the caller, so retries never inflate the totals or
    the progress bar.
    """
    result = delete_one(row)
    for _ in range(retries):
        if result.status is not Status.RATE_LIMITED:
            break
        if not pause.wait(on_cooldown_tick):
            return result, True
        result = delete_one(row)
    return result, False


def run_batch(
    rows: Sequence,
    delete_one: Callable[[object], ActionResult],
    *,
    dry_run: bool = True,
    cooldown: Cooldown | None = None,
    on_result: ResultCallback | None = None,
    on_cooldown_tick: TickCallback | None = None,
) -> BatchSummary:
    """Delete each row in turn, moving on past rows that do not work out.

    A row the site refuses (a post already gone, a conflict) is
    recorded as SKIPPED and the batch carries on. Only real failures — auth
    lost, server errors, network down — count toward the abort threshold, so
    one bad row never ends the run.

    A 429 is different from both. It is not about the row, it is the site
    asking the whole session to slow down, so the row is retried behind the
    cooldown instead of being given up on. If it is *still* rate limited once
    the retries run out, the site is not letting up and the batch stops —
    working through the remaining rows would only ask the same question a few
    hundred more times.

    Rows that are not rate limited get a short pause instead; there is no
    evidence the site enforces a fixed delay between ordinary deletes, so
    waiting the full cooldown after each one only slows the batch down.
    """
    if len(rows) > config.MAX_BATCH:
        raise ValueError(f"한 번에 {config.MAX_BATCH}개까지만 처리합니다")

    summary = BatchSummary()
    pause = cooldown or Cooldown()
    consecutive_failures = 0
    # A dry run issues no request, so it has nothing to be rate limited by and
    # nothing to wait for.
    retries = 0 if dry_run else config.RATE_LIMIT_RETRIES

    for index, row in enumerate(rows):
        if pause.cancelled:
            summary.aborted = True
            break

        result, cancelled = _delete_with_retries(
            row, delete_one, retries, pause, on_cooldown_tick
        )
        summary.add(result)
        if on_result is not None:
            on_result(result)

        if cancelled:
            summary.aborted = True
            break

        if not dry_run and result.status is Status.RATE_LIMITED:
            # Every retry came back rate limited; the next row would too.
            summary.aborted = True
            break

        if result.status is Status.FAILED:
            consecutive_failures += 1
            if consecutive_failures >= config.MAX_CONSECUTIVE_FAILURES:
                summary.aborted = True
                break
        else:
            consecutive_failures = 0

        if index == len(rows) - 1:
            break
        if not dry_run:
            time.sleep(config.SKIPPED_ROW_DELAY_SEC)

    return summary
