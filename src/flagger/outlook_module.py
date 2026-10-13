"""
outlook_module.py — Microsoft Outlook OWA API client.

All email read and flag operations go through the Exchange Web Services (EWS)
OWA API endpoint (service.svc). No browser is used during normal operation.

Playwright is used ONLY at startup to log in and extract session cookies + Bearer token.
Those cookies and the token are then used for all subsequent HTTP requests.

Confirmed API endpoints (discovered via F12 Network inspection):
  POST https://outlook.cloud.microsoft/owa/pn@registrarcorp.com/service.svc?action=FindItem
  POST https://outlook.cloud.microsoft/owa/pn@registrarcorp.com/service.svc?action=UpdateItem
  POST https://outlook.cloud.microsoft/owa/pn@registrarcorp.com/service.svc?action=GetItem

Auth: Microsoft session cookies + Authorization: Bearer token extracted by Playwright.
The Bearer token is persisted to .env as OUTLOOK_AUTH_TOKEN for resilience.
"""
import re
import time
import threading
import requests
from pathlib import Path

OWA_BASE = "https://outlook.cloud.microsoft/owa/pn@registrarcorp.com/service.svc"
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 5

# Thread-safe session state
_cookies: dict = {}
_cookies_lock = threading.Lock()
_session_status: str = "UNKNOWN"  # UNKNOWN | ACTIVE | EXPIRED


class OutlookSessionExpiredError(Exception):
    """Raised when Outlook detects the SSO session has expired."""


class OutlookNetworkError(Exception):
    """Raised when Outlook OWA is unreachable after retries."""


class OutlookAPIError(Exception):
    """Raised when OWA returns an unexpected response format."""


# ── Session cookie management ─────────────────────────────────────────────────

def get_session_status() -> str:
    return _session_status


_auth_token: str = ""


def _set_auth_token(token: str):
    global _auth_token
    with _cookies_lock:
        _auth_token = token


def _set_cookies(new_cookies: dict):
    global _session_status, _auth_token
    with _cookies_lock:
        _cookies.clear()
        auth = new_cookies.pop("_AUTH_HEADER", None)
        if auth:
            _auth_token = auth
        _cookies.update(new_cookies)
        _session_status = "ACTIVE"


def _mark_expired():
    global _session_status
    _session_status = "EXPIRED"


