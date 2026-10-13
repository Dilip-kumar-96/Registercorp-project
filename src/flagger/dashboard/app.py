"""
dashboard/app.py — Flask web dashboard.

Runs in a background thread. Serves the local UI at http://localhost:5000.
All bot management (start/stop, token update, re-login, settings) is done here.

Routes:
  GET  /                  Main dashboard (or redirect to /setup on first launch)
  GET  /setup             First-launch setup wizard
  GET  /settings          Settings page
  GET  /api/status        JSON: bot + system status
  GET  /api/activity      JSON: recent activity log
  GET  /api/alerts        JSON: active desktop alerts
  POST /api/token/test    Test a portal token without saving
  POST /api/token/save    Save portal token + hot-reload
  POST /api/bot/start     Start the bot engine
  POST /api/bot/stop      Stop the bot engine
  POST /api/bot/resume    Resume a paused bot
  POST /api/relogin       Trigger Playwright Outlook re-login
  POST /api/settings      Save settings to .env
  POST /api/alerts/dismiss Dismiss an alert by ID
"""
import threading
import webbrowser
from flask import Flask, jsonify, redirect, render_template, request, url_for

from .. import alerts as alert_store
from .. import bot_engine, config, database, outlook_module, portal_module, session_logger

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = "flagger-local-only-no-auth-needed"


# ── Page routes ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if config.is_first_launch():
        return redirect(url_for("setup"))
    return render_template("index.html")


@app.route("/setup")
def setup():
    return render_template("setup.html")


@app.route("/settings")
def settings():
    return render_template(
        "settings.html",
        check_interval=config.get_check_interval(),
        date_range=config.get_api_date_range_days(),
        dry_run=config.is_dry_run(),
        auto_start=config.is_auto_start_windows(),
        dashboard_port=config.get_dashboard_port(),
    )


# ── Status API ────────────────────────────────────────────────────────────────

@app.route("/api/status")
def api_status():
    engine = bot_engine.get_status()
    counts = database.get_counts()
    active_alerts = alert_store.get_active_alerts()

    return jsonify({
        "engine": engine,
        "counts": counts,
        "alerts": active_alerts,
        "has_critical_alerts": any(
            a["urgency"] == "critical" for a in active_alerts
        ),
        "portal_token_set": bool(config.get_portal_token()),
        "outlook_status": outlook_module.get_session_status(),
        "dry_run": config.is_dry_run(),
        "session_log": session_logger.get_path(),
    })


@app.route("/api/activity")
def api_activity():
    return jsonify(database.get_activity(limit=50))


@app.route("/api/alerts")
def api_alerts():
    return jsonify(alert_store.get_active_alerts())


# ── Token management ──────────────────────────────────────────────────────────

@app.route("/api/token/test", methods=["POST"])
def api_token_test():
    token = (request.json or {}).get("token", "").strip()
    if not token:
        return jsonify({"valid": False, "message": "Token cannot be empty."})
    valid, message = portal_module.test_token(token)
    return jsonify({"valid": valid, "message": message})


@app.route("/api/token/save", methods=["POST"])
def api_token_save():
    token = (request.json or {}).get("token", "").strip()
    if not token:
        return jsonify({"success": False, "message": "Token cannot be empty."})
    try:
        config.update_portal_token(token)
        return jsonify({"success": True, "message": "Token saved and applied."})
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 500


# ── Bot control ───────────────────────────────────────────────────────────────

@app.route("/api/bot/start", methods=["POST"])
def api_bot_start():
    try:
        bot_engine.start()
        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 500


@app.route("/api/bot/stop", methods=["POST"])
def api_bot_stop():
    try:
        bot_engine.stop()
        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 500


@app.route("/api/bot/resume", methods=["POST"])
def api_bot_resume():
    try:
        bot_engine.resume()
        return jsonify({"success": True})
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 500


# ── Outlook re-login ──────────────────────────────────────────────────────────

