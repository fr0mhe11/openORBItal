"""Data records passed between scraper, deleter, exporter and the UI."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum


@dataclass(frozen=True)
class Post:
    """One post written by the logged-in user.

    ``id`` is kept as a string: orbi ids are zero-padded (``00079186801``) and
    turning them into ints loses the padding needed to rebuild URLs.
    """

    id: str
    title: str
    url: str
    created_at: str = ""

    def as_row(self) -> dict[str, str]:
        return asdict(self)


class Status(str, Enum):
    DELETED = "DELETED"
    SKIPPED_DRY_RUN = "SKIPPED_DRY_RUN"
    #: The site refused this particular row for a reason that will not change
    #: on a retry — an already-deleted post, a conflict. Not a failure of the
    #: tool, so it never counts toward the abort threshold.
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"
    RATE_LIMITED = "RATE_LIMITED"


@dataclass
class ActionResult:
    """Outcome of acting on a single row. Never raises out of a batch loop."""

    id: str
    status: Status
    message: str = ""
    #: Seconds the site itself asked us to wait, read off its ``Retry-After``
    #: header. Only ever set alongside :attr:`Status.RATE_LIMITED`, and None
    #: when the site sent no header — the caller then falls back to its own
    #: configured cooldown.
    retry_after: float | None = None

    @property
    def ok(self) -> bool:
        """True when nothing went wrong — including rows the site refused."""
        return self.status in (
            Status.DELETED,
            Status.SKIPPED_DRY_RUN,
            Status.SKIPPED,
        )


@dataclass
class BatchSummary:
    """Totals for one destructive run, shown when the worker finishes."""

    deleted: int = 0
    dry_run: int = 0
    skipped: int = 0
    failed: int = 0
    rate_limited: int = 0
    aborted: bool = False

    def add(self, result: ActionResult) -> None:
        if result.status is Status.DELETED:
            self.deleted += 1
        elif result.status is Status.SKIPPED_DRY_RUN:
            self.dry_run += 1
        elif result.status is Status.SKIPPED:
            self.skipped += 1
        elif result.status is Status.RATE_LIMITED:
            self.rate_limited += 1
        else:
            self.failed += 1
