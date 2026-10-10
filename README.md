# FedEx Email Auto-Flagger

A Python background application that automatically monitors a shared Microsoft Outlook inbox, checks the status of FedEx prior-notice filings on the Registrar Admin portal, and flags emails whose status is **Confirmed**.

## How It Works

1. Reads the shared Outlook inbox via the OWA internal API (no browser during normal operation)
2. Extracts tracking numbers from FedEx prior-notice emails
3. Checks each tracking number's status on the Registrar Admin portal REST API
4. Adds a red flag to emails with status **CONFIRMED**
5. Re-checks SUBMITTED/PROCESSING emails every 2 minutes
6. Ignores FAILED emails for the entire session

## Installation (End Users)

1. **Install Python 3.12** from [python.org](https://www.python.org/downloads/) — tick **"Add Python to PATH"**
2. **Download `FedExFlagger.exe`** from the [Releases](https://github.com/Dilip-kumar-96/Registercorp-project/releases) page
3. **Double-click `FedExFlagger.exe`** — browser opens automatically to the dashboard
4. **Complete the Setup Wizard** (3 steps — portal token, Outlook login, start bot)
5. A 🚩 icon appears in the system tray — the bot is running

## Developer Setup

```bash
git clone https://github.com/Dilip-kumar-96/Registercorp-project.git
cd Registercorp-project
pip install -r requirements.txt
playwright install chromium
cd src
python -m flagger.main
```

Open `http://localhost:5000` in your browser.

## Building the EXE

```bash
python build/build_exe.py
# Output: dist/FedExFlagger.exe
```

## Project Structure

```
src/flagger/          Core application code
  main.py             Entry point
  bot_engine.py       2-minute scan loop
  outlook_module.py   Outlook OWA API (FindItem, UpdateItem)
  portal_module.py    Registrar Admin portal API
  database.py         SQLite session state
  session_logger.py   Per-session log files
  dashboard/          Flask web UI (localhost:5000)
tests/                Unit and integration tests
logs/                 Session log files (gitignored)
IMPLEMENTATION_PLAN.md Complete technical documentation
```

## Documentation

See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) for the complete technical specification, API details, architecture, and build roadmap.