@app.route("/api/relogin", methods=["POST"])
def api_relogin():
    """Trigger Playwright to re-login to Outlook and refresh session cookies."""
    def _do_relogin():
        try:
            outlook_module.initialize_session(
                config.get_outlook_url(),
                config.get_browser_profile_dir(),
            )
            database.log_activity("info", "OUTLOOK_RELOGIN_SUCCESS",
                                  detail="Session refreshed via dashboard")
            session_logger.log("info", "OUTLOOK_RELOGIN_SUCCESS")
            # Resume bot if it was paused for session expiry
            if bot_engine.get_status()["paused"]:
                bot_engine.resume()
        except Exception as exc:
            database.log_activity("error", "OUTLOOK_RELOGIN_FAILED", detail=str(exc))
            session_logger.log("error", "OUTLOOK_RELOGIN_FAILED", error=str(exc))

    threading.Thread(target=_do_relogin, name="relogin", daemon=True).start()
    return jsonify({"success": True, "message": "Re-login started. A browser window will open."})


# ── Settings ──────────────────────────────────────────────────────────────────

@app.route("/api/settings", methods=["POST"])
def api_settings():
    data = request.json or {}
    try:
        if "check_interval" in data:
            config.update_check_interval(int(data["check_interval"]))
        if "date_range" in data:
            config.update_api_date_range(int(data["date_range"]))
        if "dry_run" in data:
            config.update_dry_run(bool(data["dry_run"]))
        if "auto_start" in data:
            config.update_auto_start_windows(bool(data["auto_start"]))
        return jsonify({"success": True, "message": "Settings saved."})
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 500


# ── Alert management ──────────────────────────────────────────────────────────

@app.route("/api/alerts/dismiss", methods=["POST"])
def api_alerts_dismiss():
    alert_id = (request.json or {}).get("id")
    if alert_id is not None:
        alert_store.dismiss(int(alert_id))
    return jsonify({"success": True})


# ── Manual Outlook session (paste from browser) ───────────────────────────────

@app.route("/api/outlook/session/test", methods=["POST"])
def api_outlook_session_test():
    """
    Test a manually-entered Bearer token + OWA Canary by making a live
    FindItem call against the OWA API. Does NOT save anything.
    """
    data = request.json or {}
    bearer = data.get("bearer_token", "").strip()
    canary = data.get("owa_canary", "").strip()

    if not bearer:
        return jsonify({"valid": False, "message": "Bearer token cannot be empty."})

    if not bearer.startswith("Bearer "):
        bearer = f"Bearer {bearer}"

    valid, message = outlook_module.test_manual_session(bearer, canary)
    return jsonify({"valid": valid, "message": message})


@app.route("/api/outlook/session/save", methods=["POST"])
def api_outlook_session_save():
    """
    Save manually-entered Bearer token + OWA Canary.
    Applies immediately to the running bot without restart.
    """
    data = request.json or {}
    bearer = data.get("bearer_token", "").strip()
    canary = data.get("owa_canary", "").strip()

    if not bearer:
        return jsonify({"success": False, "message": "Bearer token cannot be empty."})

    if not bearer.startswith("Bearer "):
        bearer = f"Bearer {bearer}"

    try:
        outlook_module.apply_manual_session(bearer, canary)
        session_logger.log("info", "OUTLOOK_MANUAL_SESSION_APPLIED")
        database.log_activity("info", "OUTLOOK_MANUAL_SESSION", detail="Tokens applied manually via Settings")
        # Resume bot if it was paused due to session error
        if bot_engine.get_status()["paused"]:
            bot_engine.resume()
        return jsonify({"success": True, "message": "Session tokens saved and applied. Bot will use these on next cycle."})
    except Exception as exc:
        return jsonify({"success": False, "message": str(exc)}), 500


# ── Server runner ─────────────────────────────────────────────────────────────

def run_in_thread(port: int = 5000):
    """Start Flask in a background daemon thread."""
    import logging
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)  # Suppress Flask request logs

    thread = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False),
        name="flask-dashboard",
        daemon=True,
    )
    thread.start()
    return thread


def open_browser(port: int = 5000, delay: float = 1.5):
    """Open the dashboard in the default browser after a short delay."""
    def _open():
        import time
        time.sleep(delay)
        webbrowser.open(f"http://localhost:{port}")

    threading.Thread(target=_open, name="open-browser", daemon=True).start()
