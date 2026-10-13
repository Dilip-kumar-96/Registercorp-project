"""
bot_engine.py — The core 2-minute scan loop.

Orchestrates three phases every cycle:
  Phase 1 — FindItem: Discover new unflagged FedEx emails from Outlook
  Phase 2 — Portal:   Check tracking number statuses in bulk
  Phase 3 — UpdateItem: Flag all CONFIRMED emails

The engine runs in a background daemon thread.
All state is persisted to SQLite for the dashboard to read.
"""
import threading
import time
from datetime import datetime

from . import config, database, session_logger, alerts
from . import portal_module, outlook_module

_running = False
_paused = False
_thread: threading.Thread | None = None
_cycle_count = 0
_consecutive_failures = 0
_last_cycle_at: datetime | None = None
_last_cycle_duration: float | None = None
_status = "STOPPED"  # STOPPED | RUNNING | PAUSED | ERROR

MAX_FAILURES = 5  # Pause the bot after this many consecutive cycle failures
_lock = threading.Lock()


# ── Public API ────────────────────────────────────────────────────────────────

def get_status() -> dict:
    """Return a dict describing the current engine state (used by dashboard)."""
    with _lock:
        next_scan_in = None
        if _last_cycle_at and _running and not _paused:
            elapsed = (datetime.now() - _last_cycle_at).total_seconds()
            remaining = max(0, config.get_check_interval() - elapsed)
            next_scan_in = int(remaining)

        return {
            "status": _status,
            "running": _running,
            "paused": _paused,
            "cycle_count": _cycle_count,
            "consecutive_failures": _consecutive_failures,
            "last_cycle_at": _last_cycle_at.strftime("%H:%M:%S") if _last_cycle_at else None,
            "last_cycle_duration": _last_cycle_duration,
            "next_scan_in": next_scan_in,
            "dry_run": config.is_dry_run(),
            "outlook_status": outlook_module.get_session_status(),
            "session_duration": session_logger.get_duration_str(),
        }


def start():
    """Start the bot engine in a background thread."""
    global _running, _paused, _thread, _status, _consecutive_failures

    if _running:
        return

    _running = True
    _paused = False
    _status = "RUNNING"
    _consecutive_failures = 0

    _thread = threading.Thread(target=_loop, name="bot-engine", daemon=True)
    _thread.start()
    session_logger.log("info", "BOT_STARTED", dry_run=str(config.is_dry_run()))
    database.log_activity("info", "BOT_STARTED",
                          detail=f"dry_run={config.is_dry_run()}")


def stop():
    """Stop the bot engine gracefully."""
    global _running, _status

    _running = False
    _status = "STOPPED"

    counts = database.get_counts()
    session_logger.write_summary(
        flagged=counts.get("flagged", 0),
        failed=counts.get("failed", 0),
        pending=counts.get("pending", 0),
        errors=counts.get("error", 0),
    )
    session_logger.log("info", "BOT_STOPPED")
    database.log_activity("info", "BOT_STOPPED")


def resume():
    """Resume a paused bot."""
    global _paused, _status, _consecutive_failures
    _paused = False
    _consecutive_failures = 0
    _status = "RUNNING"
    session_logger.log("info", "BOT_RESUMED")
    database.log_activity("info", "BOT_RESUMED")


def is_running() -> bool:
    return _running and not _paused


# ── Internal loop ─────────────────────────────────────────────────────────────

def _loop():
    """Background thread: run scan cycles with configurable interval."""
    global _status

    while _running:
        if _paused:
            time.sleep(2)
            continue

        try:
            _run_cycle()
            _reset_failures()
        except Exception as exc:
            _record_failure(exc)

        # Wait for next cycle (check _running every second so stop() is responsive)
        interval = config.get_check_interval()
        waited = 0
        while waited < interval and _running and not _paused:
            time.sleep(1)
            waited += 1


def _reset_failures():
    global _consecutive_failures
    with _lock:
        _consecutive_failures = 0


def _record_failure(exc: Exception):
    global _consecutive_failures, _paused, _status

    with _lock:
        _consecutive_failures += 1
        count = _consecutive_failures

    session_logger.log("error", "CYCLE_EXCEPTION",
                       attempt=count, error=str(exc)[:200])
    database.log_activity("error", "CYCLE_ERROR", detail=str(exc)[:200])

    if count >= MAX_FAILURES:
        with _lock:
            _paused = True
            _status = "PAUSED"
        msg = f"{count} consecutive failures. Last: {exc}"
        alerts.bot_paused(msg)
        session_logger.log("critical", "BOT_AUTO_PAUSED", reason=msg[:200])
        database.log_activity("critical", "BOT_AUTO_PAUSED", detail=msg[:200])


