"""Table model with a checkbox column.

Column 0 is the checkbox; the remaining columns come from the active
:class:`~orbi_manager.modes.ModeSpec`. Selection is capped at
``config.MAX_BATCH`` — attempting to exceed it leaves the row unchecked and
emits :attr:`RowTableModel.capReached` so the window can say why.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QFont

from .. import config
from ..models import Status
from ..modes import ModeSpec

CHECK_COL = 0


class RowTableModel(QAbstractTableModel):
    capReached = Signal(int)
    selectionChanged = Signal(int)

    def __init__(self, mode: ModeSpec, rows: Sequence | None = None) -> None:
        super().__init__()
        self._mode = mode
        self._rows: list = list(rows or [])
        self._checked: set[int] = set()
        self._status: dict[int, str] = {}

    # -- content ------------------------------------------------------------

    def set_mode(self, mode: ModeSpec) -> None:
        """Switch mode without discarding fetched rows or the current selection.

        All current modes share the same fetch source (``scraper.fetch_posts``)
        and the same row set, so a mode switch is purely a change of columns —
        keep both the rows and whatever is already checked.
        """
        self.beginResetModel()
        self._mode = mode
        self.endResetModel()

    def set_rows(self, rows: Sequence) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self._checked.clear()
        self._status.clear()
        self.endResetModel()
        self.selectionChanged.emit(0)

    def rows(self) -> list:
        return list(self._rows)

    def checked_rows(self) -> list:
        return [self._rows[i] for i in sorted(self._checked)]

    def mark_status(self, row_id: str, status: str) -> None:
        """Record the outcome of an action so the row can show it.

        A deleted row is dropped from the selection and its checkbox
        disabled — there is nothing left on the site to act on again.
        """
        for position, row in enumerate(self._rows):
            if row.id == row_id:
                self._status[position] = status
                if status == Status.DELETED.value:
                    self._checked.discard(position)
                left = self.index(position, 0)
                right = self.index(position, self.columnCount() - 1)
                self.dataChanged.emit(left, right, [])
                self.selectionChanged.emit(len(self._checked))
                return

    # -- Qt model interface -------------------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._mode.columns) + 1

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        if orientation is not Qt.Orientation.Horizontal:
            return None
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if section == CHECK_COL:
            return "선택"
        return self._mode.columns[section - 1].header

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        base = Qt.ItemFlag.ItemIsEnabled
        if index.column() == CHECK_COL:
            if self._status.get(index.row()) == Status.DELETED.value:
                return Qt.ItemFlag.NoItemFlags
            return base | Qt.ItemFlag.ItemIsUserCheckable
        return base

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]

        if index.column() == CHECK_COL:
            if role == Qt.ItemDataRole.CheckStateRole:
                checked = index.row() in self._checked
                return (
                    Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
                ).value
            return None

        if role == Qt.ItemDataRole.FontRole:
            if self._status.get(index.row()) == Status.DELETED.value:
                font = QFont()
                font.setStrikeOut(True)
                return font
            return None

        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            field = self._mode.columns[index.column() - 1].field
            if field == "index":
                status = self._status.get(index.row())
                position = str(index.row() + 1)
                return f"{position} · {status}" if status else position
            return str(getattr(row, field, ""))
        return None

    def setData(  # noqa: N802
        self,
        index: QModelIndex,
        value,
        role: int = Qt.ItemDataRole.EditRole,
    ) -> bool:
        if not index.isValid() or index.column() != CHECK_COL:
            return False
        if role != Qt.ItemDataRole.CheckStateRole:
            return False
        if self._status.get(index.row()) == Status.DELETED.value:
            return False

        wants_check = Qt.CheckState(value) == Qt.CheckState.Checked
        if wants_check:
            if len(self._checked) >= config.MAX_BATCH:
                self.capReached.emit(config.MAX_BATCH)
                return False
            self._checked.add(index.row())
        else:
            self._checked.discard(index.row())

        self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
        self.selectionChanged.emit(len(self._checked))
        return True

    # -- bulk selection -----------------------------------------------------

    def set_all_checked(self, checked: bool) -> None:
        self.beginResetModel()
        if not checked:
            self._checked.clear()
        else:
            selectable = [
                position
                for position in range(len(self._rows))
                if self._status.get(position) != Status.DELETED.value
            ]
            limit = min(len(selectable), config.MAX_BATCH)
            self._checked = set(selectable[:limit])
            if len(selectable) > config.MAX_BATCH:
                self.capReached.emit(config.MAX_BATCH)
        self.endResetModel()
        self.selectionChanged.emit(len(self._checked))
