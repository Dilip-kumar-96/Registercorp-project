"""
config.py — Configuration management.

Reads and writes settings via the .env file.
Users interact with settings through the dashboard UI only —
they never need to edit .env manually.
"""
import os
from pathlib import Path
from dotenv import load_dotenv, set_key

# Path to .env file — always relative to the project root (one level above src/)
_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = _ROOT / ".env"


def load():
    """Load (or reload) all settings from .env into environment variables."""
    if ENV_PATH.exists():
        load_dotenv(str(ENV_PATH), override=True)
    else:
        # Create empty .env from .env.example if it doesn't exist
        example = _ROOT / ".env.example"
        if example.exists():
            ENV_PATH.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
            load_dotenv(str(ENV_PATH), override=True)


def is_first_launch() -> bool:
    """True if the portal token is missing — triggers Setup Wizard."""
    return not os.getenv("PORTAL_API_TOKEN", "").strip()


# ── Getters ──────────────────────────────────────────────────────────────────

def get_portal_token() -> str:
    return os.getenv("PORTAL_API_TOKEN", "").strip()

def get_outlook_url() -> str:
    return os.getenv("OUTLOOK_MAILBOX_URL",
                     "https://outlook.cloud.microsoft/mail/pn@registrarcorp.com/")

def get_sender_filter() -> str:
    return os.getenv("SENDER_FILTER", "myfda@registrarcorp.com")

def get_check_interval() -> int:
    return int(os.getenv("CHECK_INTERVAL_SECONDS", "120"))

def get_api_date_range_days() -> int:
    return int(os.getenv("API_DATE_RANGE_DAYS", "2"))

def get_dashboard_port() -> int:
    return int(os.getenv("DASHBOARD_PORT", "5000"))

def is_dry_run() -> bool:
    return os.getenv("DRY_RUN", "true").lower() in ("true", "1", "yes")

def get_browser_profile_dir() -> str:
    raw = os.getenv("BROWSER_PROFILE_DIR", "./browser_profile")
    # Resolve relative paths against project root
    path = Path(raw)
    if not path.is_absolute():
        path = _ROOT / raw
    return str(path)

def is_auto_start_windows() -> bool:
    return os.getenv("AUTO_START_WINDOWS", "false").lower() in ("true", "1", "yes")


# ── Setters (write to .env and hot-reload) ───────────────────────────────────

def _write(key: str, value: str):
    """Write a setting to .env and reload into the current process."""
    if not ENV_PATH.exists():
        ENV_PATH.touch()
    set_key(str(ENV_PATH), key, value)
    load()


def update_portal_token(token: str):
    _write("PORTAL_API_TOKEN", token.strip())

def update_dry_run(enabled: bool):
    _write("DRY_RUN", "true" if enabled else "false")

def update_check_interval(seconds: int):
    _write("CHECK_INTERVAL_SECONDS", str(max(30, int(seconds))))

def update_api_date_range(days: int):
    _write("API_DATE_RANGE_DAYS", str(max(1, int(days))))

def update_auto_start_windows(enabled: bool):
    _write("AUTO_START_WINDOWS", "true" if enabled else "false")
    _apply_windows_auto_start(enabled)


def _apply_windows_auto_start(enabled: bool):
    """Add or remove the bot from Windows startup via the registry."""
    import sys
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "FedExFlagger"
        exe_path = sys.executable  # Points to the EXE when packaged

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        if enabled:
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, f'"{exe_path}"')
        else:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception:
        pass  # Non-critical — registry access may fail in some environments