# ── Cycle ─────────────────────────────────────────────────────────────────────

def _run_cycle():
    global _cycle_count, _last_cycle_at, _last_cycle_duration, _status

    with _lock:
        _cycle_count += 1
        cycle_num = _cycle_count

    cycle_start = datetime.now()
    session_logger.log("info", "CYCLE_START", cycle=cycle_num)

    # ── Phase 1: Discover emails ──────────────────────────────────────────────
    _phase1_discover()

    # ── Phase 2: Check portal statuses ───────────────────────────────────────
    _phase2_portal()

    # ── Phase 3: Flag confirmed emails ───────────────────────────────────────
    _phase3_flag()

    # ── Wrap up ───────────────────────────────────────────────────────────────
    with _lock:
        _last_cycle_at = datetime.now()
        _last_cycle_duration = round(
            (_last_cycle_at - cycle_start).total_seconds(), 1
        )

    counts = database.get_counts()
    session_logger.log(
        "info", "CYCLE_END",
        flagged=counts["flagged"],
        pending=counts["pending"],
        failed=counts["failed"],
        errors=counts["error"],
        duration=f"{_last_cycle_duration}s",
    )


def _phase1_discover():
    """FindItem: discover new unflagged FedEx emails from Outlook."""
    try:
        emails = outlook_module.find_unflagged_fedex_emails(config.get_sender_filter())
    except outlook_module.OutlookSessionExpiredError as exc:
        session_logger.log("error", "OUTLOOK_SESSION_EXPIRED", error=str(exc))
        alerts.outlook_session_expired()
        database.log_activity("error", "OUTLOOK_SESSION_EXPIRED",
                              detail="Re-login required via dashboard")
        raise  # Fail the cycle — cannot proceed without Outlook

    except outlook_module.OutlookNetworkError as exc:
        session_logger.log("error", "OUTLOOK_NETWORK_ERROR", phase=1, error=str(exc))
        alerts.network_error("Outlook")
        database.log_activity("error", "OUTLOOK_NETWORK_ERROR", detail=str(exc)[:150])
        raise

    new_count = 0
    skipped = 0

    for email in emails:
        tracking = email["tracking_number"]
        current = database.get_status(tracking)

        if current is None:
            database.add_email(tracking, email["item_id"], email["change_key"])
            session_logger.log("info", "DISCOVERED", tracking=tracking)
            database.log_activity("info", "DISCOVERED", tracking=tracking)
            new_count += 1
        elif current == "FAILED":
            skipped += 1
        # PENDING / CONFIRMED / FLAGGED / GONE — already tracked

    session_logger.log("info", "DISCOVER_DONE",
                       total=len(emails), new=new_count, skipped_failed=skipped)


def _phase2_portal():
    """Portal API: check statuses for all PENDING tracking numbers."""
    pending = database.get_pending()
    if not pending:
        session_logger.log("info", "PORTAL_SKIP", reason="no_pending_emails")
        return

    pending_tracking_numbers = [email["tracking_number"] for email in pending]

    try:
        status_map = portal_module.fetch_statuses(
            token=config.get_portal_token(),
            tracking_numbers=pending_tracking_numbers,
        )
    except portal_module.PortalTokenExpiredError as exc:
        session_logger.log("error", "PORTAL_TOKEN_EXPIRED", error=str(exc))
        alerts.portal_token_expired()
        database.log_activity("error", "PORTAL_TOKEN_EXPIRED",
                              detail="Update token via dashboard Settings")
        return  # Skip Phase 2, but continue to Phase 3

    except portal_module.PortalNetworkError as exc:
        session_logger.log("error", "PORTAL_NETWORK_ERROR", error=str(exc))
        alerts.network_error("Portal")
        database.log_activity("error", "PORTAL_NETWORK_ERROR", detail=str(exc)[:150])
        return  # Skip Phase 2, continue to Phase 3

    except portal_module.PortalParseError as exc:
        session_logger.log("error", "PORTAL_PARSE_ERROR", error=str(exc))
        database.log_activity("error", "PORTAL_PARSE_ERROR", detail=str(exc)[:150])
        return

    session_logger.log("info", "PORTAL_FETCHED", records=len(status_map))

    for email in pending:
        tracking = email["tracking_number"]
        portal_status = status_map.get(tracking)

        if portal_status == "CONFIRMED":
            database.update_status(tracking, "CONFIRMED", portal_status="CONFIRMED")
            session_logger.log("info", "CONFIRMED", tracking=tracking)
            database.log_activity("info", "CONFIRMED", tracking=tracking,
                                  detail="Ready to flag")

        elif portal_status == "FAILED":
            database.update_status(tracking, "FAILED", portal_status="FAILED")
            session_logger.log("info", "FAILED", tracking=tracking)
            database.log_activity("warning", "FAILED", tracking=tracking,
                                  detail="Not rechecking this session")

        elif portal_status in ("SUBMITTED", "PROCESSING"):
            database.update_status(tracking, "PENDING", portal_status=portal_status)
            session_logger.log("info", "STILL_PENDING", tracking=tracking,
                               portal_status=portal_status)
            database.log_activity("info", "PENDING", tracking=tracking,
                                  detail=portal_status)

        else:
            session_logger.log("debug", "NOT_IN_PORTAL", tracking=tracking)


