# Side Hustle Scout Agent — Design Spec

**Date:** 2026-04-28
**Author:** Claude (brainstorming)
**Status:** Draft

---

## Overview

A `SideHustleScout` agent continuously monitors web sources and industry reports from the vault, evaluates opportunities with mandatory consultation of CoachPartner and DevilsAdvocatePartner, and routes findings via Slack — immediate alerts for high-value "extraordinary" finds, daily digest for everything else.

---

## Agent: `SideHustleScout`

### Role & Goal

- **Role:** Side Hustle Opportunity Scout
- **Goal:** Continuously identify, evaluate, and surface viable side income opportunities that match the user's profile and capabilities.
- **Backstory:** You are a relentless business development analyst who monitors freelance markets, startup communities, and industry trends to surface side hustle opportunities. You evaluate each opportunity rigorously, consult the right experts before surfacing anything, and only escalate truly extraordinary finds. You are based in Europe and understand both EU and non-EU market dynamics.

### LLM

Same `get_llm()` as existing agents (MiniMax-M2.7 via custom endpoint).

---

## Tools (3)

| Tool | Purpose | Source |
|---|---|---|
| `WebScraperTool` | Scrape Reddit, IndieHackers, Product Hunt, freelance boards | `requests` + `BeautifulSoup` |
| `IndustryReportTool` | Search and read industry reports from vault | `~/srv/vault` FS search |
| `OpportunityStorageTool` | Log opportunities to a local JSON store | JSON file at `~/.claude/side_hustle_opportunities.json` |

### Tool Implementation Notes

- All web scraping uses `requests` + `BeautifulSoup` (Python stdlib + pip package)
- Vault tools operate on `~/srv/vault/` — path configurable via `VAULT_ROOT`
- Opportunity store: `~/.claude/side_hustle_opportunities.json` — JSON array of opportunity records
- Slack uses incoming webhook — no bot user needed for notifications

---

## Workflow: Daily Scan + Routing

```
1. SCAN
   Run WebScraperTool against configured sources:
   - r/startups, r/Entrepreneur, r/sidehustle (Reddit)
   - IndieHackers "monetize" posts
   - Product Hunt trending products with monetization signals
   - Upwork/Fiverr trending categories

   Run IndustryReportTool to cross-reference vault reports for:
   - Growing market segments
   - Emerging customer needs
   - Skill gaps in your industry

2. EVALUATE
   Score each opportunity on:
   - Income potential (€X/month)
   - Time required (hours/week)
   - Startup cost (€X)
   - Skill match (low/medium/high)
   - Market timing (early/growing/mature)

3. CONSULT (mandatory for every opportunity)
   - CoachPartner: "Is this aligned with founder mindset and sustainable growth?"
   - DevilsAdvocatePartner: "What could go wrong? What's the worst-case scenario?"

   Selective additional consultation (scout decides):
   - CFOPartner for financial validation
   - IntelligencePartner for market size check
   - DemandGenPartner for customer acquisition estimate

4. ROUTE
   - "Extraordinary" (agent judgment: high income potential + low startup cost + good timing):
     → Send IMMEDIATE Slack alert
     → Wait for approval before logging as approved
   - "Regular" (solid opportunity, not extraordinary):
     → Include in daily DAILY REPORT Slack message
     → Log to opportunity store with status "pending"

5. STORE
   All opportunities go to ~/.claude/side_hustle_opportunities.json:
   {
     "id": "uuid",
     "title": "...",
     "description": "...",
     "scores": { "income": €, "time_hrs_week": N, "startup_cost": €, "skill_match": "low/med/high", "timing": "early/growing/mature" },
     "council_feedback": { "coach": "...", "devils_advocate": "...", "others": {...} },
     "status": "pending/approved/rejected",
     "discovered_date": "YYYY-MM-DD",
     "source": "reddit/indiehackers/ph/upwork/etc.",
     "slack_sent": true/false,
     "slack_immediate": true/false
   }
```

---

## Slack Notifications

**Channel:** `#side-hustles` (created via Slack API)

**Slack Integration:**
- Uses Slack incoming webhooks (simplest, no bot needed for send-only)
- Env vars: `SLACK_WEBHOOK_URL`, `SLACK_CHANNEL` (default: `#side-hustles`)
- Fallback: if no webhook configured, log to console + opportunity store (no crash)

**Immediate Alert format:**
```
🔔 EXTRAORDINARY OPPORTUNITY FOUND

[Title]
[2-3 sentence description]

💰 Income Potential: €X/month
⏱ Time Required: X hrs/week
💵 Startup Cost: €X
🎯 Skill Match: Low/Medium/High
📈 Market Timing: Early/Growing/Mature

Coach Says: "[key insight from Coach]"
Devil's Advocate: "[key concern from Devil's Advocate]"

👉 APPROVE (y/n) or INVESTIGATE FURTHER
Source: [URL]
```

**Daily Report format:**
```
📊 Side Hustle Daily Report — [date]

Found X opportunities today:

1. [Title] — €X/mo | X hrs/wk | [Coach verdict in 1 line]
2. [Title] — €X/mo | X hrs/wk | [Coach verdict in 1 line]
...
```

---

## Scheduling

- **Daily scan:** Cron at 09:00 local (`0 9 * * *`), durable, recurring
- **Extraordinary alerts:** Event-driven — agent decides when to send immediately based on judgment
- **Manual trigger:** You can say "scan for side hustles" to trigger a manual scan anytime

---

## File Structure (new files)

```
srv/crewai/src/
├── agents/
│   ├── __init__.py                  # Add SideHustleScout export
│   └── side_hustle_scout.py         # New — SideHustleScout agent + tools
├── tasks/
│   ├── __init__.py                  # Add side_hustle_scout_task export
│   └── side_hustle_tasks.py         # New — task definitions

srv/crewai/scripts/
├── daily_hustle_scan.py             # New — standalone daily scan script
└── send_slack_alert.py              # New — Slack notification script

srv/crewai/slack/
└── slack_client.py                  # New — Slack API/webhook wrapper
```

---

## Dependencies

- Python: `crewai`, `crewai_tools`, `requests`, `beautifulsoup4`
- Existing: `gws` CLI (already available)
- Slack: incoming webhook URL (provided during setup)

---

## Config Env Vars

| Var | Default | Description |
|---|---|---|
| `SLACK_WEBHOOK_URL` | `""` | Slack incoming webhook URL |
| `SLACK_CHANNEL` | `#side-hustles` | Slack channel for notifications |
| `VAULT_ROOT` | `~/srv/vault` | Root of vault folder |
| `OPPORTUNITY_STORE` | `~/.claude/side_hustle_opportunities.json` | Opportunity log file |

---

## Edge Cases

- **No webhook configured:** Log to console + opportunity store. No crash, no blocking.
- **Web scraping blocked:** Return "Could not reach [source]" — don't fail entire scan.
- **No new opportunities:** Daily report says "No new opportunities today."
- **Council agents unavailable:** Proceed with scout's own evaluation; log as "council unavailable"
- **Slack send fails:** Log locally, retry next cycle.

---

## Scope Boundaries

- Scout monitors publicly available web sources only
- No automated account creation or posting
- No paid data sources unless API key provided
- Agent judgment is final for "extraordinary" classification — user can always override
- Read-only from vault (no writes by scout)

---

## Related: `/install-slack-app`

This is a Claude CLI command that installs Slack integration for Claude Code. It is run separately as a prerequisite setup step, not part of this implementation plan. The implementation uses Slack webhooks directly for notifications.