def get_cookies_via_playwright(mailbox_url: str, browser_profile_dir: str) -> dict:
    """
    Open Outlook Web using Playwright and extract session cookies and Bearer token.
    The browser profile preserves the "Keep me signed in" session.

    Strategy:
    1. Listen for Authorization: Bearer headers on ALL requests (context-level)
    2. After page load, do a deep MSAL cache search in localStorage/sessionStorage
    3. Actively trigger an OWA service.svc call via fetch() inside the page
       to force a Bearer-authenticated request we can intercept
    4. Persist the captured token back to .env for resilience

    Returns dict of cookies (including _AUTH_HEADER) ready for use in requests.
    Raises OutlookSessionExpiredError if the session has expired.
    """
    import os
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

    profile_path = str(Path(browser_profile_dir).resolve())

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            headless=False,
            args=["--start-minimized", "--no-sandbox"],
        )
        try:
            # Start with any previously saved token as fallback
            captured = {"auth": os.getenv("OUTLOOK_AUTH_TOKEN", "")}

            def on_request(req):
                """Intercept ANY request that carries a Bearer token."""
                auth = req.headers.get("authorization")
                if auth and auth.startswith("Bearer "):
                    captured["auth"] = auth

            # Context-level listener catches ALL frames, workers, service workers
            context.on("request", on_request)

            page = context.new_page()
            page.goto(mailbox_url, wait_until="domcontentloaded", timeout=30_000)

            # Give the page time to settle / redirect
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except PlaywrightTimeout:
                pass  # Timeout is okay — we just check the URL

            url = page.url
            if any(d in url for d in (
                "microsoftonline.com", "login.microsoft.com",
                "login.live.com", "account.microsoft.com"
            )):
                raise OutlookSessionExpiredError(
                    "Outlook session has expired. "
                    "Please re-login via the dashboard Re-login button."
                )

            # Wait a moment for background service.svc calls to fire
            time.sleep(2)

            # ── Strategy 2: Deep MSAL cache search ─────────────────────────────
            if not captured["auth"]:
                try:
                    tok = page.evaluate("""
                    () => {
                        // MSAL stores tokens in localStorage with keys like:
                        // "<clientId>.<tenantId>-login.windows.net-accesstoken-..."
                        // Keys may contain "accesstoken", "idtoken", "secret", etc.
                        const stores = [];
                        try { stores.push(localStorage); } catch(e) {}
                        try { stores.push(sessionStorage); } catch(e) {}

                        for (const storage of stores) {
                            try {
                                for (let i = 0; i < storage.length; i++) {
                                    const k = storage.key(i);
                                    if (!k) continue;
                                    const val = storage.getItem(k);
                                    if (!val) continue;

                                    // Direct JWT (rare)
                                    if (val.startsWith("eyJ") && val.split(".").length === 3) {
                                        return "Bearer " + val;
                                    }

                                    // JSON blob containing token
                                    if (val.includes("eyJ")) {
                                        try {
                                            const obj = JSON.parse(val);
                                            const fields = [
                                                "secret", "credential", "accessToken",
                                                "access_token", "token", "value"
                                            ];
                                            for (const f of fields) {
                                                if (obj[f] && typeof obj[f] === "string"
                                                    && obj[f].startsWith("eyJ")
                                                    && obj[f].split(".").length === 3) {
                                                    return "Bearer " + obj[f];
                                                }
                                            }
                                        } catch(e) {}
                                    }
                                }
                            } catch(e) {}
                        }
                        return "";
                    }
                    """)
                    if tok:
                        captured["auth"] = tok
                except Exception:
                    pass

            # ── Strategy 3: Trigger a live OWA API call to force Bearer emission ──
            if not captured["auth"]:
                try:
                    # Build a lightweight FindItem request and fire it via fetch()
                    # inside the page context — this forces OWA's JS to add the
                    # Authorization header, which we intercept via on_request.
                    service_url = mailbox_url.rstrip("/").split("/mail/")[0]
                    email_part = mailbox_url.split("/mail/")[-1].rstrip("/")
                    svc_endpoint = f"{service_url}/owa/{email_part}/service.svc?action=FindItem&app=Mail&n=0"

                    page.evaluate(f"""
                    async () => {{
                        try {{
                            await fetch({repr(svc_endpoint)}, {{
                                method: "POST",
                                credentials: "include",
                                headers: {{ "Content-Type": "application/json" }},
                                body: JSON.stringify({{ Header: {{ RequestServerVersion: "V2018_01_08" }}, Body: {{ __type: "FindItemRequest:#Exchange", Traversal: "Shallow", ItemShape: {{ BaseShape: "IdOnly" }}, ParentFolderIds: [{{ __type: "DistinguishedFolderId:#Exchange", Id: "inbox" }}] }} }})
                            }});
                        }} catch(e) {{}}
                    }}
                    """)
                    # Give the interceptor a moment to fire
                    time.sleep(2)
                except Exception:
                    pass

            # Final settle
            if not captured["auth"]:
                time.sleep(2)

            cookies = {c["name"]: c["value"] for c in context.cookies()}
            if captured["auth"]:
                cookies["_AUTH_HEADER"] = captured["auth"]
                # Persist token to .env for resilience across restarts
                _save_token_to_env(captured["auth"])
            return cookies

        except OutlookSessionExpiredError:
            raise
        except Exception as exc:
            raise OutlookNetworkError(f"Playwright error during login: {exc}") from exc
        finally:
            context.close()


def _save_token_to_env(token: str):
    """Persist the captured Bearer token to .env so it survives restarts."""
    try:
        from pathlib import Path as _Path
        from dotenv import set_key as _set_key
        root = _Path(__file__).resolve().parent.parent.parent
        env_path = root / ".env"
        if env_path.exists():
            _set_key(str(env_path), "OUTLOOK_AUTH_TOKEN", token)
    except Exception:
        pass  # Non-critical


def initialize_session(mailbox_url: str, browser_profile_dir: str):
    """Extract cookies via Playwright and store them. Call once at bot startup."""
    cookies = get_cookies_via_playwright(mailbox_url, browser_profile_dir)
    _set_cookies(cookies)


# ── OWA API request helper ────────────────────────────────────────────────────

