"""
check_token.py — Diagnostic tool to verify Outlook token capture.

Run from the project root:
    python check_token.py

This will:
1. Open Chromium and log into Outlook
2. Show exactly what Bearer token was captured (partial — for security)
3. Make a LIVE test call to the OWA service.svc API
4. Report SUCCESS or FAILURE with the full error detail
"""
import sys
import os
from pathlib import Path

# Add src/ to path
src = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(src))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

from flagger import config
config.load()

mailbox_url = config.get_outlook_url()
profile_dir = config.get_browser_profile_dir()

print("=" * 60)
print("  Outlook Token Diagnostic")
print("=" * 60)
print(f"  Mailbox URL : {mailbox_url}")
print(f"  Profile dir : {profile_dir}")
print(f"  Profile exists: {Path(profile_dir).exists()}")
print()

# Step 1: Run Playwright login
print("  [1/3] Opening Chromium to capture session cookies + token...")
print("        *** The browser will open — do NOT close it ***")
print("        Waiting up to 30 seconds for a Bearer token...")
print()

try:
    from flagger.outlook_module import get_cookies_via_playwright
    cookies = get_cookies_via_playwright(mailbox_url, profile_dir)
except Exception as e:
    print(f"  X Playwright failed: {e}")
    sys.exit(1)

# Step 2: Inspect what was captured
print("  [2/3] Inspecting captured data...")
print()

auth_header = cookies.pop("_AUTH_HEADER", None)
remaining_cookies = {k: v for k, v in cookies.items() if v}

print(f"  Cookies captured : {len(remaining_cookies)} cookies")
important = ["X-OWA-CANARY", "owa_at", "OID", "MSISAuth", "ESTSAUTHPERSISTENT"]
for name in important:
    val = cookies.get(name, "")
    if val:
        print(f"    OK {name}: {val[:30]}...")
    else:
        print(f"    MISSING {name}: NOT FOUND")

print()
if auth_header:
    display = auth_header[:40] + "..." + auth_header[-10:] if len(auth_header) > 60 else auth_header
    print(f"  Bearer token : CAPTURED")
    print(f"  Token preview: {display}")
    print(f"  Token length : {len(auth_header)} chars")
else:
    env_token = os.getenv("OUTLOOK_AUTH_TOKEN", "")
    if env_token:
        print(f"  Bearer token : WARNING - NOT captured from browser, but found in .env")
        print(f"  Token preview: {env_token[:40]}...")
        auth_header = env_token if env_token.startswith("Bearer ") else f"Bearer {env_token}"
    else:
        print(f"  Bearer token : FAILED - NOT CAPTURED")
        print()
        print("  Fix: Open the browser profile manually and log into Outlook,")
        print("       then run this script again.")
        sys.exit(1)

print()

# Step 3: Test the token with a real API call
print("  [3/3] Testing token with a live OWA API call (FindItem)...")
print()

import requests

OWA_BASE = "https://outlook.cloud.microsoft/owa/pn@registrarcorp.com/service.svc"
url = f"{OWA_BASE}?action=FindItem&app=Mail&n=1"

headers = {
    "Content-Type": "application/json; charset=utf-8",
    "Accept": "application/json",
    "action": "FindItem",
    "x-anchormailbox": "pn@registrarcorp.com",
    "Authorization": auth_header if auth_header.startswith("Bearer ") else f"Bearer {auth_header}",
    "X-OWA-CANARY": cookies.get("X-OWA-CANARY", ""),
}

body = {
    "Header": {
        "RequestServerVersion": "V2018_01_08",
        "TimeZoneContext": {"TimeZoneDefinition": {"Id": "UTC"}},
    },
    "Body": {
        "__type": "FindItemRequest:#Exchange",
        "ItemShape": {"BaseShape": "IdOnly"},
        "Paging": {
            "__type": "IndexedPageView:#Exchange",
            "BasePoint": "Beginning",
            "Offset": 0,
            "MaxEntriesReturned": 5,
        },
        "ParentFolderIds": [
            {"__type": "DistinguishedFolderId:#Exchange", "Id": "inbox"}
        ],
        "Traversal": "Shallow",
    },
}

try:
    resp = requests.post(url, json=body, cookies=cookies, headers=headers, timeout=15, allow_redirects=False)
    print(f"  HTTP Status  : {resp.status_code}")

    if resp.status_code == 200:
        try:
            data = resp.json()
            items = data["Body"]["ResponseMessages"]["Items"][0]["RootFolder"]["Items"]
            print(f"  SUCCESS! OWA returned {len(items)} inbox items")
            print()
            print("  Token is VALID and working. The bot should work correctly.")
        except Exception:
            print(f"  HTTP 200 received but response structure unexpected:")
            print(f"  {resp.text[:200]}")
    elif resp.status_code == 401:
        print(f"  FAILED - HTTP 401, token is invalid or expired")
        print(f"  Response: {resp.text[:200]}")
        print()
        print("  Fix: Delete the browser_profile/ folder and re-login from scratch.")
    elif resp.status_code in (301, 302):
        print(f"  FAILED - HTTP {resp.status_code} redirect to login")
        print(f"  Location: {resp.headers.get('Location', 'unknown')}")
    else:
        print(f"  FAILED - Unexpected HTTP {resp.status_code}")
        print(f"  Response: {resp.text[:300]}")

except requests.RequestException as exc:
    print(f"  Network error: {exc}")

print()
print("=" * 60)
