"""Native GTK window hosting the read-only KYOCERA dashboard.

The window is a thin WebKit container around the same local HTTP dashboard as
``--web``.  GTK and WebKit are optional runtime dependencies: importing this
module never fails when they are absent, so the CLI and tests keep working on
headless systems.
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from .config_web import ConfigWorkbench
from .scan import ScanArtifact, ScanJobManager
from .web import DeviceRegistry, create_server

_DOWNLOAD_PATH_RE = re.compile(
    r"^/api/scans/([0-9a-f]{32})/files/([0-9]+)$"
)


class GuiUnavailable(RuntimeError):
    """Raised when GTK/WebKit cannot be loaded."""


def _load_gtk():
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        raise GuiUnavailable(
            "没有可用的图形会话；请使用 --web 在浏览器中打开"
        )
    try:
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("WebKit2", "4.1")
        from gi.repository import Gtk, WebKit2
    except (ImportError, ValueError) as exc:
        raise GuiUnavailable(
            "GTK3/WebKit2 不可用；请安装 gir1.2-gtk-3.0 和 "
            "gir1.2-webkit2-4.1，或改用 --web 在浏览器中打开"
        ) from exc
    return Gtk, WebKit2


def safe_download_filename(value: object) -> str:
    """Return a local basename suitable for a user download."""
    if not isinstance(value, str):
        return "kyocera-scan.bin"
    name = Path(value.replace("\\", "/")).name.strip()
    name = "".join(
        "_" if ord(character) < 32 or character in ("\x7f", "\x00") else character
        for character in name
    )
    if not name or name in {".", ".."}:
        return "kyocera-scan.bin"
    if len(name) > 180:
        suffix = Path(name).suffix[:20]
        name = name[: 180 - len(suffix)] + suffix
    return name


def download_destination(
    directory: Path,
    filename: str,
) -> tuple[int, Path]:
    """Create a unique destination exclusively and return its descriptor."""
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    safe_name = safe_download_filename(filename)
    stem = Path(safe_name).stem
    suffix = Path(safe_name).suffix
    for index in range(1000):
        candidate_name = (
            safe_name if index == 0 else f"{stem}-{index}{suffix}"
        )
        candidate = directory / candidate_name
        try:
            descriptor = os.open(
                candidate,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            continue
        return descriptor, candidate
    raise FileExistsError(f"cannot allocate a unique name for {safe_name}")


def save_download_artifact(
    artifact: ScanArtifact,
    directory: Path,
) -> Path:
    """Exclusively save one in-memory scan artifact."""
    descriptor, destination = download_destination(directory, artifact.filename)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(artifact.data)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        try:
            os.unlink(destination)
        except FileNotFoundError:
            pass
        raise
    return destination


def parse_download_request(payload: object) -> tuple[str, int, str]:
    """Validate the small native-download message sent by the page."""
    if not isinstance(payload, dict):
        raise ValueError("download request must be an object")
    url = payload.get("url")
    filename = payload.get("filename")
    if not isinstance(url, str) or not isinstance(filename, str):
        raise ValueError("download url and filename must be strings")
    parsed = urlsplit(url)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("download url must be a same-origin relative path")
    match = _DOWNLOAD_PATH_RE.fullmatch(parsed.path)
    if match is None:
        raise ValueError("invalid scan download url")
    return match.group(1), int(match.group(2)), safe_download_filename(filename)


def _message_payload(message: object) -> object:
    value = message
    getter = getattr(value, "get_js_value", None)
    if getter is not None:
        value = getter()
    as_json = getattr(value, "to_json", None)
    if as_json is None:
        raise ValueError("WebKit message has no JSON payload")
    return json.loads(as_json(0))


def _show_download_result(
    Gtk,
    window,
    title: str,
    detail: str,
    error: bool = False,
) -> bool:
    if not window.get_visible():
        return False
    dialog = Gtk.MessageDialog(
        transient_for=window,
        flags=0,
        message_type=Gtk.MessageType.ERROR if error else Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.OK,
        text=title,
    )
    dialog.format_secondary_text(detail)
    dialog.connect("response", lambda item, _response: item.destroy())
    dialog.show()
    return False


def _install_download_bridge(
    Gtk,
    GLib,
    content_manager,
    manager: ScanJobManager,
    window,
    *,
    downloads_directory: Path | None = None,
) -> None:
    directory = downloads_directory or Path.home() / "Downloads"

    def receive(_manager, message) -> None:
        try:
            job_id, index, _filename = parse_download_request(
                _message_payload(message)
            )
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            GLib.idle_add(
                _show_download_result,
                Gtk,
                window,
                "下载失败",
                str(exc),
                True,
            )
            return

        def worker() -> None:
            try:
                artifact = manager.output(job_id, index)
                destination = save_download_artifact(artifact, directory)
            except Exception as exc:
                GLib.idle_add(
                    _show_download_result,
                    Gtk,
                    window,
                    "下载失败",
                    f"{type(exc).__name__}: {exc}",
                    True,
                )
            else:
                GLib.idle_add(
                    _show_download_result,
                    Gtk,
                    window,
                    "扫描文件已下载",
                    str(destination),
                )

        threading.Thread(
            target=worker,
            name="kyocera-download",
            daemon=True,
        ).start()

    content_manager.register_script_message_handler("kyoceraDownload")
    content_manager.connect(
        "script-message-received::kyoceraDownload",
        receive,
    )


def run_gui(
    registry: DeviceRegistry,
    *,
    discover_fn: Callable[[], list] | None = None,
    config_workbench: ConfigWorkbench | None = None,
    push_scan_reader: Callable[[str], dict] | None = None,
    title: str = "KYOCERA 打印机",
) -> None:
    """Open the dashboard in a native window and block until it closes."""

    Gtk, WebKit2 = _load_gtk()
    from gi.repository import GLib

    manager = ScanJobManager()
    server = create_server(
        registry,
        bind="127.0.0.1",
        port=0,
        discover_fn=discover_fn,
        scan_manager=manager,
        config_workbench=config_workbench,
        push_scan_reader=push_scan_reader,
    )
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    window = Gtk.Window(title=title)
    window.set_default_size(1080, 780)
    window.set_size_request(720, 520)
    content_manager = WebKit2.UserContentManager()
    view = WebKit2.WebView.new_with_user_content_manager(content_manager)
    _install_download_bridge(
        Gtk,
        GLib,
        content_manager,
        manager,
        window,
    )
    settings = view.get_settings()
    settings.set_enable_javascript(True)
    settings.set_enable_developer_extras(False)
    window.add(view)
    window.connect("destroy", Gtk.main_quit)
    window.connect("key-press-event", lambda _w, event: _reload_on_f5(
        view, event
    ))
    window.show_all()
    view.load_uri(f"http://127.0.0.1:{port}/")

    try:
        Gtk.main()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


def _reload_on_f5(view, event) -> bool:
    # GDK_KEY_F5 == 0xFFC2; avoid importing Gdk just for one constant.
    if getattr(event, "keyval", None) == 0xFFC2:
        view.reload()
        return True
    return False


def main() -> int:
    """Entry point for the ``kyocera-gui`` console script."""

    import sys

    from .cli import main as cli_main

    return cli_main(["--gui", *sys.argv[1:]])
