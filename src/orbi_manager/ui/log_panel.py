"""Per-row status log shown under the table."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import QPlainTextEdit


class LogPanel(QPlainTextEdit):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(5000)
        self.setPlaceholderText("진행 상황이 여기에 표시됩니다.")

    def log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.appendPlainText(f"[{stamp}] {message}")
