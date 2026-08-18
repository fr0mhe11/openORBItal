"""Read-only collection of the logged-in user's own posts.

Posts come from the member's own profile timeline (`/api/v1/user/<uid>/timeline`)
— unlike the site's search, this list is not missing posts an admin has
"모어보기 밴"'d off the search index (see `selectors.TIMELINE_URL`).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from selectolax.parser import HTMLParser

from . import config, selectors
from .models import Post
from .pacing import Pacer

ProgressCallback = Callable[[int, int], None]
"""Called as (rows_so_far, pages_or_posts_fetched)."""

StopCallback = Callable[[], bool]
"""Asked between list pages; True means give back what was collected so far."""


class ScrapeError(RuntimeError):
    """A page could not be fetched, or contained no recognisable rows."""


class RateLimited(ScrapeError):
    """The timeline answered 429.

    Kept distinct from :class:`ScrapeError` so callers can tell "the site
    asked us to slow down" apart from every other way a page can fail — the
    two need opposite responses: this one is worth retrying, the rest are not.
    """


# -- helpers -----------------------------------------------------------------


def _get(client: httpx.Client, url: str) -> HTMLParser:
    try:
        response = client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as err:
        raise ScrapeError(f"요청 실패: {url} ({err})") from err
    return HTMLParser(response.text)


def _get_json(client: httpx.Client, url: str) -> dict[str, Any]:
    try:
        response = client.get(url)
        if response.status_code == 429:
            raise RateLimited(f"429 Too Many Requests: {url}")
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as err:
        raise ScrapeError(f"요청 실패: {url} ({err})") from err
    except ValueError as err:
        raise ScrapeError(f"응답을 해석할 수 없습니다: {url} ({err})") from err
    if not isinstance(payload, dict) or not payload.get("success"):
        raise ScrapeError(f"요청이 거부되었습니다: {url}")
    return payload


def _strip_query(url: str) -> str:
    """List links carry `?q=…&type=…`; the canonical post URL does not."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _absolute(href: str) -> str:
    return _strip_query(urljoin(config.SITE, href))


def _item_date(item: dict[str, Any]) -> str:
    # "2026-08-18T22:43:04" -> "2026-08-18 22:43:04", matching the site's own
    # display format.
    return str(item.get("created_at") or "").replace("T", " ", 1)


# -- session identity --------------------------------------------------------


def current_user_id(client: httpx.Client) -> str:
    """The logged-in member id (orbi calls it `imin`)."""
    try:
        response = client.get(config.SITE)
        response.raise_for_status()
    except httpx.HTTPError as err:
        raise ScrapeError(f"사용자 확인 실패: {err}") from err

    match = selectors.OWN_USER_ID_RE.search(response.text)
    if match:
        return match.group(1)

    node = HTMLParser(response.text).css_first(selectors.OWN_USER_ID_NODE)
    if node is not None:
        uid = node.attributes.get(selectors.OWN_USER_ID_NODE_ATTR)
        if uid:
            return uid

    raise ScrapeError("로그인 상태를 확인할 수 없습니다. 다시 로그인하세요.")


# -- list walking ------------------------------------------------------------


def _timeline_page(
    client: httpx.Client,
    uid: str,
    offset: int | str,
    page_size: int | None,
) -> tuple[dict[str, Any], int | None]:
    """Fetch one timeline page, giving up on ``limit`` if the server balks.

    Returns the payload and the page size to use from here on — ``None`` once
    the server has shown it will not take one. A server that simply *ignores*
    the parameter is not a refusal: it answers normally with its own default
    size, which costs nothing extra, so the parameter keeps riding along.
    """
    if page_size is None:
        return _get_json(
            client, selectors.TIMELINE_URL.format(uid=uid, offset=offset)
        ), None

    try:
        payload = _get_json(
            client,
            selectors.TIMELINE_URL_SIZED.format(
                uid=uid, offset=offset, limit=page_size
            ),
        )
    except RateLimited:
        # Being rate limited says nothing about whether the parameter itself
        # is welcome — that is a decision for `_walk_timeline` to retry, not
        # a reason to give up on `limit` for the rest of the walk.
        raise
    except ScrapeError:
        # One fallback for the whole walk: ask again without the parameter and
        # never send it again.
        return _get_json(
            client, selectors.TIMELINE_URL.format(uid=uid, offset=offset)
        ), None
    return payload, page_size