def _phase3_flag():
    """UpdateItem: flag all CONFIRMED emails in Outlook."""
    confirmed = database.get_confirmed()
    if not confirmed:
        return

    dry_run = config.is_dry_run()

    for email in confirmed:
        tracking = email["tracking_number"]
        item_id = email["item_id"]
        change_key = email["change_key"]

        try:
            result = outlook_module.flag_email(item_id, change_key, dry_run=dry_run)
        except outlook_module.OutlookSessionExpiredError as exc:
            session_logger.log("error", "OUTLOOK_SESSION_EXPIRED", phase=3, error=str(exc))
            alerts.outlook_session_expired()
            database.log_activity("error", "OUTLOOK_SESSION_EXPIRED")
            raise  # Fail the cycle

        except outlook_module.OutlookNetworkError as exc:
            session_logger.log("error", "OUTLOOK_NETWORK_ERROR", phase=3,
                               tracking=tracking, error=str(exc))
            # Leave as CONFIRMED — will retry next cycle
            continue

        if result["success"]:
            if not dry_run:
                # Only mark FLAGGED in DB after a real flag (not dry run).
                # Dry run must leave status as CONFIRMED so the next live cycle
                # can actually perform the flag.
                database.update_status(tracking, "FLAGGED")
                if result.get("new_change_key"):
                    database.update_change_key(tracking, result["new_change_key"])
            else:
                # Dry run: refresh ChangeKey from Outlook so it stays fresh
                # for when the real flag runs later.
                fresh_ck = outlook_module.get_item_change_key(item_id)
                if fresh_ck and fresh_ck != change_key:
                    database.update_change_key(tracking, fresh_ck)

            label = "DRY_FLAGGED" if dry_run else "FLAGGED"
            session_logger.log("info", label, tracking=tracking)
            database.log_activity(
                "info",
                "DRY_RUN_WOULD_FLAG" if dry_run else "FLAGGED",
                tracking=tracking,
                detail="(dry run)" if dry_run else None,
            )

        else:
            error_code = result.get("error_code", "")

            if error_code == "ErrorItemNotFound":
                database.update_status(tracking, "GONE")
                session_logger.log("warning", "EMAIL_GONE", tracking=tracking)
                database.log_activity("warning", "EMAIL_GONE", tracking=tracking,
                                      detail="Deleted before flagging")

            elif error_code in ("ErrorChangeKeyRequired", "ErrorIrresolvableConflict"):
                # ChangeKey is stale — either someone else modified the email
                # (ErrorChangeKeyRequired) or there was a sync conflict
                # (ErrorIrresolvableConflict). Both are fixed the same way:
                # fetch the fresh ChangeKey via GetItem and retry the flag.
                session_logger.log("warning", "CHANGEKEY_MISMATCH",
                                   tracking=tracking, reason=error_code)
                new_ck = outlook_module.get_item_change_key(item_id)
                if new_ck:
                    retry = outlook_module.flag_email(item_id, new_ck, dry_run=dry_run)
                    if retry["success"]:
                        if not dry_run:
                            database.update_status(tracking, "FLAGGED")
                            database.update_change_key(
                                tracking, retry.get("new_change_key", new_ck)
                            )
                        else:
                            database.update_change_key(tracking, new_ck)
                        label = "FLAGGED_AFTER_RETRY" if not dry_run else "DRY_FLAGGED_AFTER_RETRY"
                        session_logger.log("info", label, tracking=tracking)
                        database.log_activity("info", "FLAGGED" if not dry_run else "DRY_RUN_WOULD_FLAG",
                                              tracking=tracking,
                                              detail="After ChangeKey refresh")
                    else:
                        _mark_error(tracking, f"Retry failed: {retry.get('error_code')}")
                else:
                    _mark_error(tracking, "Could not fetch fresh ChangeKey")

            else:
                _mark_error(tracking, error_code or "UnknownError")


def _mark_error(tracking: str, reason: str):
    database.update_status(tracking, "ERROR", error_message=reason)
    session_logger.log("error", "FLAG_ERROR", tracking=tracking, reason=reason)
    database.log_activity("error", "FLAG_ERROR", tracking=tracking, detail=reason)
