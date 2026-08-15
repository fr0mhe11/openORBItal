"""JSON + CSV backup of the rows the user selected.

Backing up is a deliberate step, not an automatic one. Nothing here is called
from a delete batch: the only caller is the "백업 export" mode, which writes
whichever rows are checked. A backup taken before deleting has to be taken by
hand, and the README says so — do not let this docstring claim otherwise.

The CSV is written with a BOM so Excel opens Korean text correctly.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Protocol

from . import config


class Exportable(Protocol):
    def as_row(self) -> dict[str, str]: ...


def export(
    rows: Sequence[Exportable],
    mode: str,
    out_dir: Path | None = None,
) -> list[Path]:
    """Write ``rows`` as JSON and CSV. Returns the paths written.

    Raises on an empty selection rather than writing an empty file, so a
    backup that saved nothing cannot look like one that succeeded.
    """
    if not rows:
        raise ValueError("nothing to export")

    directory = out_dir or config.default_backup_dir()
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    stem = f"orbi_backup_{mode}_{stamp}"

    records = [row.as_row() for row in rows]

    json_path = directory / f"{stem}.json"
    json_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    csv_path = directory / f"{stem}.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)

    return [json_path, csv_path]
