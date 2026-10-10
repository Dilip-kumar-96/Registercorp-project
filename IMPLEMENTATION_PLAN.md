# FedEx Email Auto-Flagger — Complete Implementation Plan

**Version:** 7.0 (Final — Build-Ready)
**Last updated:** 2026-10-11
**Repository:** https://github.com/Dilip-kumar-96/Registercorp-project
**Status:** ✅ All APIs confirmed — Ready to build

> **Purpose of this document:** This file is the single source of truth for the entire project.
> Any developer or AI reading this document should be able to build the exact bot from scratch
> without needing any other reference. Every API, data format, decision, and error case is
> documented here precisely.

---

## Quick Summary (for any new developer or AI reading this)

This is a Python background application that:
1. Reads a shared Microsoft Outlook inbox via the OWA internal API (no browser needed during normal operation)
2. Extracts tracking numbers from FedEx prior-notice emails
3. Checks each tracking number's status via the Registrar Admin Tools portal REST API
4. Flags emails with status CONFIRMED using the Outlook OWA API
5. Shows everything on a local Flask dashboard at http://localhost:5000
6. Is packaged as a Windows EXE — double-click to start, system tray icon to manage
7. Has a first-launch setup wizard — no manual config file editing required
8. All authentication, settings, and errors are managed entirely through the dashboard UI

