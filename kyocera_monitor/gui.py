"""Native GTK window hosting the read-only KYOCERA dashboard.

The window is a thin WebKit container around the same local HTTP dashboard as
``--web``.  GTK and WebKit are optional runtime dependencies: importing this
module never fails when they are absent, so the CLI and tests keep working on
headless systems.
"""

from __future__ import annotations

import os
import threading
from typing import Callable

from .web import DeviceRegistry, create_server


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


def run_gui(
    registry: DeviceRegistry,
    *,
    discover_fn: Callable[[], list] | None = None,
    title: str = "KYOCERA 打印机",
) -> None:
    """Open the dashboard in a native window and block until it closes."""

    Gtk, WebKit2 = _load_gtk()
    server = create_server(registry, bind="127.0.0.1", port=0,
                           discover_fn=discover_fn)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    window = Gtk.Window(title=title)
    window.set_default_size(1080, 780)
    window.set_size_request(720, 520)
    view = WebKit2.WebView()
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
