"""Background session thread.

Playwright's sync API binds its objects to the thread that created them, so
the browser, the derived httpx client and every job that touches them live on
one dedicated thread. The UI posts jobs onto a queue and receives Qt signals
back; it never blocks and never touches the network itself.
"""

from __future__ import annotations

import queue
import threading
import traceback
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from . import deleter, exporter
from .auth import AuthSession, LoginError
from .modes import ModeSpec
from .ratelimit import Cooldown


@dataclass
class _Job:
    run: Callable[[], None]
    name: str


class SessionThread(QThread):
    """Owns the logged-in session and runs one job at a time."""

    logged_in = Signal()
    login_failed = Signal(str)

    rows_ready = Signal(list)
    fetch_progress = Signal(int, int)  # rows so far, pages fetched

    row_done = Signal(str, str, str)  # id, status, message
    batch_progress = Signal(int, int)  # done, total
    cooldown_tick = Signal(int)  # seconds remaining
    batch_finished = Signal(object)  # BatchSummary

    export_done = Signal(list)  # list[str] paths
    failed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._jobs: queue.Queue[_Job | None] = queue.Queue()
        self._session = AuthSession()
        self._client = None
        self._cooldown: Cooldown | None = None
        self._stop = threading.Event()

    # -- thread loop --------------------------------------------------------

    def run(self) -> None:  # noqa: D102 - QThread entry point
        while True:
            job = self._jobs.get()
            if job is None:
                break
            # A stop applies to the job that was running when it was asked for,
            # never to the next one.
            self._stop.clear()
            self._cooldown = None
            try:
                job.run()
            except LoginError as err:
                self.login_failed.emit(str(err))
            except Exception as err:  # noqa: BLE001 - surface, never crash the thread
                self.failed.emit(f"{job.name} 실패: {err}")
                traceback.print_exc()
        self._session.close()

    def shutdown(self) -> None:
        self.request_stop()
        self._jobs.put(None)
        self.wait(5000)

    # -- job submission (called from the GUI thread) ------------------------

    def submit_login(self, user_id: str, password: str) -> None:
        def job() -> None:
            self._session.login_password(user_id, password)
            self._after_login()

        self._jobs.put(_Job(job, "로그인"))

    def submit_fetch(self, mode: ModeSpec) -> None:
        def job() -> None:
            rows = mode.fetch(
                self._require_client(),
                self.fetch_progress.emit,
                limit=mode.fetch_limit,
                should_stop=self._stop.is_set,
            )
            self.rows_ready.emit(list(rows))

        self._jobs.put(_Job(job, "목록 불러오기"))

    def submit_export(self, rows: Sequence, mode_key: str, out_dir: Path | None) -> None:
        def job() -> None:
            paths = exporter.export(rows, mode_key, out_dir)
            self.export_done.emit([str(path) for path in paths])

        self._jobs.put(_Job(job, "백업"))

    def submit_delete(
        self,
        rows: Sequence,
        mode: ModeSpec,
        dry_run: bool,
        cooldown_sec: int,
    ) -> None:
        if mode.delete_one is None:
            raise ValueError(f"{mode.key}는 삭제 모드가 아닙니다")

        def job() -> None:
            client = self._require_client()

            self._cooldown = Cooldown(cooldown_sec)
            # Closes the gap between the job being queued and the cooldown
            # existing: a stop asked for in that window must still land.
            if self._stop.is_set():
                self._cooldown.cancel()
            total = len(rows)
            done = 0

            def on_result(result) -> None:
                nonlocal done
                done += 1
                self.row_done.emit(result.id, result.status.value, result.message)
                self.batch_progress.emit(done, total)

            batch = deleter.run_batch(
                rows,
                lambda row: mode.delete_one(row, client, dry_run),
                dry_run=dry_run,
                cooldown=self._cooldown,
                on_result=on_result,
                on_cooldown_tick=self.cooldown_tick.emit,
            )
            self.batch_finished.emit(batch)

        self._jobs.put(_Job(job, "삭제"))

    def request_stop(self) -> None:
        """Ask the running job to stop at its next safe point.

        A fetch stops between list pages; a delete batch stops between rows,
        and an in-flight cooldown is interrupted so a 429 wait does not hold
        the stop for another minute. Nothing is ever cut off mid-request.
        """
        self._stop.set()
        if self._cooldown is not None:
            self._cooldown.cancel()

    # -- helpers ------------------------------------------------------------

    def _after_login(self) -> None:
        self._client = self._session.client
        self.logged_in.emit()

    def _require_client(self):
        if self._client is None:
            raise LoginError("로그인 먼저 하세요.")
        return self._client