**No database to install** (SQLite is built into Python — zero setup).
**No command line during normal use** — EXE + dashboard handles everything.
**No manual .env editing** — dashboard Settings page writes config automatically.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Background & Context](#2-background--context)
3. [The Manual Process Being Automated](#3-the-manual-process-being-automated)
4. [Technical Discovery — All APIs Confirmed](#4-technical-discovery--all-apis-confirmed)
5. [Complete Architecture](#5-complete-architecture)
6. [The 2-Minute Cycle — Detailed](#6-the-2-minute-cycle--detailed)
7. [Session & Data Management](#7-session--data-management)
8. [Error Handling Strategy](#8-error-handling-strategy)
9. [Web Dashboard Specification](#9-web-dashboard-specification)
10. [Tech Stack](#10-tech-stack)
11. [Project Folder Structure](#11-project-folder-structure)
12. [Environment Configuration (.env)](#12-environment-configuration-env)
13. [Installation Guide](#13-installation-guide)
14. [Build Roadmap](#14-build-roadmap)
15. [Testing Strategy](#15-testing-strategy)
16. [Git Workflow](#16-git-workflow)
17. [Risks & Mitigations](#17-risks--mitigations)
18. [Key Decisions Log](#18-key-decisions-log)

---

## 1. Project Overview

**Project name:** FedEx Email Auto-Flagger
**Company:** Registrar Corp (USA) — Indian office team
**Office hours:** 8:30 PM to 4:30 AM IST (= US daytime hours)
**Team size:** 6 members sharing one Outlook mailbox

A Python background application that automatically:
1. Reads the shared Outlook inbox via direct API calls
2. Extracts tracking numbers from FedEx prior-notice notification emails
3. Checks each tracking number's status on the Registrar Admin Tools portal via direct API
4. Adds a red flag to emails whose status is **CONFIRMED**
5. Re-checks SUBMITTED/PROCESSING emails on the next cycle
6. Ignores FAILED emails permanently within a session
7. Shows real-time activity on a local web dashboard

**The bot uses NO Playwright browser automation during normal operation.**
Playwright is used only once per session — at startup to log in and extract session cookies.
All subsequent operations are direct HTTP API calls.

---

## 2. Background & Context

Registrar Corp is a US-based FDA compliance company. The Indian team files Prior Notices (mandatory FDA declarations) for food shipments entering the United States and monitors shipment statuses.

The team shares a single Microsoft Outlook mailbox: `pn@registrarcorp.com`

The inbox receives a mix of emails:
- FedEx prior-notice notification emails (from `myfda@registrarcorp.com`)
- Prior notice confirmation emails
- Customer emails and other miscellaneous emails

FedEx volume: approximately 100–200 emails per day, sometimes more on busy days.
Maximum unflagged FedEx emails in inbox at any time: approximately 70.

The Registrar Admin Tools portal (`tools.registrarcorp.com`) is where the team checks
prior notice filing statuses. It is backed by a direct REST API on AWS API Gateway.

---

## 3. The Manual Process Being Automated

### Step-by-step manual workflow (what a human does today)

1. Open Outlook Web (`https://outlook.cloud.microsoft/mail/pn@registrarcorp.com/`)
2. Find an email from `myfda@registrarcorp.com` with subject `"Registrar: New prior notice from fedex"`
3. Open the email — read the email body, which contains:
   ```
   Account Name:   fedex
   Carrier:        FedEx
   Tracking Number:        384007184685
   Shipper Company:        TMRW
   Record Code:    246dfa1d40
   ```
4. Copy the **Tracking Number**
5. Open the Registrar Admin Tools portal (`https://tools.registrarcorp.com/priorNotice/api`)
6. Search for the tracking number
7. Read the STATUS column:

   | STATUS | What to do |
   |---|---|
   | **CONFIRMED** | Go back to Outlook → right-click email → add **red flag** ✅ |
   | **SUBMITTED** | Come back and check again in a few minutes ⏳ |
   | **PROCESSING** | Come back and check again in a few minutes ⏳ |
   | **FAILED** | Do nothing — ignore permanently 🚫 |

8. For SUBMITTED/PROCESSING: repeat from Step 2 every few minutes until confirmed

### Why this is painful
- Confirmation typically happens in **under 1 minute** but sometimes takes 5, 10, or 15+ minutes
- 100–200 emails/day means constant interruptions
- Up to 70 emails may need checking at any given time
- FAILED emails sit in the inbox unflagged and create confusion
- This task takes significant attention away from prior notice filing (the primary, more important task)

### Inbox maintenance
A team member periodically cleans the inbox — removing flagged emails, old emails, and
irrelevant emails. This is done informally throughout the shift.

---

## 4. Technical Discovery — All APIs Confirmed

> **Critical note:** During planning, we discovered that BOTH the Outlook inbox AND the portal
> use direct REST APIs. This eliminates the need for browser automation in the main loop.
> All three operations (read emails, check portal, flag emails) are confirmed working via API.

---

### 4.1 Portal API — Status Checking

**Endpoint (GET):**
```
https://ff4tbdztak.execute-api.us-east-1.amazonaws.com/prod/prior-notice/search
```

**Authentication:** Static token passed as URL parameter. No login required.
```
?token=<PORTAL_API_TOKEN from .env>
```

**Query parameters:**
```
token              = <from .env>           REQUIRED - API key
query              = 384007184685          Optional - specific tracking number search
dateSubmittedFrom  = 2026-10-09           Optional - filter by date (YYYY-MM-DD)
dateSubmittedTo    = 2026-10-11           Optional - filter by date (YYYY-MM-DD)
max                = 25                   Page size (max 25 per page)
sort               = dateSubmitted        Sort field
dir                = desc                 Sort direction
```

**Example request (bulk fetch — preferred approach):**
```
GET /prod/prior-notice/search?token=TOKEN&dateSubmittedFrom=2026-10-09&dateSubmittedTo=2026-10-11&max=25&sort=dateSubmitted&dir=desc
```

**Example response:**
```json
{
  "success": true,
  "statusCode": 200,
  "message": "Search completed",
  "data": [
    {
      "STATUS": "CONFIRMED",
      "TRACKING_NUMBER": "384007184685",
      "code": "246dfa1d40",
      "CARRIER": "FedEx",
      "accountName": "fedex",
      "lastUpdated": "2026-10-09T16:34:49.118Z",
      "dateSubmitted": "2026-10-09T16:34:49.118Z",
      "dateProcessed": "2026-10-09T16:35:53.274Z",
      "ENTRY_ID": "###-4338730-7"
    }
  ],
  "meta": {
    "total": 74060,
    "max": 25,
    "offset": 0,
    "searchAfter": [1791543736312, "b111a27451"],
    "count": 25
  }
}
```

**Key fields used by the bot:**
- `data[].STATUS` — one of: `"CONFIRMED"`, `"SUBMITTED"`, `"PROCESSING"`, `"FAILED"`
- `data[].TRACKING_NUMBER` — matches tracking number from email
- `meta.count` — number of records in this page
- `meta.searchAfter` — pagination cursor for next page (use as `searchAfter` param)

**Pagination logic:**
```python
# Fetch all records for date range
all_records = []
search_after = None

while True:
    params = {
        "token": PORTAL_API_TOKEN,
        "dateSubmittedFrom": date_from,
        "dateSubmittedTo": date_to,
        "max": 25,
        "sort": "dateSubmitted",
        "dir": "desc"
    }
    if search_after:
        params["searchAfter"] = search_after  # pagination cursor

    response = requests.get(PORTAL_API_URL, params=params, timeout=15)
    data = response.json()

    all_records.extend(data["data"])

    if len(data["data"]) < 25:
        break  # last page
    search_after = data["meta"]["searchAfter"]

# Build lookup table
status_map = {r["TRACKING_NUMBER"]: r["STATUS"] for r in all_records}
```

**Token expiry detection:**
```python
# Token is expired if:
# - Response status is 401, 403
# - Response body has "success": false
# - Response body is empty or not JSON
# - "data" field is missing from response
```

---

### 4.2 Outlook API — Reading Emails (FindItem)

**Endpoint (POST):**
```
https://outlook.cloud.microsoft/owa/pn@registrarcorp.com/service.svc?action=FindItem&app=Mail&n=1
```

**Authentication:** Microsoft session cookies (extracted by Playwright at login).
The cookie is passed in all requests as HTTP Cookie headers.

**Request payload (JSON body):**
```json
{
  "Header": {
    "RequestServerVersion": "V2018_01_08",
    "TimeZoneContext": {
      "TimeZoneDefinition": {
        "Id": "UTC"
      }
    }
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
        {"__type": "PropertyUri:#Exchange", "FieldURI": "item:DateTimeReceived"}
      ]
    },
    "Paging": {
      "__type": "IndexedPageView:#Exchange",
      "BasePoint": "Beginning",
      "Offset": 0,
      "MaxEntriesReturned": 150
    },
    "Restriction": {
      "IsEqualTo": {
        "FieldURI": {"FieldURI": "message:Sender"},
        "FieldURIOrConstant": {
          "Constant": {"Value": "myfda@registrarcorp.com"}
        }
      }
    },
    "ParentFolderIds": [
      {"__type": "DistinguishedFolderId:#Exchange", "Id": "inbox"}
    ],
    "Traversal": "Shallow"
  }
}
```

**Example response (one email entry):**
```json
{
  "Body": {
    "ResponseMessages": {
      "Items": [{
        "RootFolder": {
          "TotalItemsInView": 759,
          "IncludesLastItemInRange": false,
          "Items": [
            {
              "__type": "Message:#Exchange",
              "ItemId": {
                "Id": "AAkALgAAAAAAHYQDEapmEc2byACqAC/EWg0A9GUdL7b+ZkO2HH1ot5zRMwADiR/00QAA",
                "ChangeKey": "CQAAABYAAAD0ZR0vtv5mQ7YcfWi3nNEzAAOHPcwl"
              },
              "Sender": {
                "Mailbox": {
                  "EmailAddress": "myfda@registrarcorp.com"
                }
              },
              "Subject": "Registrar: New prior notice from fedex",
              "DateTimeReceived": "2026-10-10T16:01:11-04:00",
              "Flag": {
                "FlagStatus": "NotFlagged"
              },
              "Preview": "Account Name:   fedex\r\nCarrier:        FedEx\r\nTracking Number:        384114933419\r\nShipper Company:        TMRW\r\nRecord Code:    4efb877366\r\n\r\nLog in to the MyFDA Admin to fulfill the request..."
            }
          ]
        }
      }]
    }
  }
}
```

**Key fields extracted per email:**
```python
item_id    = email["ItemId"]["Id"]          # needed to flag this email
change_key = email["ItemId"]["ChangeKey"]   # needed to flag this email (version tag)
flag_status = email["Flag"]["FlagStatus"]   # "NotFlagged" or "Flagged"
preview    = email["Preview"]               # contains tracking number

# Extract tracking number from Preview using regex
import re
match = re.search(r'Tracking Number:\s+(\d+)', preview)
tracking_number = match.group(1) if match else None
```

**Pagination:** Set `MaxEntriesReturned` to 150. With filtering by sender and unflagged status,
result set is approximately 70 emails max — fits in one call.
If `IncludesLastItemInRange` is false, increment `Offset` and fetch again.

**Session expiry detection:**
```python
# Session is expired if:
# - HTTP response status is 302 (redirect to login page)
# - HTTP response status is 401
# - Response body contains "X-OWA-Error" or login page HTML
# - JSON parsing fails (got HTML login page instead)
```

---

### 4.3 Outlook API — Flagging Emails (UpdateItem)

**Endpoint (POST):**
```
https://outlook.cloud.microsoft/owa/pn@registrarcorp.com/service.svc?action=UpdateItem&app=Mail&n=1
```

**Authentication:** Same Microsoft session cookies as FindItem.

**Request payload (JSON body):**
```json
{
  "Header": {
    "RequestServerVersion": "V2018_01_08"
  },
  "Body": {
    "__type": "UpdateItemRequest:#Exchange",
    "ItemChanges": [
      {
        "__type": "ItemChange:#Exchange",
        "ItemId": {
          "Id": "AAkALgAAAAAAHYQDEapmEc2byACqAC/EWg0A9GUdL7b+ZkO2HH1ot5zRMwADiR/00QAA",
          "ChangeKey": "CQAAABYAAAD0ZR0vtv5mQ7YcfWi3nNEzAAOHPcwl"
        },
        "Updates": [
          {
            "__type": "SetItemField:#Exchange",
            "Path": {
              "__type": "PropertyUri:#Exchange",
              "FieldURI": "item:Flag"
            },
            "Item": {
              "__type": "Message:#Exchange",
              "Flag": {
                "FlagStatus": "Flagged"
              }
            }
          }
        ]
      }
    ],
    "ConflictResolution": "AutoResolve",
    "MessageDisposition": "SaveOnly"
  }
}
```

**Success response:**
```json
{
  "Body": {
    "ResponseMessages": {
      "Items": [{
        "ResponseCode": "NoError",
        "ResponseClass": "Success",
        "Items": [{"ItemId": {"Id": "...", "ChangeKey": "..."}}]
      }]
    }
  }
}
```

**Important:** After a successful `UpdateItem`, the `ChangeKey` changes.
The bot must use the new `ChangeKey` from the UpdateItem response for any future updates.

**Failure cases:**
- `ResponseCode: "ErrorItemNotFound"` — email was deleted between FindItem and UpdateItem. Skip it.
- `ResponseCode: "ErrorChangeKeyRequired"` — ChangeKey mismatch. Re-fetch via FindItem and retry.
- `ResponseClass: "Error"` — general error. Log and skip this email.

---

### 4.4 Playwright — Login (One-Time per Session)

Used only at bot startup to obtain the Outlook session cookies.

**Chrome profile strategy:**
- A dedicated Chrome profile is created specifically for the bot
- Profile stored at: `browser_profile/` (gitignored)
- The user logs into Outlook in this profile ONCE with "Keep me signed in" checked
- On subsequent startups, the saved session in the profile is usually still active
- If session expired, Playwright detects the login page and alerts the user

**Playwright login flow:**
```python
from playwright.sync_api import sync_playwright

def get_outlook_cookies():
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir="./browser_profile",
            headless=False,  # visible during login, hidden after
            args=["--start-minimized"]
        )
        page = browser.new_page()
        page.goto("https://outlook.cloud.microsoft/mail/pn@registrarcorp.com/")
        page.wait_for_load_state("networkidle", timeout=30000)

        # Check if we got the login page
        if "login" in page.url or "microsoftonline" in page.url:
            # Session expired — make browser visible, alert user
            raise OutlookSessionExpiredError("Outlook session expired. Please log in.")

        # Extract cookies
        cookies = browser.cookies()
        browser.close()
        return {c["name"]: c["value"] for c in cookies}
```

---

## 5. Complete Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    FedEx Email Auto-Flagger                     │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                  STARTUP (once)                         │   │
│  │  Playwright → Outlook Web → Login → Extract Cookies     │   │
│  │  If session expired: alert user → wait → retry          │   │
│  └──────────────────────────┬──────────────────────────────┘   │
│                             │ session cookies                   │
│  ┌──────────────────────────▼──────────────────────────────┐   │
│  │              MAIN LOOP (every 2 minutes)                 │   │
│  │                                                         │   │
│  │  PHASE 1 — FindItem (HTTP POST with cookies)            │   │
│  │    Filter: sender=myfda@registrarcorp.com, unflagged    │   │
│  │    Returns: ItemId + ChangeKey + Tracking Number        │   │
│  │    → New tracking numbers → add to DB as PENDING        │   │
│  │    → Known FAILED → skip entirely                       │   │
│  │                                                         │   │
│  │  PHASE 2 — Portal API (HTTP GET with token)             │   │
│  │    Only if PENDING emails exist (else skip)             │   │
│  │    Bulk-fetch by date range → paginate                  │   │
│  │    Build: {tracking_number: STATUS} lookup table        │   │
│  │    → CONFIRMED → mark DB CONFIRMED                      │   │
│  │    → FAILED → mark DB FAILED (done forever)             │   │
│  │    → SUBMITTED/PROCESSING → stay PENDING                │   │
│  │                                                         │   │
│  │  PHASE 3 — UpdateItem (HTTP POST with cookies)          │   │
│  │    For each CONFIRMED email in DB                       │   │
│  │    POST UpdateItem → FlagStatus: Flagged                │   │
│  │    → Success → mark DB FLAGGED                          │   │
│  │    → Already flagged → mark DB FLAGGED (skip)           │   │
│  │    → Email not found → mark DB GONE (email was deleted) │   │
│  └──────────────────────────┬──────────────────────────────┘   │
│                             │                                   │
│           ┌─────────────────┼─────────────────┐                │
│           │                 │                 │                │
│    ┌──────▼──────┐  ┌───────▼──────┐  ┌───────▼──────┐       │
│    │  SQLite DB  │  │ Session Log  │  │  Flask UI    │       │
│    │ (session)   │  │    File      │  │ localhost:5000│       │
│    └─────────────┘  └──────────────┘  └──────────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. The 2-Minute Cycle — Detailed

### Phase 1: Discover new emails (FindItem)

```
POST service.svc?action=FindItem
Body: filter by sender=myfda@registrarcorp.com, MaxEntriesReturned=150

For each email in response:
  Extract tracking_number from Preview using regex
  If tracking_number is None:
    → Log warning: "Email <ItemId> has no tracking number in Preview"
    → Skip this email

  Look up tracking_number in session DB:
    CASE: Not in DB
      → INSERT into DB: (tracking_number, item_id, change_key, status=PENDING, first_seen=now)
      → Log: "DISCOVERED tracking=<N>"
    CASE: Status = FAILED
      → Skip (don't re-check this session)
    CASE: Status = PENDING
      → Already tracked, no action
    CASE: Status = CONFIRMED
      → Will be flagged in Phase 3
    CASE: Status = FLAGGED
      → Already done (email won't appear in unflagged filter anyway)
```

### Phase 2: Check portal statuses (Portal API)

```
Query DB: SELECT tracking_number WHERE status = 'PENDING'

IF count = 0:
  → Log: "No pending emails. Skipping portal check."
  → Skip to Phase 3

IF count > 0:
  Build date range: today - API_DATE_RANGE_DAYS to today
  
  Fetch all portal records for date range (paginate):
    GET portal/search?token=TOKEN&dateSubmittedFrom=...&dateSubmittedTo=...&max=25
    Repeat with searchAfter until all pages fetched
  
  Build lookup: { "384007184685": "CONFIRMED", ... }
  
  For each PENDING tracking number in DB:
    Look up in portal_lookup:
    CASE: STATUS = "CONFIRMED"
      → UPDATE DB status = CONFIRMED
      → Log: "CONFIRMED tracking=<N>"
    CASE: STATUS = "FAILED"
      → UPDATE DB status = FAILED
      → Log: "FAILED tracking=<N> (will not recheck this session)"
    CASE: STATUS = "SUBMITTED" or "PROCESSING"
      → No change (stay PENDING)
      → Log: "PENDING tracking=<N> status=<STATUS>"
    CASE: Not found in portal results
      → No change (stay PENDING)
      → Log: "NOT_FOUND tracking=<N> (staying pending)"
```

### Phase 3: Flag confirmed emails (UpdateItem)

```
Query DB: SELECT * WHERE status = 'CONFIRMED'

IF count = 0:
  → Log: "No emails to flag."

FOR each confirmed email:
  POST service.svc?action=UpdateItem
  Body: ItemId + ChangeKey + FlagStatus=Flagged

  CASE: ResponseCode = "NoError"
    → UPDATE DB status = FLAGGED, flagged_at = now
    → Log: "FLAGGED tracking=<N>"
    → Update dashboard counter

  CASE: ResponseCode = "ErrorItemNotFound"
    → UPDATE DB status = GONE
    → Log: "EMAIL_GONE tracking=<N> (deleted before flagging)"

  CASE: ResponseCode = "ErrorChangeKeyRequired"
    → Re-fetch this email's ChangeKey via GetItem
    → Retry UpdateItem with new ChangeKey (one retry only)
    → If retry fails: Log error, mark DB status = ERROR

  CASE: Any other error
    → Log: "FLAG_ERROR tracking=<N> error=<ResponseCode>"
    → Leave status as CONFIRMED (will retry next cycle)
```

---

## 7. Session & Data Management

### Session lifecycle

**Every time the bot starts:**
1. Create new session log file: `logs/session_YYYY-MM-DD_HH-MM-SS.log`
2. Write: `[timestamp] SESSION_START`
3. Wipe SQLite database (drop and recreate all tables)
4. Run Playwright login to get fresh cookies
5. Begin the 2-minute scan loop

**Every cycle:**
- All actions written to the session log with timestamps
- SQLite updated after each state change

**On graceful shutdown (user clicks Stop on dashboard):**
1. Write session summary to log:
   ```
   [timestamp] SESSION_END (user stopped)
   [timestamp] DURATION: 6h 57m 10s
   [timestamp] SUMMARY: flagged=187 failed=9 pending=0 errors=0
   ```
2. Wipe SQLite database

**On forced shutdown/crash:**
- SQLite is ACID-compliant — never corrupts even if power is cut mid-write
- Log file ends mid-session — still readable and useful
- On next startup: fresh DB, new log file, pending emails in inbox re-discovered automatically

### SQLite database schema

```sql
CREATE TABLE emails (
    tracking_number   TEXT PRIMARY KEY,
    item_id           TEXT NOT NULL,
    change_key        TEXT NOT NULL,
    bot_status        TEXT NOT NULL DEFAULT 'PENDING',
    -- bot_status values: PENDING | CONFIRMED | FAILED | FLAGGED | GONE | ERROR
    first_seen_at     TEXT NOT NULL,  -- ISO8601 timestamp
    last_checked_at   TEXT,           -- ISO8601 timestamp
    flagged_at        TEXT,           -- ISO8601 timestamp, null until flagged
    portal_status     TEXT,           -- last known portal status
    error_message     TEXT            -- last error if status=ERROR
);

CREATE TABLE session_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
-- Rows: start_time, flagged_count, failed_count, error_count
```

### Session log format

Each line: `[YYYY-MM-DD HH:MM:SS] LEVEL EVENT details`

```
[2026-10-11 21:32:45] INFO  SESSION_START
[2026-10-11 21:32:47] INFO  COOKIES_OBTAINED from Outlook (session active)
[2026-10-11 21:34:12] INFO  CYCLE_START cycle=1
[2026-10-11 21:34:15] INFO  DISCOVER found=3 new=2 skipped_failed=1
[2026-10-11 21:34:15] INFO  DISCOVERED tracking=384114934492
[2026-10-11 21:34:15] INFO  DISCOVERED tracking=384114933419
[2026-10-11 21:34:18] INFO  PORTAL_FETCH pages=4 records=87 api_calls=4
[2026-10-11 21:34:18] INFO  CONFIRMED tracking=384114934492
[2026-10-11 21:34:18] INFO  PENDING tracking=384114933419 portal_status=PROCESSING
[2026-10-11 21:34:19] INFO  FLAGGED tracking=384114934492
[2026-10-11 21:34:20] INFO  CYCLE_END flagged=1 pending=1 failed=0 errors=0 duration=8.2s
[2026-10-11 21:36:20] INFO  CYCLE_START cycle=2
[2026-10-11 21:36:23] INFO  CONFIRMED tracking=384114933419
[2026-10-11 21:36:24] INFO  FLAGGED tracking=384114933419
[2026-10-11 21:36:24] INFO  CYCLE_END flagged=1 pending=0 failed=0 errors=0 duration=4.1s
[2026-10-11 04:29:55] INFO  SESSION_END (user stopped)
[2026-10-11 04:29:55] INFO  DURATION: 6h 57m 10s
[2026-10-11 04:29:55] INFO  SUMMARY: flagged=187 failed=9 pending=0 errors=2
```

---

## 8. Error Handling Strategy

> **Design principle:** The bot must NEVER silently fail. Every error must be:
> 1. Logged to the session log file with full details
> 2. Shown on the dashboard with a clear description
> 3. If critical: send a Windows desktop notification with actionable instructions
> 4. If recoverable: retry automatically (with limits)
> 5. If not recoverable: pause the affected operation and continue others

### Error categories and responses

---

#### 8.1 Portal API: Token Expired

**Detection:**
```python
response.status_code in [401, 403]
OR response.json().get("success") == False
OR "token" in response.json().get("message", "").lower()
```

**Response:**
- Set `portal_status = "TOKEN_EXPIRED"` in dashboard
- Stop making portal API calls for this cycle
- Send Windows desktop notification:
  ```
  Title: "FedEx Flagger — Portal Token Expired"
  Message: "The portal API token has expired. Open the dashboard at
            http://localhost:5000, paste the new token, and click Save."
  ```
- How to get a new token: Log in to tools.registrarcorp.com → F12 → Network →
  click any request → copy the `token=` value from the URL
- Bot continues scanning inbox (Phase 1) and flagging already-confirmed emails (Phase 3)
- Portal checks (Phase 2) resume automatically once token is updated via dashboard

---

#### 8.2 Portal API: Network Error / Timeout

**Detection:**
```python
requests.exceptions.ConnectionError
requests.exceptions.Timeout (timeout=15 seconds)
requests.exceptions.RequestException
```

**Response:**
- Log: `ERROR PORTAL_NETWORK_ERROR attempt=<N> error=<message>`
- Retry up to 3 times with 5-second delays between retries
- If all 3 retries fail:
  - Send desktop notification: "FedEx Flagger — Portal API unreachable. Check internet connection."
  - Skip Phase 2 for this cycle
  - Continue to Phase 3
  - Try again next full cycle

---

#### 8.3 Portal API: Unexpected Response Format

**Detection:**
```python
response.json()  # raises JSONDecodeError
"data" not in response.json()
```

**Response:**
- Log: `ERROR PORTAL_PARSE_ERROR response=<first 200 chars of response>`
- Skip this cycle's portal check
- Send desktop notification if this happens 3 cycles in a row:
  "Portal API response format has changed. The bot may need updating."

---

#### 8.4 Outlook Session Expired

**Detection:**
- Playwright: page URL contains `login.microsoftonline.com` or `login.microsoft.com`
- requests: HTTP 302 redirect to login URL
- requests: Response body is HTML containing login form instead of JSON
  ```python
  try:
      data = response.json()
  except json.JSONDecodeError:
      if "login" in response.text.lower() or "microsoftonline" in response.text.lower():
          raise OutlookSessionExpiredError()
  ```

**Response:**
- Set `outlook_status = "SESSION_EXPIRED"` on dashboard (big red banner)
- Pause Phases 1 and 3 (cannot read or flag emails)
- Phase 2 (portal) continues if token is still valid
- Send Windows desktop notification:
  ```
  Title: "FedEx Flagger — Outlook Login Required"
  Message: "Your Outlook session has expired. Click here to re-login.
            The bot will resume automatically after login."
  ```
- Dashboard shows a button: [Re-login to Outlook]
- Clicking the button launches Playwright visibly → user logs in → cookies extracted → bot resumes
- Re-login usually takes under 30 seconds

---

#### 8.5 Outlook API: Email Not Found (ErrorItemNotFound)

**Detection:**
```python
response_message["ResponseCode"] == "ErrorItemNotFound"
```

**Cause:** Email was deleted/moved between FindItem and UpdateItem calls.

**Response:**
- Log: `WARN EMAIL_GONE tracking=<N> item_id=<ID>`
- Update DB: `status = GONE`
- Continue processing other emails (not a critical error)
- No notification needed

---

#### 8.6 Outlook API: ChangeKey Mismatch (ErrorChangeKeyRequired)

**Detection:**
```python
response_message["ResponseCode"] == "ErrorChangeKeyRequired"
```

**Cause:** Email was modified (e.g., flagged by someone else) between FindItem and UpdateItem.

**Response:**
- Log: `WARN CHANGEKEY_MISMATCH tracking=<N>. Re-fetching and retrying.`
- Make a GetItem call to fetch the updated ChangeKey
- Retry UpdateItem with the new ChangeKey (one retry only)
- If retry succeeds: mark as FLAGGED, log normally
- If retry fails with another error:
  - Log: `ERROR FLAG_RETRY_FAILED tracking=<N> error=<code>`
  - Update DB: `status = ERROR, error_message = <details>`
  - Show on dashboard: "Failed to flag email <tracking_number> — <reason>"
  - No notification (not critical enough)

---

#### 8.7 Outlook API: Network Error

**Detection:**
```python
requests.exceptions.ConnectionError
requests.exceptions.Timeout
```

**Response:**
- Retry up to 3 times with 5-second delays
- If all retries fail for FindItem (Phase 1): skip this cycle entirely, try next cycle
- If all retries fail for UpdateItem (Phase 3):
  - Leave email status as CONFIRMED in DB (will retry next cycle)
  - Log: `ERROR OUTLOOK_NETWORK_ERROR phase=3 tracking=<N>`
  - Send notification if 3 consecutive cycles fail: "FedEx Flagger — Cannot reach Outlook. Check connection."

---

#### 8.8 Tracking Number Not Found in Email

**Detection:**
```python
match = re.search(r'Tracking Number:\s+(\d+)', preview)
if not match:
    # No tracking number found
```

**Response:**
- Log: `WARN NO_TRACKING_NUMBER item_id=<ID> subject=<subject>`
- Skip this email completely (do not add to DB)
- This should not happen for valid FedEx prior-notice emails
- If this happens frequently, show on dashboard: "Warning: <N> emails missing tracking numbers"

---

#### 8.9 Database Error

**Detection:** `sqlite3.Error` exceptions

**Response:**
- Log: `CRITICAL DB_ERROR error=<message>`
- Send desktop notification: "FedEx Flagger — Database error. Bot stopped. Check logs."
- Stop the bot (database is required for correct operation)
- The user must manually restart the bot

---

#### 8.10 Dashboard / Flask Server Error

**Detection:** `Exception` in Flask route handlers

**Response:**
- Log the error to the session log
- Return HTTP 500 with a clear error message to the browser
- The bot engine continues running (dashboard is separate thread)
- User sees error message in browser: "Dashboard error: <details>"

---

#### 8.11 Consecutive Cycle Failures

If 5 consecutive cycles fail completely (all three phases fail):
- Send desktop notification: "FedEx Flagger — Bot is stuck. Check dashboard for details."
- Pause the bot loop
- Dashboard shows: "Bot paused after 5 consecutive failures. [Retry] [Stop]"

---

### Error display on dashboard

All errors appear in the dashboard's **Alerts** section with:
- 🔴 Red badge for critical errors (session expired, token expired, DB error)
- 🟡 Yellow badge for warnings (email not found, parse errors)
- Clear description of what happened
- Actionable instructions for how to fix it
- Timestamp of when it occurred
- [Dismiss] button to acknowledge

---

## 9. Web Dashboard Specification

**Technology:** Flask (Python), served at `http://localhost:5000`
**Accessible from:** Any browser on the same network using `http://<office-laptop-IP>:5000`

### Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  🚩 FedEx Flagger — Registrar Corp                             │
│                                                                 │
│  ┌─ Bot Status ────────────────────────────────────────────┐   │
│  │  🟢 Running    Session started: 21:32:45               │   │
│  │  Last scan: 43 sec ago | Next scan: in 1 min 17 sec    │   │
│  │  [■ Stop Bot]                                           │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─ Session Summary ───────────────────────────────────────┐   │
│  │  ✅ Flagged: 187  ⏳ Pending: 8  ❌ Failed: 9  ⚠️ Errors: 2│   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─ Alerts ────────────────────────────────────────────────┐   │
│  │  [Only shown when there are active alerts]              │   │
│  │  🔴 Outlook session expired — [Re-login] [Dismiss]      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─ API Token ─────────────────────────────────────────────┐   │
│  │  Portal API: 🟢 Active (last verified: 2 min ago)       │   │
│  │  Outlook:    🟢 Active                                  │   │
│  │                                                         │   │
│  │  Update portal token:                                   │   │
│  │  [paste new token here                           ]      │   │
│  │  [Test Token]  [Save & Apply]   Result: —               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─ Recent Activity ───────────────────────────────────────┐   │
│  │  21:38:21  ✅ Flagged     384114934492                  │   │
│  │  21:38:20  ✅ Flagged     384114933419                  │   │
│  │  21:38:18  ❌ Failed      878432095370 (not rechecking) │   │
│  │  21:36:05  ✅ Flagged     384114884542                  │   │
│  │  21:36:04  ⏳ Pending     384114884531 (PROCESSING)     │   │
│  │  21:34:55  ⚠️ Error       384114885056 (EMAIL_GONE)     │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### API endpoints (Flask routes)

```
GET  /              → Main dashboard page
GET  /api/status    → JSON: bot status, session summary, last cycle info
GET  /api/activity  → JSON: last 50 activity log entries from DB
POST /api/token/test → JSON: test portal token, return {"valid": true/false, "error": null}
POST /api/token/save → JSON: save token to .env, apply immediately
POST /api/bot/stop  → Stop the bot loop
POST /api/bot/start → Start the bot loop
POST /api/relogin   → Trigger Playwright re-login for Outlook
```

### Token update flow

1. User pastes new token in the text field
2. Clicks **Test Token**:
   - Dashboard makes `POST /api/token/test` with the token
   - Server makes a test API call: `GET portal/search?token=<new_token>&max=1`
   - Returns: `{"valid": true}` or `{"valid": false, "error": "Invalid token response"}`
   - Dashboard shows: ✅ Token is valid OR ❌ Token is invalid
3. Clicks **Save & Apply**:
   - Dashboard makes `POST /api/token/save` with the token
   - Server writes new token to `.env` file
   - Server updates `PORTAL_API_TOKEN` in memory (bot picks it up on next cycle)
   - Dashboard shows: ✅ Token saved and applied — bot will use it on next scan

---

## 10. Tech Stack

| Component | Library | Version | Purpose |
|---|---|---|---|
| Language | Python | 3.12+ | Core language |
| Portal status | `requests` | 2.31+ | HTTP calls to portal API |
| Outlook read/flag | `requests` | 2.31+ | HTTP calls to OWA API |
| Outlook login | `playwright` | 1.40+ | One-time browser login per session |
| Web dashboard | `flask` | 3.0+ | Local web UI at localhost:5000 |
| Database | `sqlite3` | built-in | **Zero installation** — built into Python |
| Scheduling | `schedule` | 1.2+ | 2-minute loop |
| Config/secrets | `python-dotenv` | 1.0+ | Read/write .env file (via dashboard only) |
| Desktop alerts | `plyer` | 2.1+ | Windows toast notifications |
| System tray | `pystray` | 0.19+ | Windows system tray icon + menu |
| EXE packaging | `pyinstaller` | 6.0+ | Bundles app into single .exe file |
| Testing | `pytest` | 7.4+ | Unit and integration tests |
| Code quality | `ruff` | 0.1+ | Linting and formatting |
| Date handling | `python-dateutil` | 2.8+ | Date parsing |

**Cost: ₹0 — all open source.**

**Note on SQLite:** SQLite requires zero installation. Python includes it by default.
The bot creates the database file automatically on startup. Users never interact with it directly.

---

## 11. Project Folder Structure

```
Registercorp-project/
│
├── IMPLEMENTATION_PLAN.md        ← THIS FILE — the single source of truth
│
├── src/
│   └── flagger/
│       ├── __init__.py
│       ├── main.py               ← Entry point: starts bot + dashboard + tray icon
│       │                           Launched by the EXE. Opens browser automatically.
│       │
│       ├── bot_engine.py         ← The 2-minute loop: orchestrates phases 1, 2, 3
│       │                           Handles consecutive failure detection and pausing
│       │
│       ├── tray_icon.py          ← Windows system tray icon (pystray)
│       │                           Shows bot status in taskbar
│       │                           Right-click menu: Open Dashboard, Start/Stop, Exit
│       │                           Icon colour: green=running, red=error, yellow=warning
│       │
│       ├── setup_wizard.py       ← First-launch setup detection and wizard flow
│       │                           Detects if portal token is missing/invalid
│       │                           Detects if Outlook session needs setup
│       │                           Redirects dashboard to /setup on first launch
│       │
│       ├── outlook_module.py     ← All Outlook operations:
│       │                           - get_cookies() via Playwright
│       │                           - find_unflagged_fedex_emails() via FindItem API
│       │                           - flag_email(item_id, change_key) via UpdateItem API
│       │                           - detect_session_expiry(response)
│       │
│       ├── portal_module.py      ← All portal operations:
│       │                           - fetch_statuses(date_from, date_to) → dict
│       │                           - detect_token_expiry(response)
│       │                           - paginate through all pages
│       │
│       ├── database.py           ← SQLite operations (zero install — built into Python):
│       │                           - initialize() — wipe and recreate tables on startup
│       │                           - add_email(tracking_number, item_id, change_key)
│       │                           - update_status(tracking_number, new_status)
│       │                           - get_pending() → list
│       │                           - get_confirmed() → list
│       │
│       ├── session_logger.py     ← Per-session log file:
│       │                           - create_session_log() → file path
│       │                           - log(level, event, details)
│       │                           - write_summary()
│       │
│       ├── alerts.py             ← Windows desktop notifications:
│       │                           - notify(title, message, urgency)
│       │                           - All notification templates defined here
│       │
│       ├── config.py             ← Reads/writes .env file:
│       │                           - All settings exposed as typed properties
│       │                           - update_portal_token(token) — writes to .env, hot-reloads
│       │                           - update_setting(key, value) — generic settings update
│       │                           - is_first_launch() → bool (token missing or empty)
│       │
│       └── dashboard/
│           ├── __init__.py
│           ├── app.py            ← Flask app with all routes (runs in background thread)
│           ├── templates/
│           │   ├── index.html    ← Main dashboard (auto-refresh every 5 sec)
│           │   ├── setup.html    ← First-launch setup wizard (3 steps)
│           │   └── settings.html ← Settings page (replaces manual .env editing)
│           └── static/
│               ├── style.css
│               └── dashboard.js
│
├── build/
│   ├── FedExFlagger.spec         ← PyInstaller build spec (EXE config)
│   └── build_exe.py              ← Script to produce FedExFlagger.exe
│
├── assets/
│   └── icon.ico                  ← App icon (used in EXE + system tray)
│
├── tests/
│   ├── conftest.py
│   ├── test_portal.py
│   ├── test_outlook.py
│   ├── test_database.py
│   ├── test_bot_engine.py
│   └── test_dashboard.py
│
├── logs/                         ← Session log files (gitignored)
├── browser_profile/              ← Chrome profile for bot login (gitignored)
├── project-management/           ← Planning documents (no code)
├── .env.example                  ← Shows what settings exist (no real values)
├── .env                          ← ⚠️ NEVER committed — written by dashboard
├── requirements.txt
├── README.md
└── .gitignore
```

---

## 12. Environment Configuration (.env)

> **Important:** Users NEVER edit .env manually.
> The dashboard Settings page reads and writes .env automatically.
> The .env file is a storage mechanism, not a user interface.

### .env.example (commit this — no real values)
```bash
# ============================================================
# FedEx Email Auto-Flagger — Configuration
# This file is managed automatically by the dashboard.
# Do NOT edit manually — use the Settings page at localhost:5000/settings
# NEVER commit .env to Git
# ============================================================

PORTAL_API_TOKEN=
OUTLOOK_MAILBOX_URL=https://outlook.cloud.microsoft/mail/pn@registrarcorp.com/
SENDER_FILTER=myfda@registrarcorp.com
CHECK_INTERVAL_SECONDS=120
API_DATE_RANGE_DAYS=2
DASHBOARD_PORT=5000
DRY_RUN=true
BROWSER_PROFILE_DIR=./browser_profile
CHROME_EXECUTABLE_PATH=
AUTO_START_WINDOWS=false
```

### Settings managed via dashboard (localhost:5000/settings)

| Setting | Default | Description |
|---|---|---|
| Portal API Token | (empty) | Set via Setup Wizard or Token panel |
| Scan interval | 120 sec | How often the bot scans (2 min default) |
| Date range | 2 days | How far back to fetch portal records |
| Dashboard port | 5000 | Web UI port |
| Dry run mode | ON | Toggle to OFF when ready to go live |
| Auto-start with Windows | OFF | Register bot to start on Windows login |

All settings saved automatically to `.env`. Bot picks up changes on next cycle without restart.

---

## 13. Installation Guide

### End-user installation (after EXE is built)

This is what the 6 team members do. No command line, no configuration files.

1. **Install Python 3.12** (one-time, on each laptop)
   - Download from: https://www.python.org/downloads/
   - Run installer → **tick "Add Python to PATH"** → Install Now
   - This is the only manual technical step required

2. **Download `FedExFlagger.exe`** from the shared drive or GitHub Releases

3. **Double-click `FedExFlagger.exe`**
   - First launch: downloads Playwright Chromium automatically (shows progress)
   - Browser opens to `http://localhost:5000` automatically
   - Setup wizard appears (see below)

4. **Complete the setup wizard** (3 steps, all in the browser):

   ```
   Step 1: Portal Token
   ─────────────────────────────────────────────────────
   How to get your token:
     1. Open tools.registrarcorp.com (log in if needed)
     2. Press F12 → click Network tab → click Fetch/XHR
     3. Click any request in the list
     4. Copy the token= value from the Request URL
   
   [Paste token here          ]  [Test Token → ✅ Valid]
   [Next →]

   Step 2: Connect Outlook
   ─────────────────────────────────────────────────────
   [Open Outlook Login Window]
   → A browser window appears
   → Log in to pn@registrarcorp.com
   → Check "Keep me signed in"
   → Browser closes automatically
   → ✅ Outlook connected
   [Next →]

   Step 3: Ready!
   ─────────────────────────────────────────────────────
   ✅ Portal token: Active
   ✅ Outlook: Connected
   Dry run mode: ON (recommended for first day)
   [Start Bot]
   ```

5. **System tray icon appears** 🚩 in the bottom-right taskbar
   - Right-click to open dashboard, stop/start, or exit
   - Bot is now running

6. **After one full shift in dry-run mode:**
   - Check dashboard activity log — verify all decisions look correct
   - Go to Settings → toggle Dry Run to OFF
   - Bot starts actually flagging emails

---

### Developer/build setup (to produce the EXE)

Only needed by the developer who builds and maintains the project.

```cmd
# 1. Clone the project
git clone https://github.com/Dilip-kumar-96/Registercorp-project.git
cd Registercorp-project

# 2. Install all dependencies
pip install -r requirements.txt
playwright install chromium

# 3. Run in development mode (no EXE needed)
python -m flagger.main

# 4. Build the EXE for distribution
python build/build_exe.py
# Output: dist/FedExFlagger.exe
```

---

### Portal token update (when it expires)

1. Log in to `tools.registrarcorp.com`
2. Press F12 → Network → Fetch/XHR → click any request → copy `token=` from URL
3. Open dashboard → paste into token field → **Test Token** → **Save & Apply**
4. Bot resumes immediately

### Outlook re-login (when session expires — every few weeks)

1. Dashboard shows red alert: "Outlook session expired"
2. Click **[Re-login to Outlook]** button on dashboard
3. Browser window opens → log in → check "Keep me signed in" → browser closes
4. Bot resumes automatically

---

## 14. Build Roadmap

### Phase 0 — Project Skeleton
**Goal:** Clean repository with all files committed to GitHub main branch.

Tasks:
- [ ] Rename `master` → `main` on GitHub
- [ ] Create `project-management/` folder with all planning docs
- [ ] Create all source files with proper docstrings (empty implementations)
- [ ] Write `requirements.txt` with pinned versions
- [ ] Write `.env.example`
- [ ] Write `.gitignore` (include: `.env`, `logs/`, `browser_profile/`, `*.db`, `dist/`, `build/`)
- [ ] Write root `README.md` with installation instructions
- [ ] Create `assets/icon.ico` (app icon)
- [ ] Create `build/FedExFlagger.spec` (PyInstaller config)
- [ ] First commit and push to `main`

---

### Phase 1 — Portal Module
**Goal:** `portal_module.py` correctly fetches and parses statuses.

Tasks:
- [ ] Implement `fetch_statuses(date_from, date_to) -> dict[str, str]`
- [ ] Implement pagination with `searchAfter`
- [ ] Implement token expiry detection
- [ ] Implement retry logic (3 attempts, 5-second delay)
- [ ] Write `tests/test_portal.py`:
  - [ ] Test CONFIRMED response → returns "CONFIRMED"
  - [ ] Test FAILED response → returns "FAILED"
  - [ ] Test SUBMITTED response → returns "SUBMITTED"
  - [ ] Test PROCESSING response → returns "PROCESSING"
  - [ ] Test token expired (401) → raises `PortalTokenExpiredError`
  - [ ] Test network error → raises `PortalNetworkError` after 3 retries
  - [ ] Test pagination → fetches all pages and merges results
  - [ ] Test bad JSON response → raises `PortalParseError`

**Done when:** `pytest tests/test_portal.py` passes, 100% coverage of all error paths.

---

### Phase 2 — Database and Session Logger
**Goal:** State machine and logging work correctly.

Tasks:
- [ ] Implement `database.py`: all CRUD operations
- [ ] Implement wipe-on-initialize behavior
- [ ] Implement `session_logger.py`: timestamped log file per session
- [ ] Write `tests/test_database.py`:
  - [ ] Test all status transitions
  - [ ] Test that `initialize()` wipes previous data
  - [ ] Test concurrent access (won't happen in practice but good to verify)

**Done when:** All tests pass. Log files are human-readable and complete.

---

### Phase 3 — Outlook Module
**Goal:** `outlook_module.py` can read emails and flag them on the office laptop.

Tasks:
- [ ] Implement `get_cookies()` using Playwright
- [ ] Implement `find_unflagged_fedex_emails()` using FindItem API
- [ ] Implement tracking number extraction with regex
- [ ] Implement `flag_email(item_id, change_key)` using UpdateItem API
- [ ] Implement session expiry detection
- [ ] Implement ChangeKey mismatch retry
- [ ] Write `tests/test_outlook.py` with mocked HTTP responses
- [ ] Test on office laptop with real Outlook (dry-run mode only)

**Done when:** Bot correctly lists all unflagged FedEx emails and tracking numbers.

---

### Phase 4 — Bot Engine (Dry Run)
**Goal:** Full 2-minute loop works end-to-end. DRY_RUN=true.

Tasks:
- [ ] Implement `bot_engine.py`: phases 1, 2, 3 in sequence
- [ ] Implement consecutive failure detection (5 failures → pause + alert)
- [ ] Write `tests/test_bot_engine.py` with all modules mocked
- [ ] Run dry-run for one full shift (8 hours)
- [ ] Compare dry-run log against what a human would have done — must match 100%

**Done when:** After one full shift, every email is correctly identified with zero false positives.

---

### Phase 5 — Web Dashboard + Setup Wizard + System Tray
**Goal:** Full application experience — EXE, tray icon, setup wizard, settings page.

Tasks:
- [ ] Implement `dashboard/app.py` with all routes
- [ ] Build `index.html`: live status, activity feed, system status panel, alerts panel
- [ ] Build `setup.html`: 3-step first-launch wizard (token → outlook login → start)
- [ ] Build `settings.html`: all settings editable in browser (replaces .env editing)
- [ ] System status panel on dashboard:
  - Portal API: 🟢 Active / 🔴 Token Expired + [Update Token] link
  - Outlook: 🟢 Active / 🔴 Session Expired + [Re-login to Outlook] button
  - Bot: 🟢 Running / ⏸ Paused / 🔴 Error
- [ ] Implement token test endpoint (`POST /api/token/test`)
- [ ] Implement token save endpoint (`POST /api/token/save`) → writes to .env, hot-reloads
- [ ] Implement re-login endpoint (`POST /api/relogin`) → triggers Playwright login flow
- [ ] Implement settings save (`POST /api/settings`) → writes all settings to .env
- [ ] Implement `tray_icon.py`: pystray tray icon with status colours and menu
- [ ] Implement `setup_wizard.py`: first launch detection, redirect to /setup
- [ ] Auto-start with Windows: Settings toggle writes/removes Windows registry entry
- [ ] Auto-refresh dashboard every 5 seconds via JavaScript polling
- [ ] Build EXE: `python build/build_exe.py` → `dist/FedExFlagger.exe`
- [ ] Test EXE on a clean Windows machine (no Python installed)
- [ ] Write `tests/test_dashboard.py`

**Done when:** Double-clicking FedExFlagger.exe completes full setup and starts bot with zero terminal use.

---

### Phase 6 — Go Live
**Goal:** DRY_RUN=false. First real flagging run.

Tasks:
- [ ] Set DRY_RUN=false
- [ ] Run for one full shift with someone watching
- [ ] Verify every flagged email is confirmed on portal
- [ ] Verify no incorrect flags
- [ ] Verify FAILED emails are never flagged

**Done when:** Zero mistakes in a full shift.

---

### Phase 7 — Harden and Stabilize
**Goal:** Bot runs reliably without supervision.

Tasks:
- [ ] All error handlers tested (token expiry, session expiry, network errors)
- [ ] All desktop notifications verified on Windows
- [ ] Optional: Windows Task Scheduler auto-start on user login
- [ ] Write maintenance guide in `project-management/`
- [ ] Tag release: `v1.0.0`

---

## 15. Testing Strategy

### Unit tests (tests/ directory)
- All modules tested with mocked external calls (no real API calls in tests)
- Mock library: `unittest.mock` (built-in Python)
- Every error path must have a test — not just the happy path

### Integration tests
- `test_bot_engine.py` tests the full cycle with all modules mocked
- Verifies correct state transitions in SQLite

### Manual tests on office laptop (required before go-live)
1. **FindItem test:** Run `python -m flagger.test_finditem` → prints all emails found
2. **Portal test:** Run `python -m flagger.test_portal` → prints statuses for 5 tracking numbers
3. **Flag test:** Run `python -m flagger.test_flag` → flags one specific test email (dry-run first!)
4. **Full dry-run:** Run for 8 hours → review session log against manual work

### Regression test after any code change
- Run `pytest` → all tests must pass before merging to `main`

---

## 16. Git Workflow

### Branch strategy
- `main` — always working, tested code. Never commit directly.
- Feature branches: `feat/portal-module`, `feat/outlook-module`, `fix/changekey-retry`, `docs/update-plan`

### Workflow per task
```
git checkout main && git pull
git checkout -b feat/<task-name>
# ... write code + tests ...
pytest  # must pass
git add .
git commit -m "feat: <description>"
git push origin feat/<task-name>
# Open Pull Request on GitHub → review → squash merge → delete branch
```

### Commit message format
```
feat: add portal bulk-fetch with searchAfter pagination
fix: retry UpdateItem on ErrorChangeKeyRequired
docs: update implementation plan with error handling strategy
test: add portal token expiry test
chore: pin dependency versions in requirements.txt
```

### Release tags
| Tag | When |
|---|---|
| `v0.1.0` | Portal module tested |
| `v0.2.0` | Outlook module tested on office laptop |
| `v0.5.0` | Dry-run works for full shift |
| `v0.9.0` | Dashboard complete |
| `v1.0.0` | Live, stable, running for one week |

### Files never committed
```gitignore
.env                  # real API token
logs/                 # session log files
browser_profile/      # Chrome profile with saved login
*.db                  # SQLite database files
__pycache__/
*.pyc
.pytest_cache/
```

---

## 17. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Portal API token expires | Certain (weeks) | Bot can't check statuses | Dashboard shows expiry + desktop alert. Update via dashboard UI in < 2 minutes |
| Outlook session expires | Certain (weeks) | Bot can't read or flag emails | Desktop alert + re-login button on dashboard. Playwright re-logins in 30 seconds |
| Laptop forcibly shut down | Possible | Session data lost | SQLite is crash-safe. Emails still in inbox, rediscovered on next startup |
| OWA API request format changes | Low | Bot can't read/flag emails | Alert fires. All selectors isolated in `outlook_module.py` — one file to fix |
| Portal API URL or structure changes | Very low | Status checks fail | API error detection → dashboard alert. New endpoint found via F12 |
| API rate limit hit | Unknown | Throttled or blocked | Reduce cycle to 3 min. If blocked: add delays between requests |
| ChangeKey conflicts (colleague flags same email) | Low | UpdateItem fails | ErrorChangeKeyRequired handled: re-fetch ChangeKey and retry once |
| IT policy disallows automation | Low | Must stop bot | Plan to disclose once stable. Bot only reads mail + adds flags — very low impact |
| "Retry Failed" on portal changes status after FAILED | Rare | Bot misses re-confirmation | Caught at next session's fresh scan |
| Email preview field format changes | Very low | Tracking number extraction fails | Alert fires with "missing tracking number" warning |
| findItem returns incomplete Preview | Possible | Can't extract tracking number | Log warning, skip email, continue |

---

## 18. Key Decisions Log

### Decision 1 — Use portal REST API, not browser scraping
**Date:** 2026-10-10
**Decision:** Use the direct AWS API Gateway endpoint instead of Playwright browser automation for portal status checking.
**Evidence:** F12 Network tab revealed: `GET https://ff4tbdztak.execute-api.us-east-1.amazonaws.com/prod/prior-notice/search?token=...`
**Benefit:** No browser needed for portal. Static token authentication. 20 lines of Python.
**Locked:** ✅ Yes

---

### Decision 2 — Use OWA service.svc API, not Playwright, for Outlook read/flag
**Date:** 2026-10-11
**Decision:** Use Microsoft Exchange OWA API (`service.svc`) for reading emails and flagging. Playwright only for initial login cookie extraction.
**Evidence:**
- FindItem (`service.svc?action=FindItem`): Returns all inbox emails in JSON. `Preview` field contains tracking number. `Flag.FlagStatus` shows flag state. `ItemId` contains Id and ChangeKey for operations.
- UpdateItem (`service.svc?action=UpdateItem`): Successfully flags email. Confirmed via GetItem response showing `"FlagStatus": "Flagged"`.
**Benefit:** No browser running during normal operation. Dramatically faster and simpler.
**Locked:** ✅ Yes

---

### Decision 3 — Fresh database on every startup
**Date:** 2026-10-11
**Decision:** SQLite database is wiped completely on every bot startup.
**Reason:** Shift is well-defined (8:30 PM – 4:30 AM IST). Almost all emails resolve within minutes of arrival. Any unresolved emails at shutdown are handled by the morning shift or rediscovered at next startup. Persistence between sessions adds complexity with no benefit.
**Edge case:** Emails still in inbox from previous session are rediscovered in the first scan.
**Locked:** ✅ Yes

---

### Decision 4 — Per-session log files
**Date:** 2026-10-11
**Decision:** Each bot startup creates a new log file: `logs/session_YYYY-MM-DD_HH-MM-SS.log`
**Reason:** User may start/stop multiple times per shift. Each run needs its own audit trail. Even a crash produces a partial but complete and readable log.
**Locked:** ✅ Yes

---

### Decision 5 — FAILED emails ignored for the entire session
**Date:** 2026-10-11
**Decision:** Once `bot_status = FAILED` in DB, the email is never re-checked during that session.
**Reason:** FAILED status means the portal filing failed. Rechecking wastes API calls.
**Exception:** "Retry Failed" on portal → status changes → caught at next session's fresh scan.
**Locked:** ✅ Yes

---

### Decision 6 — Bulk-fetch portal statuses by date range
**Date:** 2026-10-10
**Decision:** Fetch all portal records for the last N days in bulk (paginated), build a lookup table, match all pending emails against it. Do NOT make one API call per tracking number.
**Reason:** With ~200 emails/day, per-email calls would be 200 calls/cycle. Bulk fetch is ~8 calls/cycle regardless of email count.
**Locked:** ✅ Yes

---

### Decision 7 — Web dashboard for all management — no manual config files
**Date:** 2026-10-11
**Decision:** Flask dashboard at `localhost:5000` with: first-launch setup wizard, portal token management, Outlook re-login button, settings page, system status, activity log. Users never edit `.env` manually — dashboard writes it automatically.
**Reason:** Portal token expires periodically. Outlook session expires periodically. Manual `.env` editing is error-prone and not suitable for a team of non-developers. Dashboard makes everything a 1–3 click operation.
**Locked:** ✅ Yes

---

### Decision 10 — EXE packaging with system tray icon
**Date:** 2026-10-11
**Decision:** Package the entire application as `FedExFlagger.exe` using PyInstaller. Add a Windows system tray icon using `pystray`. Browser opens automatically to the dashboard on startup.
**Reason:** The 6 team members are non-developers. Running `python -m flagger.main` from a terminal is not acceptable for a production tool. The application must feel and behave like a proper Windows application.
**Implementation:** PyInstaller bundles Python + all dependencies. First-run downloads Playwright Chromium automatically. EXE distributed via shared drive or GitHub Releases.
**Locked:** ✅ Yes

---

### Decision 11 — First-launch setup wizard
**Date:** 2026-10-11
**Decision:** On first launch (when portal token is missing), dashboard redirects to `/setup` which walks the user through: (1) paste and test portal token, (2) log in to Outlook, (3) start bot. No manual configuration required.
**Reason:** Team members should not need to know what an `.env` file is or how to edit one.
**Locked:** ✅ Yes

---

### Decision 8 — 2-minute check interval
**Date:** 2026-10-11
**Decision:** Main scan loop runs every 2 minutes.
**Reason:** Status typically confirms in under 1 minute but sometimes takes 5–15 minutes. 2 minutes balances responsiveness with giving enough time for the previous cycle to complete. FindItem + portal API + UpdateItem typically completes in 8–15 seconds per cycle.
**Adjustable:** Via `CHECK_INTERVAL_SECONDS` in `.env`

---

### Decision 9 — DRY_RUN mode
**Date:** 2026-10-11
**Decision:** `DRY_RUN=true` in `.env` during testing. Bot logs all decisions but does not actually flag.
**Reason:** Validate bot decisions for a full shift before trusting it to actually modify emails. Prevents accidental mass-flagging during testing.
**Locked:** ✅ Yes (always start with DRY_RUN=true)
