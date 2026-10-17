"""Asks GitHub whether a newer release of Open Horned Rat is out, for the launcher's notice.

One anonymous HTTPS request to the GitHub REST API for the repository's latest release (prereleases and drafts
are never "latest"), made in the background when the launcher starts. Any failure (offline, rate limit, an
unexpected answer) simply means no notice. Setting ``OHR_NO_UPDATE_CHECK`` to any value turns the check off.
Stdlib only, like the rest of the launcher.
"""

import json
import os
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from whshr.version import is_newer_release, version

LATEST_RELEASE_API = "https://api.github.com/repos/pgrudzien12/openHornedRat/releases/latest"
RELEASES_PAGE = "https://github.com/pgrudzien12/openHornedRat/releases/latest"
DISABLE_ENV = "OHR_NO_UPDATE_CHECK"
TIMEOUT_SECONDS = 5

Fetch = Callable[[str, float], bytes]  # (url, timeout) -> response body


@dataclass(frozen=True)
class Release:
    tag: str  # e.g. "v1.1.0"
    url: str  # the release's web page

    @property
    def number(self) -> str:
        return self.tag.removeprefix("v")


def _fetch(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json", "User-Agent": f"open-horned-rat-launcher/{version()}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https URL
        return response.read()


def newer_release(current: str | None = None, fetch: Fetch = _fetch,
                  environ: Mapping[str, str] | None = None) -> Release | None:
    """The latest release when it is newer than ``current`` (this engine's version by default), else None."""
    environ = os.environ if environ is None else environ
    if environ.get(DISABLE_ENV):
        return None
    try:
        data: Any = json.loads(fetch(LATEST_RELEASE_API, TIMEOUT_SECONDS))
    except Exception:  # offline, rate-limited, blocked or malformed: no notice
        return None
    if not isinstance(data, dict):
        return None
    tag, url = data.get("tag_name"), data.get("html_url")  # pyright: ignore[reportUnknownMemberType]
    if not isinstance(tag, str) or data.get("draft") or data.get("prerelease"):  # pyright: ignore[reportUnknownMemberType]
        return None
    if not is_newer_release(tag, current if current is not None else version()):
        return None
    return Release(tag, url if isinstance(url, str) and url.startswith("https://") else RELEASES_PAGE)


def notice_text(release: Release) -> str:
    """The launcher's line for a newer release."""
    return f"Version {release.number} is out - click here"  # short enough for one line under the portrait