def _walk_timeline(
    client: httpx.Client,
    uid: str,
    on_progress: ProgressCallback | None,
    limit: int | None = None,
    should_stop: StopCallback | None = None,
    safe_mode: bool = False,
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield (post_id, item) for every post in the profile timeline.

    A stop is honoured between pages, so the items already yielded stay
    usable. The timeline is cursor-paginated: each response carries the
    offset to request next, rather than a page number.

    The first request asks for a bigger page than the server's default of 10
    (see :data:`selectors.TIMELINE_URL_SIZED`). If the server refuses that
    parameter the walk drops it — once, for the whole walk — and carries on
    at whatever size the server prefers. 안전 모드 skips the probe entirely and
    asks the plain endpoint throughout, exactly as this tool always did.

    Pages are paced much closer together than deletes: this is a read, no
    different from a browser's own infinite scroll, so a wrong guess costs
    only a retry rather than a half-finished action. 안전 모드 trades that for
    the original fixed interval instead. Either way, a 429 is retried at the
    same offset — behind a backed-off pace when adaptive, the same fixed one
    otherwise — rather than failing the whole fetch, up to
    :data:`config.LIST_RATE_LIMIT_RETRIES` times, past which the site is not
    letting up and the error is allowed to surface.
    """
    seen: set[str] = set()
    offset = 0
    page_size: int | None = None if safe_mode else config.TIMELINE_PAGE_SIZE
    pace = (
        Pacer.fixed(config.LIST_SAFE_MODE_DELAY_SEC)
        if safe_mode
        else Pacer(start=config.LIST_PACE_START_SEC, floor=config.LIST_PACE_FLOOR_SEC)
    )
    consecutive_rate_limits = 0
    for page in range(1, config.MAX_PAGES + 1):
        if should_stop is not None and should_stop():
            return
        pace.wait()
        try:
            payload, page_size = _timeline_page(client, uid, offset, page_size)
        except RateLimited:
            consecutive_rate_limits += 1
            pace.on_rate_limited()
            if consecutive_rate_limits > config.LIST_RATE_LIMIT_RETRIES:
                raise
            continue  # retry the same offset once the backed-off pace allows
        consecutive_rate_limits = 0
        pace.on_success()
        data = payload.get("data") or {}
        items = data.get("posts") or []
        if not items:
            break

        new_on_page = 0
        for item in items:
            post_id = selectors.post_id_from_url(str(item.get("url") or ""))
            if post_id is None or post_id in seen:
                continue
            seen.add(post_id)
            new_on_page += 1
            yield post_id, item
            if limit is not None and len(seen) >= limit:
                return

        if on_progress is not None:
            on_progress(len(seen), page)

        next_offset = data.get("offset")
        # No new ids, or the cursor stopped moving: the list has run out.
        if new_on_page == 0 or next_offset is None or next_offset == offset:
            break
        offset = next_offset


def fetch_posts(
    client: httpx.Client,
    on_progress: ProgressCallback | None = None,
    uid: str | None = None,
    limit: int | None = None,
    should_stop: StopCallback | None = None,
    safe_mode: bool = False,
) -> list[Post]:
    """The logged-in user's posts, newest first, up to ``limit`` of them.

    A stopped fetch returns the posts collected so far — even none — rather
    than raising: nothing went wrong, the user just asked it to end early.
    """
    uid = uid or current_user_id(client)
    limit = limit or config.MAX_FETCH_POSTS
    posts: list[Post] = []

    walk = _walk_timeline(
        client, uid, on_progress, limit, should_stop, safe_mode=safe_mode
    )
    for post_id, item in walk:
        author = item.get("author") or {}
        author_id = author.get("imin")
        if author_id is not None and str(author_id) != str(uid):
            continue  # defensive: the timeline should only hold this member's posts
        posts.append(
            Post(
                id=post_id,
                title=str(item.get("title") or ""),
                url=_absolute(str(item.get("url") or "")),
                created_at=_item_date(item),
            )
        )

    if not posts and not (should_stop is not None and should_stop()):
        raise ScrapeError("글을 하나도 찾지 못했습니다.")
    return posts
