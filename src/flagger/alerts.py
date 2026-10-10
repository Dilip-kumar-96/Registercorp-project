"""
alerts.py — Windows desktop notifications and in-memory alert store.

Notifications are sent via plyer (Windows toast notifications).
All alerts are also stored in memory so the dashboard can display them.
"""
import threading
from datetime import datetime

_alerts: list[dict] = []
_lock = threading.Lock()


def notify(title: str, message: str, urgency: str = "normal"):
    """Send a Windows desktop toast notification and store it for the dashboard.

    Args:
        title: Notification title (bold text)
        message: Notification body
        urgency: 'normal' or 'critical' (critical shows red badge on dashboard)
    """
    # Store for dashboard display
    with _lock:
        _alerts.append({
            "id": len(_alerts),
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "title": title,
            "message": message,
            "urgency": urgency,
            "dismissed": False,
        })
        # Keep at most 20 alerts in memory
        if len(_alerts) > 20:
            _alerts.pop(0)

    # Send Windows toast (non-blocking, failure is silently ignored)
    try:
        from plyer import notification as plyer_notif
        plyer_notif.notify(
            title=title,
            message=message,
            app_name="FedEx Flagger",
            timeout=10,
        )
    except Exception:
        pass


def get_active_alerts() -> list[dict]:
    """Return all non-dismissed alerts for the dashboard."""
    with _lock:
        return [a for a in _alerts if not a["dismissed"]]


def dismiss(alert_id: int):
    """Dismiss an alert by its ID."""
    with _lock:
        for alert in _alerts:
            if alert["id"] == alert_id:
                alert["dismissed"] = True
                break


def clear_all():
    """Clear all alerts (used on bot restart)."""
    with _lock:
        _alerts.clear()


# ── Predefined notification templates ────────────────────────────────────────

def portal_token_expired():
    notify(
        "FedEx Flagger — Portal Token Expired",
        "Open the dashboard at http://localhost:5000 and update your portal token.",
        urgency="critical",
    )


def outlook_session_expired():
    notify(
        "FedEx Flagger — Outlook Login Required",
        "Your Outlook session has expired. Open the dashboard and click Re-login.",
        urgency="critical",
    )


def bot_paused(reason: str):
    notify(
        "FedEx Flagger — Bot Paused",
        f"The bot has paused after repeated failures: {reason}\nCheck the dashboard.",
        urgency="critical",
    )


def network_error(service: str = "service"):
    notify(
        f"FedEx Flagger — {service} Unreachable",
        "Check your internet connection. The bot will retry automatically.",
        urgency="normal",
    )