def _post(action: str, body: dict, attempt: int = 1) -> dict:
    """POST to the OWA service.svc endpoint with the given action and body."""
    import os
    url = f"{OWA_BASE}?action={action}&app=Mail&n=1"
    with _cookies_lock:
        cookies = dict(_cookies)
        auth = _auth_token

    auth_header = auth or os.getenv("OUTLOOK_AUTH_TOKEN", "")
    if auth_header and not auth_header.startswith("Bearer "):
        auth_header = f"Bearer {auth_header}"

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
        "X-OWA-CANARY": cookies.get("X-OWA-CANARY", ""),
        "action": action,
        "x-anchormailbox": "pn@registrarcorp.com",
    }
    if auth_header:
        headers["Authorization"] = auth_header

    try:
        resp = requests.post(
            url, json=body, cookies=cookies,
            headers=headers, timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )

        # Redirect to login or 401/403/440 = session expired
        if resp.status_code in (301, 302, 303, 401, 403, 440):
            _mark_expired()
            raise OutlookSessionExpiredError(
                f"Outlook session expired or unauthorized (HTTP {resp.status_code}). Please re-login via the dashboard."
            )

        if resp.status_code != 200:
            raise OutlookAPIError(
                f"Outlook API error HTTP {resp.status_code}: {resp.text[:200]}"
            )

        # Try JSON parse — failure usually means we got a login page HTML
        try:
            data = resp.json()
        except Exception:
            if any(kw in resp.text.lower() for kw in ("microsoftonline", "login", "sign in")):
                _mark_expired()
                raise OutlookSessionExpiredError(
                    "Outlook session expired: received login HTML instead of JSON."
                )
            raise OutlookAPIError(
                f"Invalid JSON from {action}: {resp.text[:200]}"
            )

        return data

    except (OutlookSessionExpiredError, OutlookAPIError):
        raise

    except (requests.ConnectionError, requests.Timeout) as exc:
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY)
            return _post(action, body, attempt + 1)
        raise OutlookNetworkError(
            f"{action} network error after {MAX_RETRIES} attempts: {exc}"
        )

    except requests.RequestException as exc:
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY)
            return _post(action, body, attempt + 1)
        raise OutlookNetworkError(
            f"{action} request failed after {MAX_RETRIES} attempts: {exc}"
        )


# ── FindItem — read inbox emails ──────────────────────────────────────────────

def find_unflagged_fedex_emails(sender_filter: str) -> list[dict]:
    """
    Fetch all unflagged emails from the specified sender in the inbox.

    Returns list of dicts:
        {
            "tracking_number": str,
            "item_id": str,
            "change_key": str,
            "received_at": str,
        }

    Raises: OutlookSessionExpiredError, OutlookNetworkError, OutlookAPIError
    """
    body = {
        "Header": {
            "RequestServerVersion": "V2018_01_08",
            "TimeZoneContext": {"TimeZoneDefinition": {"Id": "UTC"}},
        },
        "Body": {
            "__type": "FindItemRequest:#Exchange",
            "ItemShape": {
                "BaseShape": "IdOnly",
                "AdditionalProperties": [
                    {"__type": "PropertyUri:#Exchange", "FieldURI": "message:Sender"},
                    {"__type": "PropertyUri:#Exchange", "FieldURI": "item:Subject"},
                    {"__type": "PropertyUri:#Exchange", "FieldURI": "item:Flag"},
                    {"__type": "PropertyUri:#Exchange", "FieldURI": "item:Preview"},
                    {"__type": "PropertyUri:#Exchange", "FieldURI": "item:DateTimeReceived"},
                ],
            },
            "Paging": {
                "__type": "IndexedPageView:#Exchange",
                "BasePoint": "Beginning",
                "Offset": 0,
                "MaxEntriesReturned": 150,
            },
            "ParentFolderIds": [
                {"__type": "DistinguishedFolderId:#Exchange", "Id": "inbox"}
            ],
            "Traversal": "Shallow",
        },
    }

    data = _post("FindItem", body)

    try:
        items = (
            data["Body"]["ResponseMessages"]["Items"][0]
            ["RootFolder"]["Items"]
        )
    except (KeyError, IndexError, TypeError) as exc:
        raise OutlookAPIError(
            f"Unexpected FindItem response structure: {exc}. "
            f"Response: {str(data)[:200]}"
        )

    emails = []
    for item in items:
        try:
            # Skip already-flagged emails
            if item.get("Flag", {}).get("FlagStatus") == "Flagged":
                continue

            # In-memory sender filter if Sender field is present
            if sender_filter:
                sender_addr = (
                    item.get("Sender", {})
                    .get("Mailbox", {})
                    .get("EmailAddress", "")
                    .lower()
                )
                if sender_addr and sender_filter.lower() not in sender_addr:
                    continue

            preview = item.get("Preview", "")
            tracking = _extract_tracking_number(preview)
            if not tracking:
                continue  # No tracking number found — skip silently

            emails.append({
                "tracking_number": tracking,
                "item_id": item["ItemId"]["Id"],
                "change_key": item["ItemId"]["ChangeKey"],
                "received_at": item.get("DateTimeReceived", ""),
            })
        except (KeyError, TypeError):
            continue  # Skip malformed entries

    return emails


