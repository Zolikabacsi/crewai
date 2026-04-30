# Office Assistant Agent — Design Spec

**Date:** 2026-04-28
**Author:** Claude (brainstorming)
**Status:** Draft

---

## Overview

The `OfficeAssistant` agent is a dual-mode crewAI agent that:

1. **Answers questions** on demand about calendar, email, and company documents — standing alone or as part of the business evaluator crew
2. **Runs a daily sync** that checks a Google Drive folder for new files, pulls them into `Aestas Vault/`, and runs the ingest workflow per CLAUDE.md schema

---

## Agent: `OfficeAssistant`

### Role & Goal

- **Role:** Office & Calendar Assistant
- **Goal:** Provide accurate, real-time answers about your schedule, email context, and company documents. Maintain vault sync with Drive.
- **Backstory:** You are a diligent executive assistant with access to Google Calendar, Gmail, and the company document vault. You answer questions precisely, maintain strict privacy, and run a daily check to keep the vault up to date with new Drive files.

### LLM

Same `get_llm()` as existing agents (MiniMax-M2.7 via custom endpoint).

---

## Tools (5)

| Tool | Action | Source |
|---|---|---|
| `CalendarTool` | List today's/week's events, get event details | `gws calendar events list` |
| `EmailSearchTool` | Search inbox (sender, subject, date), read email body | `gws gmail users messages list/get` |
| `VaultSearchTool` | Full-text search across vault files | `~/srv/vault` (FS grep) |
| `VaultReadTool` | Read specific document content | `~/srv/vault` (FS read) |
| `DriveSyncTool` | List Drive folder, download new files to vault | `gws drive files list/get` |

### Tool Implementation Notes

- All `gws` calls use the existing `~/bin/gws` CLI wrapper, invoked via `subprocess.run()`
- Vault tools operate on `~/srv/vault/` — path is configurable via env var `VAULT_ROOT`
- `DriveSyncTool` targets the folder `Aestas Group/Aestras Healthcare Ltd` — configurable via `DRIVE_SYNC_FOLDER_ID`
- Drive sync state is persisted in `~/.claude/office_assistant_last_sync.json` (last known file list)
- Email tool is read-only (no send/delete)

---

## Mode 1: On-Demand Query

You call the crew with a question. The agent decides which tools to use and returns a direct answer.

Example queries:
- *"What's on my calendar Thursday?"*
- *"Any emails from my accountant this week?"*
- *"What does Q1 budget say about R&D?"*
- *"Check for new Drive files"*

---

## Mode 2: Integrated Crew Agent

Other agents (e.g. `FinancialAnalyst`) have `OfficeAssistant` in their context and delegate tool calls to it:

> *"Assistant, search the vault for 'Q1 budget R&D' and tell me what's on my calendar Thursday"*

The `OfficeAssistant` executes the delegated task and returns results. Other agents do not get direct Drive/email/calendar tools — they go through `OfficeAssistant` to maintain clear boundaries.

---

## Mode 3: Daily Drive Sync (Background Job)

A cron-triggered workflow (separate from crew execution):

```
1. List all files in Drive folder "Aestas Group/Aestras Healthcare Ltd"
2. Compare against last known state (stored in ~/.claude/office_assistant_last_sync.json)
3. For each new file:
   a. Download to ~/srv/vault/Aestas Vault/raw/
   b. Create wiki/sources/[name].md summary
   c. Update wiki/entities/ and wiki/concepts/ pages
   d. Update meta/index.md
   e. Append to meta/log.md
4. Save new file list as last_sync state
```

The sync can also be triggered on demand: *"Check for new Drive files"*

### Vault Ingest Workflow (per CLAUDE.md)

For each new file dropped into `Aestas Vault/raw/`:

1. Create `Aestas Vault/wiki/sources/[name].md` with frontmatter + 2-3 sentence summary
2. Update or create `Aestas Vault/wiki/entities/` pages for named entities (people, companies)
3. Update or create `Aestas Vault/wiki/concepts/` pages for topic keywords
4. Update `Aestas Vault/meta/index.md` catalog entry
5. Append `## [YYYY-MM-DD] ingest | filename` to `Aestas Vault/meta/log.md`

