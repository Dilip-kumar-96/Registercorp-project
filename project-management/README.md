# Project Management

This folder contains all planning and discovery documents for the FedEx Email Auto-Flagger project.

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
