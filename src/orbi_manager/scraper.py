"""Read-only collection of the logged-in user's own posts.

Posts come straight from the site's member search (`?type=imin&q=<uid>`).

Parsing is entirely selector-driven (see `selectors.py`).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from selectolax.parser import HTMLParser, Node

from . import config, selectors
from .models import Post

ProgressCallback = Callable[[int, int], None]
"""Called as (rows_so_far, pages_or_posts_fetched)."""

StopCallback = Callable[[], bool]
"""Asked between list pages; True means give back what was collected so far."""


class ScrapeError(RuntimeError):
    """A page could not be fetched, or contained no recognisable rows."""


# -- helpers -----------------------------------------------------------------


def _get(client: httpx.Client, url: str) -> HTMLParser:
    try:
        response = client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as err:
        raise ScrapeError(f"요청 실패: {url} ({err})") from err
    return HTMLParser(response.text)


def _strip_query(url: str) -> str:
    """List links carry `?q=…&type=…`; the canonical post URL does not."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _absolute(href: str) -> str:
    return _strip_query(urljoin(config.SITE, href))


def _is_notice(row: Node) -> bool:
    return selectors.NOTICE_CLASS in (row.attributes.get("class") or "")


def _row_author_id(row: Node) -> str | None:
    author = row.css_first(selectors.ROW_AUTHOR)
    if author is None:
        return None
    return author.attributes.get(selectors.ROW_AUTHOR_ID_ATTR)


def _row_post_link(row: Node) -> Node | None:
    """The title link — the one whose href holds a post id, not a tag link."""
    block = row.css_first(selectors.ROW_TITLE_BLOCK) or row
    for anchor in block.css("a"):
        href = anchor.attributes.get("href") or ""
        if selectors.post_id_from_url(href):
            return anchor
    return None


def _row_date(row: Node) -> str:
    node = row.css_first(selectors.ROW_DATE)
    if node is None:
        return ""
    # title="@2026-08-11 22:48:21" is absolute; the visible text is relative.
    absolute = node.attributes.get(selectors.ROW_DATE_TITLE_ATTR) or ""
    return absolute.lstrip("@").strip() or node.text(strip=True)


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
        uid = node.attributes.get(selectors.ROW_AUTHOR_ID_ATTR)
        if uid:
            return uid

    raise ScrapeError("로그인 상태를 확인할 수 없습니다. 다시 로그인하세요.")


# -- list walking ------------------------------------------------------------


def _walk_search(
    client: httpx.Client,
    kind: str,
    uid: str,
    on_progress: ProgressCallback | None,
    limit: int | None = None,
    should_stop: StopCallback | None = None,
) -> Iterator[tuple[str, Node]]:
    """Yield (post_id, row) for every non-notice row, up to ``limit`` rows.

    A stop is honoured between pages, so the rows already yielded stay usable.
    """
    seen: set[str] = set()
    for page in range(1, config.MAX_PAGES + 1):
        if should_stop is not None and should_stop():
            return
        tree = _get(
            client, selectors.SEARCH_URL.format(kind=kind, uid=uid, page=page)
        )
        rows = tree.css(selectors.LIST_ROW)
        if not rows:
            break

        new_on_page = 0
        for row in rows:
            if _is_notice(row):
                continue
            link = _row_post_link(row)
            if link is None:
                continue
            post_id = selectors.post_id_from_url(link.attributes.get("href") or "")
            if post_id is None or post_id in seen:
                continue
            seen.add(post_id)
            new_on_page += 1
            yield post_id, row
            if limit is not None and len(seen) >= limit:
                return

        if on_progress is not None:
            on_progress(len(seen), page)

        # Nothing new on this page: the list has run out (the site keeps
        # serving the last page rather than 404ing).
        if new_on_page == 0:
            break
        if should_stop is not None and should_stop():
            return
        time.sleep(config.LIST_PAGE_DELAY_SEC)


def fetch_posts(
    client: httpx.Client,
    on_progress: ProgressCallback | None = None,
    uid: str | None = None,
    limit: int | None = None,
    should_stop: StopCallback | None = None,
) -> list[Post]:
    """The logged-in user's posts, newest first, up to ``limit`` of them.

    A stopped fetch returns the posts collected so far — even none — rather
    than raising: nothing went wrong, the user just asked it to end early.
    """
    uid = uid or current_user_id(client)
    limit = limit or config.MAX_FETCH_POSTS
    posts: list[Post] = []

    for post_id, row in _walk_search(
        client, selectors.KIND_MY_POSTS, uid, on_progress, limit, should_stop
    ):
        author = _row_author_id(row)
        if author is not None and author != uid:
            continue  # defensive: search should only return this member's posts
        link = _row_post_link(row)
        assert link is not None  # _walk_search only yields rows that have one
        posts.append(
            Post(
                id=post_id,
                title=link.text(strip=True),
                url=_absolute(link.attributes.get("href") or ""),
                created_at=_row_date(row),
            )
        )

    if not posts and not (should_stop is not None and should_stop()):
        raise ScrapeError("글을 하나도 찾지 못했습니다.")
    return posts
