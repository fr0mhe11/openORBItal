"""Typed confirmation for irreversible deletions."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)


class ConfirmDeleteDialog(QDialog):
    """Requires the user to type the exact row count before deleting.

    Clicking through a yes/no box is too easy for an action that cannot be
    undone, so the count has to be typed by hand.
    """

    def __init__(self, count: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("삭제 확인")
        self._count = count

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                f"<b>{count}개</b>를 삭제합니다. 이 작업은 되돌릴 수 없습니다."
            )
        )
        layout.addWidget(QLabel(f"확인하려면 숫자 <b>{count}</b>를 입력하세요:"))

        self._field = QLineEdit()
        self._field.textChanged.connect(self._sync_button)
        layout.addWidget(self._field)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

        self._ok_button.setEnabled(False)
        self._ok_button.setText("삭제")

    @property
    def _ok_button(self):
        return self._buttons.button(QDialogButtonBox.StandardButton.Ok)

    def _sync_button(self, text: str) -> None:
        self._ok_button.setEnabled(text.strip() == str(self._count))
