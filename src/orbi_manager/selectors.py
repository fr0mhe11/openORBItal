"""Every CSS selector and URL template lives here.

When orbi.kr changes its markup, this is the only file that should need
editing — and `tests/test_parsers.py` turns such a change into a fast test
failure instead of a silent mis-parse.

All values below are confirmed against captures taken by `scripts/recon.py`
and against the site's own JS bundle (`s3.orbi.kr/assets/orbi-app.pc.js`).
"""

from __future__ import annotations

import re

# --- Login ------------------------------------------------------------------

#: The login form posts these three fields to https://login.orbi.kr/login
#: with `X-Requested-With: XMLHttpRequest`.
LOGIN_FIELD_ID = "username"
LOGIN_FIELD_PASSWORD = "password"
LOGIN_FIELD_RETURN_URL = "url"

#: The password box is the anchor: the id field is the text input before it.
PASSWORD_INPUT = "input[type=password]"
ID_INPUT_CANDIDATES = (
    "input[name=username]",
    "input[name=id]",
    "input[name=email]",
    "input[type=text]",
)
SUBMIT_CANDIDATES = (
    "button[type=submit]",
    "input[type=submit]",
    "form button",
)

#: A logged-in page pushes the viewer's own id into the GTM data layer.
OWN_USER_ID_RE = re.compile(r"user_id:\s*[\"'](\d+)[\"']")
#: Fallback: the sidebar member box links to the viewer's own profile.
OWN_USER_ID_NODE = "div.member-box a.nickname"
OWN_USER_ID_NODE_ATTR = "imin"

# --- My content lists -------------------------------------------------------

#: The site's own search (`?type=imin&q=<uid>`) silently drops posts an admin
#: has "모어보기 밴"'d — they're excluded from the search index, but still
#: show on the member's own profile. The profile's "활동" tab loads its list
#: from this JSON endpoint (confirmed via `scripts/recon_profile_api.py`),
#: which is unaffected by that ban, so it — not search — is the source of
#: truth for "every post this member wrote". Cursor-paginated: each response
#: carries the offset to pass for the next page.
TIMELINE_URL = "https://orbi.kr/api/v1/user/{uid}/timeline?offset={offset}"
#: The site's own JS sends no page-size parameter and the server's default is
#: 10 posts per response (see `scripts/recon_out/06_profile_api_calls.json`),
#: so `limit` is a guess — one worth making, because a bigger page means
#: *fewer* requests for the same list, not faster ones. `scraper` sends it
#: once and drops it for the rest of the walk if the server refuses it.
TIMELINE_URL_SIZED = TIMELINE_URL + "&limit={limit}"

# --- Ids --------------------------------------------------------------------

#: Post links look like /00079186801/url-encoded-title (ids are zero-padded to
#: 11 characters in URLs, but the delete endpoint takes the unpadded number).
POST_ID_RE = re.compile(r"/(\d{8,})(?:/|$|\?)")


def post_id_from_url(url: str) -> str | None:
    """Extract the zero-padded post id from a post URL, or None."""
    match = POST_ID_RE.search(url)
    return match.group(1) if match else None


def unpadded(post_id: str) -> str:
    """`00079187183` -> `79187183`, the form the delete endpoints expect."""
    return str(int(post_id))


# --- Deletion ---------------------------------------------------------------
#
# From the site's own AngularJS code:
#   deletePost: window.confirm(...) && httpUnited.delete('/delete/79187183')
#
# `httpUnited.delete` is named delete but its body is `$http.post(url)`, so
# deleting a post is an HTTP POST; sending a real DELETE to /delete/{id}
# answers 405. No CSRF token; the session cookie is the only credential.

DELETE_POST_URL = "https://orbi.kr/delete/{post_id}"
DELETE_POST_METHOD = "POST"
