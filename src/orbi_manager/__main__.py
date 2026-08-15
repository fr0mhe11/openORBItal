"""Entry point.

    python -m orbi_manager          # GUI
    python -m orbi_manager --cli    # headless smoke test of the scraper
"""

from __future__ import annotations

import argparse
import getpass
import sys


def _run_cli() -> int:
    from . import scraper
    from .auth import AuthSession, LoginError

    user_id = input("아이디: ").strip()
    session = AuthSession()
    try:
        session.login_password(user_id, getpass.getpass("비밀번호: "))
    except LoginError as err:
        print(f"로그인 실패: {err}", file=sys.stderr)
        session.close()
        return 1

    try:
        client = session.client
        rows = scraper.fetch_posts(
            client, lambda total, page: print(f"  {page}페이지 / {total}건")
        )
        for index, row in enumerate(rows, start=1):
            print(f"{index:4d}  {row.id}  {row.title[:60]}")
        print(f"총 {len(rows)}건")
    except Exception as err:  # noqa: BLE001 - CLI surface
        print(f"실패: {err}", file=sys.stderr)
        return 1
    finally:
        session.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="orbi-manager")
    parser.add_argument(
        "--cli",
        action="store_true",
        help="GUI 없이 목록만 출력 (스크레이퍼 점검용)",
    )
    args = parser.parse_args()

    if args.cli:
        return _run_cli()

    from PySide6.QtWidgets import QApplication

    from .ui.main_window import MainWindow

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
