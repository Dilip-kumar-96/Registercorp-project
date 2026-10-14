"""
session_logger.py — Per-session log file management.

Creates a new timestamped log file on every bot startup.
Each start/stop produces its own log file, making it easy to
track how long the bot ran and what it did.

Log file format: logs/session_YYYY-MM-DD_HH-MM-SS.log
"""
import logging
from datetime import datetime
from pathlib import Path
from . import config

_logger: logging.Logger | None = None
_log_file_path: Path | None = None
_session_start: datetime | None = None

_LOG_DIR = config.get_app_dir() / "logs"


def create():
    """Create a new session log file. Call once at bot startup."""
    global _logger, _log_file_path, _session_start

    _LOG_DIR.mkdir(exist_ok=True)
    _session_start = datetime.now()
    timestamp = _session_start.strftime("%Y-%m-%d_%H-%M-%S")
    _log_file_path = _LOG_DIR / f"session_{timestamp}.log"

    _logger = logging.getLogger(f"flagger.{timestamp}")
    _logger.setLevel(logging.DEBUG)
    _logger.propagate = False

    # File handler — full detail
    fh = logging.FileHandler(str(_log_file_path), encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)-5s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    _logger.addHandler(fh)

    # Console handler — INFO and above only
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S"
    ))
    _logger.addHandler(ch)

    _logger.info("SESSION_START log_file=%s", _log_file_path.name)
    return str(_log_file_path)


def log(level: str, event: str, **details):
    """Write a structured log entry.

    Args:
        level: 'debug', 'info', 'warning', 'error', 'critical'
        event: Short event name in UPPER_SNAKE_CASE (e.g. 'FLAGGED', 'CYCLE_END')
        **details: Additional key=value pairs appended to the log line
    """
    if not _logger:
        return
    detail_str = " ".join(f"{k}={v}" for k, v in details.items())
    msg = f"{event}  {detail_str}".rstrip()
    getattr(_logger, level.lower(), _logger.info)(msg)


def write_summary(flagged: int, failed: int, pending: int, errors: int):
    """Write session summary to the log file on shutdown."""
    if not _logger or not _session_start:
        return
    duration = datetime.now() - _session_start
    total_sec = int(duration.total_seconds())
    h, rem = divmod(total_sec, 3600)
    m, s = divmod(rem, 60)
    _logger.info("SESSION_END (user stopped)")
    _logger.info("DURATION: %dh %dm %ds", h, m, s)
    _logger.info(
        "SUMMARY: flagged=%d  failed=%d  pending=%d  errors=%d",
        flagged, failed, pending, errors
    )


def get_path() -> str | None:
    """Return the path to the current session log file."""
    return str(_log_file_path) if _log_file_path else None


def get_start_time() -> datetime | None:
    return _session_start


def get_duration_str() -> str:
    """Return formatted duration since session started."""
    if not _session_start:
        return "—"
    delta = datetime.now() - _session_start
    total_sec = int(delta.total_seconds())
    h, rem = divmod(total_sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m}m {s}s"
