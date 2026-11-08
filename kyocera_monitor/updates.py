"""Manual release update checks for the local Web/GUI."""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

DEFAULT_UPDATE_URL = (
    "https://github.com/yuannancheng/"
    "kyocera-client-tool-for-linux/releases/download/updater/update.json"
)
MAX_UPDATE_BYTES = 16 * 1024
DEFAULT_CACHE_SECONDS = 60.0
VERSION_RE = re.compile(
    r"^v?((?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))$"
)


class UpdateCheckError(RuntimeError):
    """Raised when the local version or remote update metadata is invalid."""


@dataclass(frozen=True)
class UpdateResult:
    current_version: str
    latest_version: str
    update_available: bool
    release_url: str
    checked_at: str
    cached: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "current_version": self.current_version,
            "latest_version": self.latest_version,
            "update_available": self.update_available,
            "release_url": self.release_url,
            "checked_at": self.checked_at,
            "cached": self.cached,
        }


def project_version_from_pyproject(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(
        r'(?ms)^\[project\]\s*$.*?^version\s*=\s*"([^"]+)"\s*$',
        text,
    )
    if match is None:
        return None
    version = match.group(1)
    return version if VERSION_RE.fullmatch(version) else None


def current_version() -> str:
    """Resolve the installed or source-tree package version."""

    source_version = project_version_from_pyproject(
        Path(__file__).resolve().parent.parent / "pyproject.toml"
    )
    if source_version is not None:
        return source_version

    try:
        from ._build_version import __version__ as build_version
    except ImportError:
        build_version = None
    if isinstance(build_version, str) and VERSION_RE.fullmatch(build_version):
        return build_version

    try:
        value = metadata.version("kyocera-monitor")
    except metadata.PackageNotFoundError:
        value = None
    if value and VERSION_RE.fullmatch(value):
        return value
    raise UpdateCheckError("cannot determine the installed project version")


def _version_key(version: str) -> tuple[int, int, int]:
    match = VERSION_RE.fullmatch(version.strip())
    if match is None:
        raise UpdateCheckError(f"invalid semantic version: {version!r}")
    return tuple(int(part) for part in match.group(1).split("."))


def is_newer_version(latest: str, current: str) -> bool:
    return _version_key(latest) > _version_key(current)


def _validated_release_url(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise UpdateCheckError("update metadata has no release URL")
    parsed = urlsplit(value.strip())
    if parsed.scheme != "https" or not parsed.hostname:
        raise UpdateCheckError("update release URL must use HTTPS")
    return value.strip()


def fetch_update_metadata(
    url: str,
    *,
    timeout: float = 5.0,
) -> tuple[str, str]:
    """Return ``(version, release_url)`` from the fixed update JSON asset."""

    parsed_url = urlsplit(url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
        raise UpdateCheckError("update metadata URL must use HTTP or HTTPS")
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "kyocera-monitor-update-check",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            if status == 404:
                raise UpdateCheckError("update metadata is not published")
            if status != 200:
                raise UpdateCheckError(
                    f"update metadata returned HTTP {status}"
                )
            payload = response.read(MAX_UPDATE_BYTES + 1)
    except UpdateCheckError:
        raise
    except Exception as exc:
        raise UpdateCheckError(
            f"{type(exc).__name__}: {exc}"
        ) from exc
    if len(payload) > MAX_UPDATE_BYTES:
        raise UpdateCheckError("update metadata is too large")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateCheckError("update metadata is not valid JSON") from exc
    if not isinstance(value, dict):
        raise UpdateCheckError("update metadata must be a JSON object")
    version = value.get("version")
    if not isinstance(version, str) or VERSION_RE.fullmatch(version) is None:
        raise UpdateCheckError("update metadata has an invalid version")
    release_url = _validated_release_url(value.get("htmlUrl"))
    return version.removeprefix("v"), release_url


class UpdateChecker:
    """Cache manual checks briefly without contacting the network at startup."""

    def __init__(
        self,
        *,
        current: str | None = None,
        url: str = DEFAULT_UPDATE_URL,
        cache_seconds: float = DEFAULT_CACHE_SECONDS,
        fetcher: Callable[[str], tuple[str, str]] = fetch_update_metadata,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ):
        self._current = (current or current_version()).removeprefix("v")
        if VERSION_RE.fullmatch(self._current) is None:
            raise UpdateCheckError(
                f"invalid current version: {self._current!r}"
            )
        self.url = url
        self.cache_seconds = max(0.0, float(cache_seconds))
        self._fetcher = fetcher
        self._clock = clock
        self._wall_clock = wall_clock
        self._lock = threading.Lock()
        self._cached: UpdateResult | None = None
        self._cached_at = 0.0

    @property
    def current(self) -> str:
        return self._current

    def check(self, *, force: bool = False) -> UpdateResult:
        with self._lock:
            now = self._clock()
            if (
                not force
                and self._cached is not None
                and now - self._cached_at < self.cache_seconds
                and self._cached.current_version == self._current
            ):
                return UpdateResult(
                    **{
                        **self._cached.to_dict(),
                        "cached": True,
                    }
                )
            try:
                latest, release_url = self._fetcher(self.url)
                available = is_newer_version(latest, self._current)
            except UpdateCheckError:
                raise
            except Exception as exc:
                raise UpdateCheckError(
                    f"{type(exc).__name__}: {exc}"
                ) from exc
            result = UpdateResult(
                current_version=self._current,
                latest_version=latest,
                update_available=available,
                release_url=release_url,
                checked_at=datetime.fromtimestamp(
                    self._wall_clock(),
                    tz=timezone.utc,
                ).isoformat(timespec="seconds"),
            )
            self._cached = result
            self._cached_at = now
            return result


UPDATE_RUNTIME_STYLE = """
<style>
  .version-check { margin-left: 0; font-variant-numeric: tabular-nums; }
  .version-check:disabled { cursor: wait; opacity: .65; }
  .version-check.available { border-color: #7fb18a; background: #edf8ef;
                             color: #194d20; font-weight: 600; }
  .update-overlay { position: fixed; inset: 0; z-index: 1100;
                    display: grid; place-items: center; padding: 18px;
                    background: rgba(15, 23, 30, .48); }
  .update-overlay[hidden] { display: none; }
  .update-dialog { width: min(430px, 100%); border-radius: 12px; padding: 18px;
                   background: #fff; color: #1b1f24;
                   box-shadow: 0 24px 70px rgba(10, 20, 30, .28); }
  .update-dialog h2 { margin: 0 0 10px; font-size: 1.16rem; }
  .update-dialog p { margin: 0; line-height: 1.55; }
  .update-actions { display: flex; justify-content: flex-end; gap: 8px;
                    margin-top: 18px; }
  .update-actions a, .update-actions button {
    padding: 7px 12px; border-radius: 8px; border: 1px solid #b9c1c9;
    background: #fff; color: inherit; font: inherit; text-decoration: none;
    cursor: pointer;
  }
  .update-actions a { border-color: #83a9c9; background: #edf5fb;
                      color: #174b74; font-weight: 600; }
  @media (prefers-color-scheme: dark) {
    .version-check.available { background: #1d3523; color: #d3f2d8;
                               border-color: #356943; }
    .update-dialog { background: #1c2228; color: #e7ebef; }
    .update-actions a, .update-actions button {
      background: #14191e; color: inherit; border-color: #3a444e;
    }
    .update-actions a { background: #203b50; color: #cce7ff;
                        border-color: #456b86; }
  }
</style>
"""


UPDATE_RUNTIME_SCRIPT = r"""
<script>
(() => {
  const button = document.getElementById("version-check");
  if (!button) return;
  const current = window.KYOCERA_VERSION || "";
  const cacheKey = "kyocera-update-check";
  const cacheTtl = 60 * 1000;
  let overlay = null;

  const label = (text) => {
    button.textContent = current ? `v${current} · ${text}` : text;
  };
  const setState = (state) => {
    button.disabled = state === "loading";
    button.classList.toggle(
      "available",
      state === "available"
    );
    if (state === "loading") label(t("正在检查…"));
    else if (state === "latest") label(t("已是最新"));
    else if (state === "available") label(t("发现新版本"));
    else if (state === "error") label(t("检查更新失败"));
    else label(t("检查更新"));
  };
  const closeDialog = () => {
    if (overlay) overlay.remove();
    overlay = null;
    button.focus();
  };
  const openDialog = (value) => {
    if (overlay) overlay.remove();
    overlay = document.createElement("div");
    overlay.className = "update-overlay";
    const dialog = document.createElement("section");
    dialog.className = "update-dialog";
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    const title = document.createElement("h2");
    title.textContent = t("发现新版本");
    const description = document.createElement("p");
    description.textContent = t(
      "发现新版本 v{latest}，当前版本 v{current}。",
      {
        latest: value.latest_version,
        current: value.current_version
      }
    );
    const actions = document.createElement("div");
    actions.className = "update-actions";
    const release = document.createElement("a");
    release.href = value.release_url;
    release.target = "_blank";
    release.rel = "noopener noreferrer";
    release.textContent = t("前往发布页");
    release.addEventListener("click", (event) => {
      const bridge = window.webkit?.messageHandlers?.kyoceraOpenUrl;
      if (!bridge) return;
      event.preventDefault();
      bridge.postMessage({url: value.release_url});
    });
    const close = document.createElement("button");
    close.type = "button";
    close.textContent = t("关闭");
    close.addEventListener("click", closeDialog);
    actions.append(release, close);
    dialog.append(title, description, actions);
    overlay.append(dialog);
    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) closeDialog();
    });
    overlay.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeDialog();
    });
    document.body.append(overlay);
    close.focus();
  };
  const apply = (value) => {
    if (value.update_available) {
      setState("available");
      openDialog(value);
    } else {
      setState("latest");
    }
  };
  const readCache = () => {
    try {
      const value = JSON.parse(localStorage.getItem(cacheKey) || "null");
      if (!value || value.current !== current) {
        localStorage.removeItem(cacheKey);
        return null;
      }
      if (Date.now() - Number(value.savedAt || 0) >= cacheTtl) return null;
      return value.result;
    } catch (_error) {
      return null;
    }
  };
  const writeCache = (value) => {
    try {
      localStorage.setItem(cacheKey, JSON.stringify({
        current,
        savedAt: Date.now(),
        result: value
      }));
    } catch (_error) {
      // The backend cache still prevents an update-check request storm.
    }
  };
  const check = async () => {
    if (button.disabled) return;
    const cached = readCache();
    if (cached) {
      apply(cached);
      return;
    }
    setState("loading");
    try {
      const response = await fetch("/api/update", {cache: "no-store"});
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || response.status);
      writeCache(payload);
      apply(payload);
    } catch (error) {
      setState("error");
      if (typeof showToast === "function") {
        showToast(t("检查更新失败：{error}", {error: String(error)}));
      }
    }
  };
  button.addEventListener("click", check);
  setState("idle");
})();
</script>
"""


def render_update_runtime(current: str) -> str:
    """Inject the shared version-check UI into one rendered page."""

    if VERSION_RE.fullmatch(current) is None:
        raise UpdateCheckError(f"invalid current version: {current!r}")
    version = json.dumps(current)
    return (
        UPDATE_RUNTIME_STYLE
        + f"<script>window.KYOCERA_VERSION={version};</script>\n"
        + UPDATE_RUNTIME_SCRIPT
    )