### Scheduling

- Cron: daily at 08:00 local time (`0 8 * * *`)
- Stored in `.claude/scheduled_tasks.json` (durable)
- Auto-expires after 7 days — requires re-setup (or move to a persistent daemon)

---

## File Structure (new files)

```
srv/crewai/src/
├── agents/
│   ├── __init__.py          # Add OfficeAssistant, update get_all_agents
│   └── office_assistant.py  # New — OfficeAssistant agent + tools
├── tasks/
│   ├── __init__.py          # Add sync_drive_task
│   └── office_tasks.py      # New — task definitions
└── tools/
    ├── __init__.py          # Export new tools
    ├── calendar_tool.py     # New
    ├── email_tool.py        # New
    ├── vault_search_tool.py # New
    ├── vault_read_tool.py   # New
    └── drive_sync_tool.py   # New

srv/crewai/scripts/
└── daily_sync.py           # New — standalone sync script (for cron)
```

---

## Dependencies

- `gws` CLI at `~/bin/gws` (existing)
- Vault at `~/srv/vault/` (existing)
- Python: `crewai`, `crewai_tools`, `subprocess`, `pathlib`

---

## Config Env Vars

| Var | Default | Description |
|---|---|---|
| `VAULT_ROOT` | `~/srv/vault` | Root of vault folder |
| `DRIVE_SYNC_FOLDER` | `Aestas Group/Aestras Healthcare Ltd` | Drive folder to monitor |
| `ANTHROPIC_AUTH_TOKEN` | (from config.py) | LLM API key |
| `ANTHROPIC_BASE_URL` | (from config.py) | LLM endpoint |

---

## Edge Cases

- **File already exists in vault:** Skip download, log as already present
- **Sync fails mid-way:** Partial state is fine; next run re-compares and picks up from last state
- **Drive file is binary (PDF/image):** Download to raw/ as-is; skip wiki summarization (ingest step 1 creates stub, LLM summarizes on next query)
- **No new files:** Sync logs "No new files" and exits cleanly
- **Email search returns 0 results:** Return empty state message, not an error

---

## Scope Boundaries

- Email: read-only, no send/forward/delete
- Drive sync: folder-specific only, no broad Drive access
- Vault: only `Aestas Vault/` for sync; both vaults searchable for on-demand queries
- Daily sync: scheduled job, not a crew task

---

## AI Council: Additional Partners to Wire Up

The following partner prompt files exist in `ai_council/prompts/` but have no corresponding agent class. Each should be wired up as a full `Agent` class following the same pattern as existing council agents.

| Agent Class | Prompt File | Role |
|---|---|---|
| `ContentStrategyPartner` | `CONTENT_STRATEGY_PARTNER_PROMPT.md` | Content strategy guidance |
| `CustomerPartner` | `CUSTOMER_PARTNER_STRATEGIC_THINKING.md` | Customer perspective and validation |
| `DemandGenPartner` | `DEMAND_GEN_STRATEGY_PARTNER_PROMPT.md` | Demand generation and growth |
| `FirstPrinciplesPartner` | `FIRST_PRINCIPLES_PARTNER_Strategic_Prompt.md` | First-principles reasoning |
| `HeadOfProductPartner` | `HEAD_OF_PRODUCT_PARTNER_PROMPT.md` | Product strategy and roadmap |
| `StartupGTMPartner` | `StartupGTM_AI_Partners_Council_System.md` | Go-to-market strategy |

### Implementation

- Each agent follows the same pattern as `DevilsAdvocatePartner` etc.
- `load_prompt()` is used to load the prompt file content as `backstory`
- `get_council_agents()` in `ai_council/src/agents/agents.py` is updated to include all 6
- `get_core_agents()` remains unchanged (still returns 4 essential agents)
- No new tools needed for these agents (they use `FileReadTool` like existing partners)