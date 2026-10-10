# Fresh Laptop Setup & Installation Guide

> **Target Audience:** Any team member or operator setting up the FedEx Email Auto-Flagger on a fresh Windows work laptop. No developer knowledge or command-line experience required.

---

## Quick Setup Summary (5-Minute Overview)

1. **Install Python 3.12** (ensure "Add python.exe to PATH" is checked).
2. **Download or copy `FedExFlagger.exe`** to your laptop (e.g. `C:\FedExFlagger\`).
3. **Double-click `FedExFlagger.exe`** — opens `http://localhost:5000` in your browser.
4. **Complete the 3-step Setup Wizard** (Paste Portal Token &rarr; Log in to Outlook &rarr; Start Bot).
5. Look for the red flag icon (**🚩**) in your Windows system tray. The bot is now running!

---

## Detailed Step-by-Step Instructions

### Step 1: Install Python 3.12

The bot engine requires Python 3.12+ runtime on Windows.

1. Open your browser and go to the official Python download page:
   [https://www.python.org/downloads/](https://www.python.org/downloads/)
2. Download the latest **Python 3.12.x Windows installer (64-bit)**.
3. Run the downloaded `.exe` installer.
4. ⚠️ **CRITICAL STEP:** On the very first screen of the installer, check the box at the bottom:
   ```
   ☑ Add python.exe to PATH
   ```
   *(If you skip this, Windows will not recognize Python commands!)*
5. Click **Install Now**.
6. When finished, click **Close**.
7. *(Optional verification)*: Press `Win + R`, type `cmd`, press Enter, and type `python --version`. It should display `Python 3.12.x`.

---

### Step 2: Download & Place the Application

1. Download the latest `FedExFlagger.exe` (or obtain the folder from your team's shared drive / GitHub Releases).
2. Create a dedicated folder on your laptop, for example:
   ```
   C:\FedExFlagger\
   ```
3. Place `FedExFlagger.exe` inside this folder.
   *(Optional)*: Right-click `FedExFlagger.exe` &rarr; **Send to** &rarr; **Desktop (create shortcut)** for easy daily access.

> **Note on Databases:** You do **NOT** need to install MySQL, PostgreSQL, or any database software! The application includes an embedded SQLite engine that creates and manages its own database automatically.

---

### Step 3: Launch the Application

1. Double-click **`FedExFlagger.exe`**.
2. **First-Time Launch (One-time only):**
   - The application will automatically check for and install the Playwright Chromium browser component (~130 MB).
   - This takes about 30–60 seconds depending on your internet connection.
3. Once ready, your default web browser (Chrome or Edge) will **automatically open** to:
   ```
   http://localhost:5000
   ```
4. You will also see a red flag icon (**🚩**) appear in your Windows System Tray (near the clock in the bottom-right taskbar).

---

### Step 4: Complete the First-Time Setup Wizard

When you open `http://localhost:5000` for the first time, the **Setup Wizard** will appear to guide you through connecting your accounts.

```
┌───────────────────────────────────────────────────────────┐
│                    FedEx Email Flagger                    │
│                      SETUP WIZARD                         │
│                                                           │
│   [ Step 1: Portal Token ] ──> [ Step 2: Outlook ] ──> [ Done ]  │
└───────────────────────────────────────────────────────────┘
```

#### Step 4.1: Connect Registrar Admin Portal (Step 1 of 3)

The bot needs permission to query shipment status from the Registrar Admin portal.

1. In your browser, log in to the Registrar Portal:
   `https://tools.registrarcorp.com`
2. Press **`F12`** on your keyboard (or right-click anywhere on the page and select **Inspect**).
3. Click on the **Network** tab at the top of the developer panel.
4. Click on the **Fetch/XHR** filter button.
5. Refresh the page or click on any search/item in the portal.
6. In the list of network requests, click on any request.
7. Under the **Headers** tab, inspect the **Request URL**. Look for `token=` followed by a long alphanumeric string:
   ```text
   https://ff4tbdztak.execute-api.us-east-1.amazonaws.com/prod/prior-notice/search?token=ABC123XYZ456...
   ```
8. Copy the value after `token=` (the long string).
9. Switch back to the Setup Wizard tab (`http://localhost:5000`).
10. Paste the string into the **Portal Token** field.
11. Click **Test Connection**.
    - If valid, a green message will appear: *"Portal connection successful!"*
12. Click **Next Step**.

---

#### Step 4.2: Connect Outlook Shared Mailbox (Step 2 of 3)

The bot accesses `pn@registrarcorp.com` using standard web session cookies. You do not need to type passwords into config files.

1. On Step 2 of the wizard, click **"Open Outlook Login Window"**.
2. A dedicated browser window will open to Microsoft Office 365 sign-in for `pn@registrarcorp.com`.
3. Enter your Office 365 credentials.
4. ⚠️ **IMPORTANT:** When prompted with **"Stay signed in?"**, click **"Yes"**.
5. Once your Outlook mailbox finishes loading, the login window will **automatically close**.
6. The Setup Wizard will show:
   ```
   ✅ Outlook session captured successfully!
   ```
7. Click **Next Step**.

---

#### Step 4.3: Start the Bot (Step 3 of 3)

1. Review the configuration summary:
   - Portal API: Connected
   - Outlook Inbox: `pn@registrarcorp.com`
   - Initial Mode: **Dry Run Mode (Safe Preview)**
2. Click **Start Bot**.
3. You will be redirected to the **Live Dashboard**.

---

## Daily Operation & Maintenance

### Do I Need to Enter User ID / Password Every Day?
- **NO.**
- **Outlook Session:** Microsoft session cookies persist across restarts. You only need to re-login once every few weeks when Microsoft expires the token.
- **Portal Token:** Stored securely and remains valid until changed by the administrator.

### What Happens When a Session Expires?
1. **Outlook Expiry:**
   - A Windows toast notification will pop up: *"Outlook session expired. Please re-login."*
   - A red alert bar will appear at the top of the dashboard.
   - Simply click the **"Re-login to Outlook"** button on the dashboard, complete login once, and the bot resumes automatically.
2. **Portal Token Expiry:**
   - The dashboard will show an alert: *"Portal token invalid or expired (HTTP 401)"*.
   - Obtain a fresh token using Step 4.1 above, navigate to **Settings** (`http://localhost:5000/settings`), paste the new token, and click **Save & Apply**.

---

## Testing with Dry Run Mode (Recommended First Shift)

By default, the bot starts in **Dry Run Mode**:
- It reads emails from `pn@registrarcorp.com`.
- It queries the portal for each tracking number.
- It displays all actions in real-time on the Dashboard table.
- **It does NOT actually apply flags in Outlook.**

### Verifying Before Going Live:
1. Let the bot run in Dry Run mode for **one full shift**.
2. Review the Dashboard and logs (`logs/session_YYYYMMDD_HHMMSS.log`).
3. Confirm that emails with status **CONFIRMED** are marked for flagging as expected.
4. When you are ready for the bot to flag real emails:
   - Go to the Dashboard &rarr; Click **Settings**.
   - Toggle **Dry Run Mode** to **OFF**.
   - Click **Save & Apply**.
   - The bot is now live!

---

## Controlling the Bot (System Tray & Dashboard)

### System Tray Icon (Bottom-Right Taskbar):
- **Right-click the 🚩 icon:**
  - **Open Dashboard:** Opens `http://localhost:5000` in your default browser.
  - **Pause / Resume:** Temporarily pause the 2-minute scanning loop.
  - **Exit:** Shuts down the background service cleanly.

### Dashboard Actions (`http://localhost:5000`):
- **Pause / Resume Bot:** Pause without closing the application.
- **Scan Now:** Immediately trigger a scan without waiting for the 2-minute timer.
- **Settings:** Update scan intervals, portal token, or Dry Run mode.
- **View Logs:** Read full session activity directly in the UI.

---

## Developer / Command-Line Setup (Alternative)

If you are a developer running from the source code instead of using `FedExFlagger.exe`:

```bash
# 1. Clone the repository
git clone https://github.com/Dilip-kumar-96/Registercorp-project.git
cd Registercorp-project

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install Playwright browser
playwright install chromium

# 4. Start the application
cd src
python -m flagger.main
```

To build a standalone `.exe`:
```bash
python build/build_exe.py
# Executable created at: dist/FedExFlagger.exe
```

---
---

# Project Management & Discovery Documentation

This section contains all planning and discovery documents for the FedEx Email Auto-Flagger project.

## Contents

| Document | Description |
|---|---|
| `../IMPLEMENTATION_PLAN.md` | **Primary document** — Complete technical spec, API details, architecture, build roadmap |

## Key Decisions

All key decisions are documented in Section 18 of the Implementation Plan.

## API Discovery

- **Portal API:** Discovered via F12 Network tab on `tools.registrarcorp.com`
- **Outlook FindItem:** Discovered via F12 on Outlook Web — `service.svc?action=FindItem`
- **Outlook UpdateItem:** Discovered by flagging an email and capturing the request — `service.svc?action=UpdateItem`
- **Authentication:** Portal uses static token; Outlook uses browser session cookies extracted once per session via Playwright
