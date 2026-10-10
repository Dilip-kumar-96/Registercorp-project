"""
tray_icon.py — Windows system tray icon using pystray.

Shows the bot's current status as a coloured dot in the system tray.
Right-click menu: Open Dashboard | Start/Stop Bot | Exit.

Colour coding:
  Green  (#10b981) — Bot running normally
  Red    (#ef4444) — Error / session expired / token expired
  Yellow (#f59e0b) — Paused / dry-run mode
  Grey   (#6b7280) — Stopped
"""
import threading
import webbrowser
from PIL import Image, ImageDraw

try:
    import pystray
    _PYSTRAY_AVAILABLE = True
except ImportError:
    _PYSTRAY_AVAILABLE = False

_icon_instance = None
_status_colour = (107, 114, 128)  # Grey — stopped


def _make_image(colour: tuple) -> Image.Image:
    """Create a 64×64 icon image with a filled circle."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Outer circle (flag red border)
    draw.ellipse([2, 2, 62, 62], fill=(30, 30, 30, 200))
    # Inner coloured dot
    draw.ellipse([10, 10, 54, 54], fill=colour + (255,))
    return img


def _build_menu(dashboard_url: str, engine_module):
    """Build the right-click context menu."""

    def open_dashboard(icon, item):
        webbrowser.open(dashboard_url)

    def toggle_bot(icon, item):
        if engine_module.is_running():
            engine_module.stop()
        else:
            engine_module.start()
        _refresh_icon(engine_module)

    def exit_app(icon, item):
        if engine_module.is_running():
            engine_module.stop()
        icon.stop()

    return pystray.Menu(
        pystray.MenuItem("📊 Open Dashboard", open_dashboard, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "⏹ Stop Bot",
            toggle_bot,
            visible=lambda item: engine_module.is_running(),
        ),
        pystray.MenuItem(
            "▶ Start Bot",
            toggle_bot,
            visible=lambda item: not engine_module.is_running(),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("✕ Exit", exit_app),
    )


def _refresh_icon(engine_module):
    """Update the icon colour based on the current bot status."""
    global _status_colour, _icon_instance

    status = engine_module.get_status()
    engine_status = status.get("status", "STOPPED")
    outlook = status.get("outlook_status", "UNKNOWN")
    active_alerts = status.get("has_critical_alerts", False)

    if engine_status == "STOPPED":
        colour = (107, 114, 128)   # Grey
    elif engine_status == "PAUSED" or active_alerts:
        colour = (239, 68, 68)     # Red
    elif status.get("dry_run"):
        colour = (245, 158, 11)    # Yellow
    elif outlook == "EXPIRED":
        colour = (239, 68, 68)     # Red
    else:
        colour = (16, 185, 129)    # Green

    _status_colour = colour
    if _icon_instance:
        _icon_instance.icon = _make_image(colour)


def start(dashboard_url: str, engine_module):
    """
    Start the system tray icon. Must be called from the MAIN THREAD on Windows.
    Blocks until the user selects Exit.
    """
    if not _PYSTRAY_AVAILABLE:
        # If pystray not available (e.g. Linux dev machine), just wait forever
        try:
            while True:
                import time; time.sleep(60)
        except KeyboardInterrupt:
            engine_module.stop()
        return

    global _icon_instance

    # Status refresh thread
    def _refresh_loop():
        import time
        while True:
            _refresh_icon(engine_module)
            time.sleep(5)

    threading.Thread(target=_refresh_loop, name="tray-refresh", daemon=True).start()

    _icon_instance = pystray.Icon(
        name="FedExFlagger",
        icon=_make_image(_status_colour),
        title="FedEx Flagger — Registrar Corp",
        menu=_build_menu(dashboard_url, engine_module),
    )
    _icon_instance.run()  # Blocks — this is the main thread's job on Windows
