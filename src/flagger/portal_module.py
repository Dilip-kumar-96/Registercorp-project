"""
portal_module.py — Registrar Admin Tools portal API client.

Fetches prior notice filing statuses from the AWS API Gateway endpoint.

Confirmed API endpoint (discovered via F12 Network inspection):
  GET https://ff4tbdztak.execute-api.us-east-1.amazonaws.com/prod/prior-notice/search
  Auth: static token passed as ?token= URL parameter

## How status lookup works (and why bulk pagination fails)

The API uses Elasticsearch `search_after` cursor pagination with TWO sort fields:
  sort = [{ "dateSubmitted": "desc" }, { "code.keyword": "asc" }]

The `meta.searchAfter` response value is a two-element list, e.g.:
  [1791925553450, "7ae06dfe4f"]

AWS API Gateway is configured for single-value query string parameters.
When requests passes a Python list as a repeated param
  (?searchAfter=1791925553450&searchAfter=7ae06dfe4f)
the Gateway collapses them — the Lambda only receives ONE value.
Elasticsearch then throws:
  "search_after has 1 value(s) but sort has 2"
  → HTTP 500

This means bulk date-range pagination is BROKEN past page 1 and cannot be fixed
from the client side without changes to the API Gateway / Lambda.

## The fix: per-tracking-number lookup via ?q=

The same endpoint supports a full-text ?q= parameter that uses Elasticsearch's
`simple_query_string` and correctly returns only the matching record:
  GET /search?token=...&q=384159446351
This has been confirmed to return the correct STATUS for any tracking number.

Strategy:
  - fetch_statuses() receives the list of tracking numbers to look up
  - It queries each one individually with ?q=<tracking_number>
  - This avoids pagination entirely and is immune to the cursor bug
  - For the typical 6–70 pending emails per session, this is at most 70 requests
    (~1 request per second with no throttling needed, well within any rate limit)

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


def lookup_tracking_number(token: str, tracking_number: str) -> str | None:
    """
    Look up a single tracking number via the ?q= full-text search parameter.

    Returns the STATUS string (e.g. "CONFIRMED", "FAILED", "SUBMITTED",
    "PROCESSING") or None if the tracking number is not found in the portal.

    Raises PortalTokenExpiredError, PortalNetworkError, PortalParseError.
    """
    data = _request(token, {"q": tracking_number})
    records = data.get("data", [])

    # The q= param uses Elasticsearch simple_query_string which can return
    # partial matches. Find the exact matching record.
    for rec in records:
        if str(rec.get("TRACKING_NUMBER", "")) == str(tracking_number):
            status = rec.get("STATUS")
            return str(status) if status else None

    return None  # Not found in portal


def fetch_statuses(token: str, tracking_numbers: list[str]) -> dict[str, str]:
    """
    Fetch portal statuses for the given list of tracking numbers.

    Queries each tracking number individually using the ?q= parameter.
    This avoids the broken bulk pagination which causes HTTP 500 errors on
    page 2+ due to an AWS API Gateway single-value query string limitation
    that prevents the Elasticsearch `search_after` cursor (a 2-element list)
    from being passed correctly.

    Args:
        token:            Portal API token.
        tracking_numbers: List of tracking number strings to look up.

    Returns:
        { "TRACKING_NUMBER": "STATUS", ... }
        Only entries that were found in the portal are included.
        STATUS is one of: CONFIRMED, SUBMITTED, PROCESSING, FAILED

    Raises:
        PortalTokenExpiredError — if the token is rejected (stops all lookups).
        PortalNetworkError     — if the portal is unreachable (stops all lookups).
        PortalParseError       — if the response format is unexpected.
    """
    result: dict[str, str] = {}

    for tn in tracking_numbers:
        status = lookup_tracking_number(token, tn)
        if status is not None:
            result[tn] = status

    return result


def validate_token(token: str) -> tuple[bool, str]:
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


# Alias for backward compatibility
test_token = validate_token
