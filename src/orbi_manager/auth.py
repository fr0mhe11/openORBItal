"""Login and session handling.

:meth:`AuthSession.login_password` posts a plain HTTP request to
``login.orbi.kr/login`` with ``username`` / ``password``, exactly the request
the site's own form sends. The session lives in one :class:`httpx.Client`.

Nothing is persisted. Credentials and session cookies live in memory for the
lifetime of the process and are gone when it exits, so every run starts from a
fresh login.
"""

from __future__ import annotations

from types import TracebackType

import httpx

from . import config, selectors

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)
LOGIN_POST_URL = "https://login.orbi.kr/login"


class LoginError(RuntimeError):
    """Login did not complete — wrong credentials, captcha, or timeout."""


class AuthSession:
    """Owns the HTTP session used for the login and every request after it."""

    def __init__(self) -> None:
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Referer": config.SITE},
            timeout=config.HTTP_TIMEOUT_SEC,
            follow_redirects=True,
        )
        self._logged_in = False

    # -- lifecycle ----------------------------------------------------------

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> AuthSession:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # -- login paths --------------------------------------------------------

    def login_password(self, user_id: str, password: str) -> None:
        """Post the login form directly. Raises :class:`LoginError` on failure."""
        try:
            response = self._client.post(
                LOGIN_POST_URL,
                data={
                    selectors.LOGIN_FIELD_RETURN_URL: f"{config.SITE}/",
                    selectors.LOGIN_FIELD_ID: user_id,
                    selectors.LOGIN_FIELD_PASSWORD: password,
                },
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": f"{LOGIN_POST_URL}?url=https%3A//orbi.kr/",
                },
            )
        except httpx.HTTPError as err:
            raise LoginError(f"로그인 요청 실패: {err}") from err

        if response.status_code >= 400:
            raise LoginError(self._login_error_text(response))
        if not self.verify():
            raise LoginError(
                "로그인에 실패했습니다 (아이디/비밀번호 확인, 또는 캡차·2단계 인증)."
            )

    @staticmethod
    def _login_error_text(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return f"로그인 실패 (HTTP {response.status_code})"
        message = payload.get("message") if isinstance(payload, dict) else None
        return message or f"로그인 실패 (HTTP {response.status_code})"

    # -- session ------------------------------------------------------------

    def verify(self) -> bool:
        """True when the HTTP session is actually logged in."""
        from .scraper import ScrapeError, current_user_id

        try:
            current_user_id(self._client)
        except ScrapeError:
            self._logged_in = False
            return False
        self._logged_in = True
        return True

    @property
    def client(self) -> httpx.Client:
        if not self._logged_in:
            raise LoginError("로그인 먼저 하세요.")
        return self._client
