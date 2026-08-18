"""Main window: login panel, mode dropdown, table, action bar, log."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from .. import config, modes
from ..models import BatchSummary
from .confirm_dialog import ConfirmDeleteDialog
from .log_panel import LogPanel
from .table_model import RowTableModel
from ..worker import SessionThread


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("openORBItal — 로그인 & 타임라인 (모드별 테이블)")
        self.resize(1300, 640)

        self.session = SessionThread()
        self._wire_session()
        self.session.start()

        self._stop_requested = False
        self._backup_dir = config.default_backup_dir()
        self._model = RowTableModel(modes.MODES[0])
        self._model.capReached.connect(self._on_cap_reached)
        self._model.selectionChanged.connect(self._on_selection_changed)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.addWidget(self._build_login_panel())
        layout.addWidget(self._build_main_panel(), stretch=1)
        self.setCentralWidget(central)

        self._set_logged_in(False)

    # -- construction -------------------------------------------------------

    def _build_login_panel(self) -> QWidget:
        panel = QFrame()
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        panel.setFixedWidth(280)
        box = QVBoxLayout(panel)

        title = QLabel("openORBItal")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        box.addWidget(title)

        self.id_field = QLineEdit()
        self.id_field.setPlaceholderText("아이디")
        self.pw_field = QLineEdit()
        self.pw_field.setPlaceholderText("비밀번호")
        self.pw_field.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw_field.returnPressed.connect(self._on_login)
        box.addWidget(self.id_field)
        box.addWidget(self.pw_field)

        notice = QLabel(
            "아이디/비밀번호 및 세션 정보는 서버나 디스크 그 어디에도 저장되지 않습니다.\n"
            "창을 닫으면 로그인 상태가 즉시 파기되므로 매번 다시 로그인해야 합니다."
        )
        notice.setWordWrap(True)
        notice.setStyleSheet("color: gray; font-size: 11px;")
        box.addWidget(notice)

        self.login_button = QPushButton("로그인")
        self.login_button.clicked.connect(self._on_login)
        box.addWidget(self.login_button)

        self.status_label = QLabel("로그아웃 상태")
        self.status_label.setWordWrap(True)
        box.addWidget(self.status_label)

        box.addStretch(1)
        return panel

    def _build_main_panel(self) -> QWidget:
        panel = QWidget()
        box = QVBoxLayout(panel)

        # Mode row
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("모드:"))
        self.mode_combo = QComboBox()
        for spec in modes.MODES:
            self.mode_combo.addItem(spec.label, spec.key)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self.mode_combo)
        mode_row.addStretch(1)
        box.addLayout(mode_row)

        # Action row
        action_row = QHBoxLayout()
        self.fetch_button = QPushButton("불러오기")
        self.fetch_button.clicked.connect(self._on_fetch)
        action_row.addWidget(self.fetch_button)

        self.select_all_box = QCheckBox("모두 선택")
        self.select_all_box.toggled.connect(self._model_set_all)
        action_row.addWidget(self.select_all_box)

        self.action_button = QPushButton("선택 삭제")
        self.action_button.clicked.connect(self._on_action)
        self.action_button.setEnabled(False)
        action_row.addWidget(self.action_button)

        self.dry_run_box = QCheckBox("모의 실행 (dry-run)")
        self.dry_run_box.setChecked(False)
        self.dry_run_box.setToolTip("체크 상태에서는 실제 삭제 요청을 보내지 않습니다.")
        action_row.addWidget(self.dry_run_box)

        self.safe_mode_box = QCheckBox("안전 모드")
        self.safe_mode_box.setChecked(False)
        self.safe_mode_box.setToolTip(
            "불러오기·삭제 모두 이 앱이 원래 쓰던 고정 속도로 되돌립니다\n"
            f"(삭제 {config.SAFE_MODE_DELAY_SEC}초, 불러오기 "
            f"{config.LIST_SAFE_MODE_DELAY_SEC}초 간격, limit 파라미터 미사용).\n"
            f"기본값(해제)은 사이트가 429를 보내면 자동으로 느려지는 "
            "적응형 속도입니다."
        )
        action_row.addWidget(self.safe_mode_box)

        action_row.addWidget(QLabel("429 대기(초):"))
        self.cooldown_spin = QSpinBox()
        self.cooldown_spin.setRange(config.MIN_COOLDOWN_SEC, 600)
        self.cooldown_spin.setValue(config.DELETE_COOLDOWN_SEC)
        self.cooldown_spin.setToolTip(
            "429를 받았을 때 기다릴 시간입니다.\n"
            "사이트가 Retry-After 헤더로 직접 시간을 알려주면 그 값을 "
            "따르고, 이 값은 헤더가 없을 때만 쓰입니다."
        )
        action_row.addWidget(self.cooldown_spin)

        self.stop_button = QPushButton("중단")
        self.stop_button.clicked.connect(self._on_stop)
        self.stop_button.setEnabled(False)
        self.stop_button.setToolTip(
            "진행 중인 불러오기나 삭제를 다음 글에서 멈춥니다. "
            "이미 삭제된 글은 되돌아오지 않습니다."
        )
        action_row.addWidget(self.stop_button)

        action_row.addStretch(1)
        self.selection_label = QLabel("선택 0개")
        action_row.addWidget(self.selection_label)
        box.addLayout(action_row)

        hint = QLabel(
            f"※ 한번에 글 {config.MAX_FETCH_POSTS}개까지 불러옵니다, "
            f"삭제는 되돌릴수 없습니다"
        )
        hint.setStyleSheet("color: gray; font-size: 11px;")
        hint.setWordWrap(True)
        box.addWidget(hint)

        # Table
        self.table = QTableView()
        self.table.setModel(self._model)
        self.table.setSortingEnabled(False)
        self.table.verticalHeader().setVisible(False)
        # The checkbox column is the only selection that means anything, so the
        # view's own cell highlight is noise — turn it off.
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        box.addWidget(self.table, stretch=1)
        self._apply_column_widths()

        # Progress + log
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        box.addWidget(self.progress)

        self.cooldown_label = QLabel("")
        box.addWidget(self.cooldown_label)

        self.log_panel = LogPanel()
        self.log_panel.setFixedHeight(120)
        box.addWidget(self.log_panel)

        backup_row = QHBoxLayout()
        self.backup_label = QLabel(f"백업 폴더: {self._backup_dir}")
        backup_row.addWidget(self.backup_label, stretch=1)
        change_backup = QPushButton("백업 폴더 변경")
        change_backup.clicked.connect(self._on_change_backup_dir)
        backup_row.addWidget(change_backup)
        box.addLayout(backup_row)

        return panel

    def _wire_session(self) -> None:
        self.session.logged_in.connect(self._on_logged_in)
        self.session.login_failed.connect(self._on_login_failed)
        self.session.rows_ready.connect(self._on_rows_ready)
        self.session.fetch_progress.connect(self._on_fetch_progress)
        self.session.row_done.connect(self._on_row_done)
        self.session.batch_progress.connect(self._on_batch_progress)
        self.session.cooldown_tick.connect(self._on_cooldown_tick)
        self.session.batch_finished.connect(self._on_batch_finished)
        self.session.export_done.connect(self._on_export_done)
        self.session.failed.connect(self._on_failed)

    # -- helpers ------------------------------------------------------------

    @property
    def _mode(self):
        return modes.by_key(self.mode_combo.currentData())

    def _apply_column_widths(self) -> None:
        self.table.setColumnWidth(0, 60)
        header = self.table.horizontalHeader()
        for position, column in enumerate(self._mode.columns, start=1):
            self.table.setColumnWidth(position, column.width)
            resize_mode = (
                QHeaderView.ResizeMode.Stretch
                if column.field == "url"
                else QHeaderView.ResizeMode.Interactive
            )
            header.setSectionResizeMode(position, resize_mode)

    def _copy_column(self) -> int | None:
        for position, column in enumerate(self._mode.columns, start=1):
            if column.field == "copy":
                return position
        return None

    def _refresh_copy_buttons(self) -> None:
        column = self._copy_column()
        if column is None:
            return
        for row in range(self._model.rowCount()):
            button = QPushButton("복사")
            button.setFixedWidth(56)
            button.clicked.connect(lambda checked=False, r=row: self._on_copy_link(r))
            self.table.setIndexWidget(self._model.index(row, column), button)

    def _on_copy_link(self, row: int) -> None:
        rows = self._model.rows()
        if row >= len(rows):
            return
        url = getattr(rows[row], "url", "")
        if not url:
            return
        QGuiApplication.clipboard().setText(url)
        self.log_panel.log(f"링크 복사됨: {url}")

    def _set_logged_in(self, value: bool) -> None:
        self._logged_in = value
        self.login_button.setEnabled(not value)
        self.id_field.setEnabled(not value)
        self.pw_field.setEnabled(not value)
        self.fetch_button.setEnabled(value)
        self.status_label.setText("로그인됨" if value else "로그아웃 상태")

    def _set_busy(self, busy: bool, *, cancellable: bool = True) -> None:
        self.fetch_button.setEnabled(not busy and self._logged_in)
        self.action_button.setEnabled(not busy and self._action_allowed())
        self.mode_combo.setEnabled(not busy)
        # Enabled only for jobs that actually check for a stop; a backup writes
        # its files too quickly to interrupt.
        self.stop_button.setEnabled(busy and cancellable)
        self.progress.setVisible(busy)
        if busy:
            self._stop_requested = False

    def _action_allowed(self) -> bool:
        if not getattr(self, "_logged_in", False):
            return False
        if not self._model.checked_rows():
            return False
        return self._mode.destructive or self._mode.key.startswith("export")

    def _model_set_all(self, checked: bool) -> None:
        self._model.set_all_checked(checked)

    # -- slots: login -------------------------------------------------------

    def _on_login(self) -> None:
        user_id = self.id_field.text().strip()
        password = self.pw_field.text()
        if not user_id or not password:
            QMessageBox.warning(self, "입력 필요", "아이디와 비밀번호를 입력하세요.")
            return
        self.status_label.setText("로그인 중...")
        self.login_button.setEnabled(False)
        self.session.submit_login(user_id, password)
        self.pw_field.clear()

    def _on_logged_in(self) -> None:
        self._set_logged_in(True)
        self.log_panel.log("로그인 성공")

    def _on_login_failed(self, message: str) -> None:
        self._set_logged_in(False)
        self.log_panel.log(f"로그인 실패: {message}")
        QMessageBox.warning(self, "로그인 실패", message)

    # -- slots: fetch -------------------------------------------------------

    def _on_mode_changed(self) -> None:
        self._model.set_mode(self._mode)
        self._apply_column_widths()
        self._refresh_copy_buttons()
        self.action_button.setText(self._mode.action_label)
        self.action_button.setEnabled(self._action_allowed())
        self.dry_run_box.setEnabled(self._mode.destructive)

    def _on_fetch(self) -> None:
        self._set_busy(True)
        self.progress.setRange(0, 0)
        self.log_panel.log(f"{self._mode.label}: 목록 불러오는 중...")
        self.session.submit_fetch(self._mode, self.safe_mode_box.isChecked())

    def _on_fetch_progress(self, rows: int, pages: int) -> None:
        self.status_label.setText(f"{pages}페이지 / {rows}건")

    def _on_rows_ready(self, rows: list) -> None:
        self._model.set_rows(rows)
        self._refresh_copy_buttons()
        self.select_all_box.setChecked(False)
        self._set_busy(False)
        limit = self._mode.fetch_limit
        if self._stop_requested:
            self.log_panel.log(f"중단됨 — {len(rows)}건까지 불러왔습니다")
        elif len(rows) >= limit:
            self.log_panel.log(f"{len(rows)}건 불러옴 (한도 {limit}개에서 멈춤)")
        else:
            self.log_panel.log(f"{len(rows)}건 불러옴")

    # -- slots: actions -----------------------------------------------------

    def _on_selection_changed(self, count: int) -> None:
        self.selection_label.setText(f"선택 {count}개")
        self.action_button.setEnabled(self._action_allowed())

    def _on_cap_reached(self, cap: int) -> None:
        self.log_panel.log(f"선택 한도 {cap}개에 도달했습니다.")

    def _on_stop(self) -> None:
        self._stop_requested = True
        # One press is the whole request; leaving it live only invites a second
        # one that does nothing.
        self.stop_button.setEnabled(False)
        self.log_panel.log("중단 요청됨 — 진행 중인 글까지 마치고 멈춥니다")
        self.session.request_stop()

    def _on_change_backup_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "백업 폴더 선택", str(self._backup_dir)
        )
        if chosen:
            self._backup_dir = Path(chosen)
            self.backup_label.setText(f"백업 폴더: {chosen}")

    def _on_action(self) -> None:
        rows = self._model.checked_rows()
        if not rows:
            return

        if not self._mode.destructive:
            self._set_busy(True, cancellable=False)
            self.progress.setRange(0, 0)
            self.session.submit_export(rows, self._mode.key, self._backup_dir)
            return

        dry_run = self.dry_run_box.isChecked()
        if not dry_run:
            dialog = ConfirmDeleteDialog(len(rows), self)
            if dialog.exec() != ConfirmDeleteDialog.DialogCode.Accepted:
                self.log_panel.log("삭제 취소됨")
                return

        self._set_busy(True)
        self.progress.setRange(0, len(rows))
        self.progress.setValue(0)
        prefix = "모의 실행" if dry_run else "삭제"
        self.log_panel.log(f"{prefix} 시작: {len(rows)}건")
        self.session.submit_delete(
            rows,
            self._mode,
            dry_run,
            self.cooldown_spin.value(),
            self.safe_mode_box.isChecked(),
        )

    def _on_row_done(self, row_id: str, status: str, message: str) -> None:
        self._model.mark_status(row_id, status)
        self.log_panel.log(f"{row_id}: {status} {message}".rstrip())

    def _on_batch_progress(self, done: int, total: int) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(done)

    def _on_cooldown_tick(self, remaining: int) -> None:
        self.cooldown_label.setText(
            f"429 (요청 과다) — {remaining}초 후 같은 글을 다시 시도합니다"
            if remaining
            else ""
        )

    def _on_batch_finished(self, summary: BatchSummary) -> None:
        self._set_busy(False)
        self.cooldown_label.setText("")
        self.log_panel.log(
            f"완료 — 삭제 {summary.deleted}, 모의 {summary.dry_run}, "
            f"건너뜀 {summary.skipped}, 실패 {summary.failed}, "
            f"제한 {summary.rate_limited}"
            + (" (중단됨)" if summary.aborted else "")
        )

    def _on_export_done(self, paths: list) -> None:
        self._set_busy(False)
        for path in paths:
            self.log_panel.log(f"백업 저장: {path}")

    def _on_failed(self, message: str) -> None:
        self._set_busy(False)
        self.log_panel.log(message)
        QMessageBox.warning(self, "오류", message)

    # -- teardown -----------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self.session.shutdown()
        super().closeEvent(event)
