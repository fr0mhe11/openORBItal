"""Mode registry: what each dropdown entry shows and what it may do.

Adding a mode means adding one :class:`ModeSpec` here — the table, the action
bar and the worker all read their behaviour from this record.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from . import config, deleter, scraper
from .models import ActionResult


@dataclass(frozen=True)
class Column:
    field: str
    header: str
    width: int = 160


@dataclass(frozen=True)
class ModeSpec:
    key: str
    label: str
    columns: Sequence[Column]
    fetch: Callable[..., list]
    #: Rows one 불러오기 collects before stopping.
    fetch_limit: int = config.MAX_FETCH_POSTS
    destructive: bool = False
    delete_one: Callable[..., ActionResult] | None = None
    action_label: str = "선택 삭제"


def _delete_post_row(row, client, dry_run) -> ActionResult:
    return deleter.delete_post(client, row.id, row.url, dry_run)


POST_COLUMNS = (
    Column("index", "No.", 60),
    Column("title", "제목", 420),
    Column("created_at", "작성일", 140),
    Column("url", "링크", 420),
    Column("copy", "", 70),
)

MODES: tuple[ModeSpec, ...] = (
    ModeSpec(
        key="timeline",
        label="타임라인 조회 (읽기 전용)",
        columns=POST_COLUMNS,
        fetch=scraper.fetch_posts,
    ),
    ModeSpec(
        key="delete_posts",
        label="내 글 삭제하기",
        columns=POST_COLUMNS,
        fetch=scraper.fetch_posts,
        destructive=True,
        delete_one=_delete_post_row,
    ),
    ModeSpec(
        key="export_posts",
        label="백업 export (내 글)",
        columns=POST_COLUMNS,
        fetch=scraper.fetch_posts,
        action_label="선택 백업",
    ),
)


def by_key(key: str) -> ModeSpec:
    for mode in MODES:
        if mode.key == key:
            return mode
    raise KeyError(key)