def _extract_tracking_number(preview: str) -> str | None:
    """Extract the FedEx tracking number from the email Preview field using regex."""
    match = re.search(r"Tracking Number:\s+(\d+)", preview)
    return match.group(1) if match else None


# ── UpdateItem — flag an email ────────────────────────────────────────────────

def flag_email(item_id: str, change_key: str, dry_run: bool = False) -> dict:
    """
    Add a red flag to an email via the UpdateItem OWA API.

    Args:
        item_id: ItemId.Id from FindItem response
        change_key: ItemId.ChangeKey from FindItem response
        dry_run: If True, log the action but do not actually flag

    Returns:
        {
            "success": bool,
            "new_change_key": str,   # Updated ChangeKey after successful flag
            "error_code": str | None,
            "dry_run": bool,
        }
    """
    if dry_run:
        return {
            "success": True,
            "new_change_key": change_key,
            "error_code": None,
            "dry_run": True,
        }

    body = {
        "Header": {"RequestServerVersion": "V2018_01_08"},
        "Body": {
            "__type": "UpdateItemRequest:#Exchange",
            "ItemChanges": [
                {
                    "__type": "ItemChange:#Exchange",
                    "ItemId": {"__type": "ItemId:#Exchange", "Id": item_id, "ChangeKey": change_key},
                    "Updates": [
                        {
                            "__type": "SetItemField:#Exchange",
                            "Path": {
                                "__type": "PropertyUri:#Exchange",
                                "FieldURI": "item:Flag",
                            },
                            "Item": {
                                "__type": "Message:#Exchange",
                                "Flag": {"FlagStatus": "Flagged"},
                            },
                        }
                    ],
                }
            ],
            "ConflictResolution": "AutoResolve",
            "MessageDisposition": "SaveOnly",
        },
    }

    data = _post("UpdateItem", body)

    try:
        msg = data["Body"]["ResponseMessages"]["Items"][0]
        code = msg.get("ResponseCode", "")
        cls = msg.get("ResponseClass", "")

        if cls == "Success" and code == "NoError":
            new_ck = (
                msg.get("Items", [{}])[0]
                .get("ItemId", {})
                .get("ChangeKey", change_key)
            )
            return {
                "success": True,
                "new_change_key": new_ck,
                "error_code": None,
                "dry_run": False,
            }

        return {
            "success": False,
            "new_change_key": change_key,
            "error_code": code or "UnknownError",
            "dry_run": False,
        }

    except (KeyError, IndexError, TypeError) as exc:
        return {
            "success": False,
            "new_change_key": change_key,
            "error_code": f"ParseError:{exc}",
            "dry_run": False,
        }


# ── GetItem — fetch fresh ChangeKey ──────────────────────────────────────────

def get_item_change_key(item_id: str) -> str | None:
    """
    Fetch the current ChangeKey for an email.
    Used when UpdateItem fails with ErrorChangeKeyRequired — the ChangeKey
    changed because someone else modified the email between FindItem and UpdateItem.

    Returns the new ChangeKey, or None if the item no longer exists.
    """
    body = {
        "Header": {"RequestServerVersion": "V2018_01_08"},
        "Body": {
            "__type": "GetItemRequest:#Exchange",
            "ItemShape": {"BaseShape": "IdOnly"},
            "ItemIds": [{"__type": "ItemId:#Exchange", "Id": item_id}],
        },
    }

    try:
        data = _post("GetItem", body)
        return (
            data["Body"]["ResponseMessages"]["Items"][0]
            ["Items"][0]["ItemId"]["ChangeKey"]
        )
    except (KeyError, IndexError, TypeError, OutlookAPIError):
        return None
