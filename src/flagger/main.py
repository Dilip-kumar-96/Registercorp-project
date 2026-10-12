"""
main.py — Application entry point.

Startup sequence:
  1. Load config from .env
  2. Initialize SQLite database (wipe from previous session)
  3. Create per-session log file
  4. Initialize Outlook session via Playwright (extract cookies)
  5. Start Flask dashboard in background thread
  6. Open browser to dashboard
  7. If first launch: redirect to /setup (Setup Wizard handles the rest)
  8. Else: start bot engine and run
  9. Start system tray icon in main thread (blocking — runs until user exits)

Usage (development):
    cd src
    python -m flagger.main

Usage (production):
    Double-click FedExFlagger.exe
"""
import sys
import os

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import threading
import time
import webbrowser
from pathlib import Path

# Add src/ to path when running as a script directly
_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from flagger import config, database, session_logger, alerts, bot_engine
from flagger import outlook_module
from flagger.dashboard import app as dashboard_app
from flagger import tray_icon


def main():
    print("=" * 56)
    print("  FedEx Email Auto-Flagger — Registrar Corp")
    print("=" * 56)

    # ── 1. Load config ────────────────────────────────────────
    config.load()
    port = config.get_dashboard_port()
    dashboard_url = f"http://localhost:{port}"
    print(f"  Dashboard → {dashboard_url}")

    # ── 2. Initialize database (fresh session) ────────────────
    try:
        database.initialize()
        print("  Database   → initialized (fresh session)")
    except Exception as exc:
        _fatal(f"Cannot initialize database: {exc}")

    # ── 3. Create session log file ────────────────────────────
    try:
        log_path = session_logger.create()
        print(f"  Session log → {log_path}")
    except Exception as exc:
        _fatal(f"Cannot create session log: {exc}")

    # ── 4. Start Flask dashboard ──────────────────────────────
    try:
        dashboard_app.run_in_thread(port=port)
        print(f"  Flask      → running on port {port}")
    except Exception as exc:
        _fatal(f"Cannot start dashboard: {exc}")

    # ── 5. Open browser ───────────────────────────────────────
    dashboard_app.open_browser(port=port, delay=1.2)

    # ── 6. First launch check ─────────────────────────────────
    if config.is_first_launch():
        print("  First launch → Setup Wizard will open in browser")
        session_logger.log("info", "FIRST_LAUNCH", action="redirecting_to_setup_wizard")
        # The browser will open /setup automatically via the Flask redirect.
        # The Setup Wizard handles Outlook login and token entry.
        # Bot starts when user clicks "Start Bot" in the wizard.
        _wait_in_tray(dashboard_url)
        return

    # ── 7. Initialize Outlook session ─────────────────────────
    print("  Outlook    → connecting via Playwright…")
    try:
        outlook_module.initialize_session(
            mailbox_url=config.get_outlook_url(),
            browser_profile_dir=config.get_browser_profile_dir(),
        )
        print("  Outlook    → session active ✓")
        session_logger.log("info", "OUTLOOK_SESSION_ACTIVE")
    except outlook_module.OutlookSessionExpiredError:
        print("  Outlook    → session EXPIRED — open dashboard to re-login")
        session_logger.log("warning", "OUTLOOK_SESSION_EXPIRED_ON_STARTUP")
        alerts.outlook_session_expired()
        # Don't exit — bot can still start, user re-logins via dashboard
    except outlook_module.OutlookNetworkError as exc:
        print(f"  Outlook    → network error: {exc}")
        session_logger.log("error", "OUTLOOK_NETWORK_ON_STARTUP", error=str(exc))
        alerts.network_error("Outlook")

    # ── 8. Start bot engine ───────────────────────────────────
    if config.get_portal_token():
        bot_engine.start()
        print(f"  Bot engine → started (dry_run={config.is_dry_run()}) ✓")
    else:
        print("  Bot engine → waiting (no portal token — complete Setup Wizard)")

    print("=" * 56)
    print("  FedEx Flagger is running. Minimize this window.")
    print(f"  Open the dashboard: {dashboard_url}")
    print("  Right-click the 🚩 tray icon to Stop or Exit.")
    print("=" * 56)

    # ── 9. System tray (main thread — blocks until Exit) ──────
    _wait_in_tray(dashboard_url)


def _wait_in_tray(dashboard_url: str):
    """Start the system tray icon. Blocks the main thread until user clicks Exit."""
    try:
        tray_icon.start(dashboard_url=dashboard_url, engine_module=bot_engine)
    except KeyboardInterrupt:
        pass
    finally:
        print("\n  Shutting down…")
        if bot_engine.is_running():
            bot_engine.stop()
        print("  Goodbye.")
        sys.exit(0)


def _fatal(message: str):
    """Print a fatal error and exit."""
    print(f"\n  FATAL ERROR: {message}")
    print("  The application cannot start. Check the error above.")
    input("\n  Press Enter to exit…")
    sys.exit(1)


if __name__ == "__main__":
    main()
