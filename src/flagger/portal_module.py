"""
portal_module.py — Registrar Admin Tools portal API client.

Fetches prior notice filing statuses from the AWS API Gateway endpoint.
Uses bulk date-range fetching + pagination to minimize API calls.

Confirmed API endpoint (discovered via F12 Network inspection):
  GET https://ff4tbdztak.execute-api.us-east-1.amazonaws.com/prod/prior-notice/search
  Auth: static token passed as ?token= URL parameter

All errors are raised as specific exception types so the bot engine
can handle each case appropriately.
"""
import time
import requests
from datetime import datetime, timedelta

PORTAL_API_URL = (
    "https://ff4tbdztak.execute-api.us-east-1.amazonaws.com/prod/prior-notice/search"
)
REQUEST_TIMEOUT = 15  # seconds
MAX_RETRIES = 3
RETRY_DELAY_SEC = 5
MAX_PAGES = 200  # Safety limit to prevent infinite pagination loops


class PortalTokenExpiredError(Exception):
    """Raised when the API returns 401/403 or explicitly states token is invalid."""


class PortalNetworkError(Exception):
    """Raised when the API is unreachable after all retries."""


class PortalParseError(Exception):
    """Raised when the API returns an unexpected response format."""


def _request(token: str, params: dict, attempt: int = 1) -> dict:
    """
    Make a single GET request to the portal API with retry logic.

    Returns the parsed JSON response dict.
    Raises PortalTokenExpiredError, PortalNetworkError, or PortalParseError.
    """
    params = {**params, "token": token}

    try:
        resp = requests.get(PORTAL_API_URL, params=params, timeout=REQUEST_TIMEOUT)

        # Token expiry / auth errors
        if resp.status_code in (401, 403):
            raise PortalTokenExpiredError(
                f"HTTP {resp.status_code} — API token may be expired or invalid."
            )

        resp.raise_for_status()

        # Parse JSON
        try:
            data = resp.json()
        except Exception:
            raise PortalParseError(
                f"Portal returned non-JSON response: {resp.text[:300]}"
            )

        # API-level failure
        if not data.get("success", True):
            msg = data.get("message", "Unknown API error")
            if any(w in msg.lower() for w in ("token", "unauthorized", "auth")):
                raise PortalTokenExpiredError(f"API error — token issue: {msg}")
            raise PortalParseError(f"API returned failure: {msg}")

        if "data" not in data:
            raise PortalParseError(
                f"Response missing 'data' field. Got: {str(data)[:300]}"
            )

        return data

    except (PortalTokenExpiredError, PortalParseError):
        raise  # Never retry auth or parse errors

    except (requests.ConnectionError, requests.Timeout) as exc:
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY_SEC)
            return _request(token, params, attempt + 1)
        raise PortalNetworkError(
            f"Portal unreachable after {MAX_RETRIES} attempts: {exc}"
        )

    except requests.RequestException as exc:
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY_SEC)
            return _request(token, params, attempt + 1)
        raise PortalNetworkError(
            f"Request failed after {MAX_RETRIES} attempts: {exc}"
        )


def fetch_statuses(token: str, date_range_days: int = 2) -> dict[str, str]:
    """
    Fetch all prior notice statuses for the last N days.

    Uses pagination (searchAfter cursor) to retrieve all pages.

    Returns:
        { "TRACKING_NUMBER": "STATUS", ... }
        STATUS is one of: CONFIRMED, SUBMITTED, PROCESSING, FAILED

    Raises:
        PortalTokenExpiredError, PortalNetworkError, PortalParseError
    """
    date_to = datetime.now()
    date_from = date_to - timedelta(days=date_range_days)

    base_params = {
        "dateSubmittedFrom": date_from.strftime("%Y-%m-%d"),
        "dateSubmittedTo": date_to.strftime("%Y-%m-%d"),
        "max": 25,
        "sort": "dateSubmitted",
        "dir": "desc",
    }

    all_records: list[dict] = []
    search_after = None
    page = 0

    while page < MAX_PAGES:
        params = base_params.copy()
        if search_after:
            params["searchAfter"] = search_after

        data = _request(token, params)
        records: list[dict] = data.get("data", [])
        all_records.extend(records)

        # Stop when last page received (fewer records than requested)
        if len(records) < 25:
            break

        search_after = data.get("meta", {}).get("searchAfter")
        if not search_after:
            break

        page += 1

    # Build lookup: { tracking_number: STATUS }
    return {
        str(r["TRACKING_NUMBER"]): str(r["STATUS"])
        for r in all_records
        if r.get("TRACKING_NUMBER") and r.get("STATUS")
    }


def test_token(token: str) -> tuple[bool, str]:
    """
    Validate a portal API token by making a minimal test request.

    Returns:
        (True, "Token is valid")  on success
        (False, "reason string")  on failure
    """
    try:
        _request(token, {"max": 1})
        return True, "Token is valid"
    except PortalTokenExpiredError as exc:
        return False, f"Token is invalid or expired: {exc}"
    except PortalNetworkError as exc:
        return False, f"Network error — cannot verify token: {exc}"
    except PortalParseError as exc:
        return False, f"Unexpected response from portal: {exc}"
