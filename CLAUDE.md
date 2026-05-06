# CLAUDE.md

**Project:** CrewAI Business Intelligence System
**Generated:** 2026-05-04
**Author:** Claude (system update)

Multi-agent business intelligence system using CrewAI framework. Powers executive AI agents (CFO, CMO, COO, CTO), an AI Council advisory board, crypto trading research, and side-hustle scouting — all coordinated via a Redis-based AgentBus and Slack notifications.

## Project Structure

```
crewai/
├── src/                    # Core crew system
│   ├── main.py             # CLI entry: python -m src.main "idea"
│   ├── crew.py             # Crew orchestration (evaluate_business_idea, run_evaluation)
│   ├── config.py           # Environment + LLM configuration
│   ├── agents/             # 16 agent classes
│   │   ├── agents.py       # MarketResearcher, FinancialAnalyst, RiskAssessor, BusinessWriter
│   │   ├── cfo.py          # Chief Financial Officer agent
│   │   ├── cmo.py          # Chief Marketing Officer agent
│   │   ├── coo.py          # Chief Operating Officer agent
│   │   ├── cto.py          # Chief Technology Officer agent
│   │   ├── cmedo.py        # Chief Marketing Executive Digital Officer
│   │   ├── side_hustle_scout.py  # Side hustle opportunity scout
│   │   ├── office_assistant.py   # Office & Drive sync assistant
│   │   ├── copywriter.py          # Marketing copywriter
│   │   ├── seogeo.py             # SEO & geo marketing agent
│   │   ├── social_manager.py      # Social media manager
│   │   ├── patient_safety.py      # Healthcare patient safety agent
│   │   ├── clinical_guidelines.py # Clinical guidelines agent
│   │   └── regulatory_advisor.py  # Regulatory compliance advisor
│   ├── tasks/              # Task definitions
│   │   ├── tasks.py        # Core evaluation tasks
│   │   ├── office_tasks.py # Office assistant tasks
│   │   └── side_hustle_tasks.py  # Side hustle tasks
│   ├── tools/             # 15 custom tools
│   │   ├── reddit_scraper_tool.py   # Reddit market research
│   │   ├── calendar_tool.py         # Google Calendar (gws CLI)
│   │   ├── email_tool.py            # Gmail search (gws CLI)
│   │   ├── vault_read_tool.py       # Vault FS read
│   │   ├── vault_search_tool.py     # Vault FS search
│   │   ├── vault_strategy_tool.py   # Strategy library access
│   │   ├── drive_sync_tool.py        # Google Drive sync (gws CLI)
│   │   ├── binance_funding_tool.py   # Binance perp funding rates
│   │   ├── binance_market_tool.py    # Binance prices/vol/OI
│   │   ├── economic_calendar_tool.py  # Macro event calendar
│   │   ├── web_scraper_tool.py       # Web scraping
│   │   ├── industry_report_tool.py   # Vault industry reports
│   │   ├── gws_tool.py               # Google Workspace CLI wrapper
│   │   └── agent_bus_tool.py         # Inter-agent messaging
│   ├── agent_bus/          # Redis-based message bus
│   │   ├── models.py        # Message types, AgentInfo
│   │   ├── redis_client.py  # Redis connection
│   │   ├── message_bus.py   # Pub/sub message handling
│   │   ├── registry.py     # Agent registration
│   │   ├── agent_bus.py    # Main bus orchestrator
│   │   ├── inbox.py        # Per-agent inbox queue
│   │   └── runners/        # Daemon runners for CEO, CFO, OfficeAssistant
│   └── agent_storage/      # Memory & vault integration
│       ├── memory_integration.py
│       ├── vault_tool.py
│       └── storage_service.py
├── ai_council/             # AI Strategic Advisory Board (18 partners)
│   ├── src/
│   │   ├── main.py          # CLI: python -m src.main "question"
│   │   ├── crew.py          # Council crew orchestration
│   │   ├── config.py
│   │   ├── memory.py
│   │   ├── agents/agents.py  # 18 partner agent classes + get_council_agents()
│   │   ├── agents/zernio_tools.py
│   │   └── tasks/tasks.py
│   └── prompts/            # 17+ partner prompt files (CEO, CFO, CMO, COO, CTO, ...)
├── marketingskills/        # 42 marketing skills (Claude Code plugin)
│   ├── CLAUDE.md            # Skill spec + tool registry
│   ├── AGENTS.md            # Agent guidelines
│   ├── skills/             # 42 skill directories (ab-test-setup, ai-seo, ...)
│   └── tools/              # CLI tools, composio, integrations
├── scripts/               # Daemon + automation scripts
│   ├── cmo_daemon.py        # CMO automated runner
│   ├── cmedo_daemon.py      # CMEDO automated runner
│   ├── run_cmo.py           # CMO script runner
│   ├── daily_crypto_research.py  # Crypto research cycle
│   ├── daily_sync.py        # Drive sync automation
│   └── daily_hustle_scan.py  # Side hustle scan
├── slack/                  # Slack integration
│   ├── slack_client.py      # General Slack client
│   └── crypto_slack_client.py  # Crypto channel client
├── vault/                  # Second Brain knowledge base
│   └── Second Brain/       # Raw files, analyses (CFO briefings, etc.)
├── docs/superpowers/      # Design specs and implementation plans
│   ├── specs/
│   │   ├── 2026-04-28-side-hustle-scout-design.md
│   │   ├── 2026-04-28-office-assistant-agent-design.md
│   │   └── 2026-04-29-crypto-futures-research-agent-design.md
│   └── plans/
│       ├── 2026-04-28-ai-council-partner-agents-plan.md
│       ├── 2026-04-28-office-assistant-plan.md
│       └── 2026-04-29-crypto-futures-research-agent-plan.md
└── tests/                  # pytest suite
    ├── agent_bus/          # AgentBus tests (bus, redis, models, registry, inbox)
    ├── test_hustle_format.py
    ├── test_hustle_dedup.py
    ├── test_reddit_parser.py
    └── test_hn_parser.py
```

## Architecture

### LLM Configuration
All agents use **MiniMax-M2.7** via Anthropic SDK pointing to `https://chat.ultimateai.org`:
- Set `ANTHROPIC_AUTH_TOKEN` and `ANTHROPIC_BASE_URL` in `.env`
- `get_llm()` in `src/agents/agents.py` creates the LLM instance

### AgentBus (Redis-based IPC)
Inter-agent communication via Redis pub/sub:
- Agents register with the bus, publish to topics, subscribe to inboxes
- Daemon runners (`cfo_runner.py`, `ceo_runner.py`, `office_assistant_runner.py`) poll queues
- Used by CFO, CEO, OfficeAssistant for async operations

### AI Council
18 strategic advisory agents (CEO, CFO, CMO, COO, CTO, Coach, Devil's Advocate, Board Member, Investor, Advisor, Content Strategy, Customer, Demand Gen, First Principles, Head of Product, Startup GTM, Intelligence, Co-Founder). Each loads its prompt from `ai_council/prompts/*.md` using `load_prompt()`.

### Marketing Skills Plugin
42 Claude Code skills for marketing automation. See `marketingskills/CLAUDE.md` and `marketingskills/AGENTS.md`.

## Code Map

| Symbol | Type | Location |
|--------|------|----------|
| `get_llm()` | fn | `src/agents/agents.py` |
| `get_all_agents()` | fn | `src/agents/agents.py` |
| `evaluate_business_idea()` | fn | `src/crew.py` |
| `run_evaluation()` | fn | `src/crew.py` |
| `get_council_agents()` | fn | `ai_council/src/agents/agents.py` |
| `load_prompt()` | fn | `ai_council/src/agents/agents.py` |
| `AgentBus` | class | `src/agent_bus/agent_bus.py` |
| `RedisAgentBusClient` | class | `src/agent_bus/redis_client.py` |
| `Config` | class | `src/config.py` |

## Conventions

- **Python:** ruff lint (E,F,I,N,W,UP,B,C4,SIM), line-length=100
- **Framework:** CrewAI 0.80+ with custom LLM endpoint
- **LLM:** MiniMax-M2.7 via `https://chat.ultimateai.org`
- **IPC:** Redis pub/sub for AgentBus
- **Auth:** `gws` CLI for Google Workspace (Calendar, Gmail, Drive)
- **Logging:** structlog-style with `logger.info()` / `logger.error()`
- **Env vars:** `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, `REDIS_URL`, `SLACK_WEBHOOK_URL`, `VAULT_ROOT`, `SLACK_CRYPTO_WEBHOOK_URL`

## Anti-Patterns

- **DO NOT hardcode model names** — use `get_llm()` which routes to MiniMax-M2.7
- **DO NOT use sync HTTP in async agents** — use thread pool or `run_in_executor`
- **DO NOT call `gws` without checking the tool exists** — validate `gws` CLI availability first
- **DO NOT expose Redis credentials** — keep `REDIS_URL` in `.env`, never commit

## Unique Patterns

- **AgentBus:** Redis pub/sub + inbox queues. Register → subscribe → poll inbox
- **AI Council:** Each partner is a CrewAI Agent loading prompt from `.md` file
- **gws CLI:** All Google Workspace tools (Calendar, Gmail, Drive) use the `~/bin/gws` wrapper
- **Vault tools:** File-system based knowledge retrieval from `~/srv/vault/`
- **Marketing skills:** 42 standalone skills in `marketingskills/skills/` for Claude Code plugin installation

## Commands

```bash
# Business idea evaluator
python -m src.main "Your business idea here"
python -m src.main  # Interactive mode

# AI Council advisory board
cd ai_council && python -m src.main "Your question"

# AgentBus daemon (Redis required)
python src/agent_bus/runners/cfo_runner.py

# CMO daemon
python scripts/cmo_daemon.py

# Side hustle scan (manual)
python scripts/daily_hustle_scan.py

# Drive sync (manual)
python scripts/daily_sync.py

# Crypto research (manual)
python scripts/daily_crypto_research.py

# Install marketing skills (Claude Code)
/plugin install marketing-skills  # from marketingskills/ directory

# Tests
pytest tests/ -v
pytest tests/agent_bus/ -v

# Lint
ruff check src/ ai_council/src/
```

## Key Design Documents

| Document | Location | Purpose |
|----------|----------|---------|
| Side Hustle Scout Design | `docs/superpowers/specs/2026-04-28-side-hustle-scout-design.md` | Scout agent full spec |
| Office Assistant Design | `docs/superpowers/specs/2026-04-28-office-assistant-agent-design.md` | Office agent full spec + 6 missing AI Council agents |
| Crypto Futures Research Design | `docs/superpowers/specs/2026-04-29-crypto-futures-research-agent-design.md` | Crypto agent full spec |
| AI Council Partner Plan | `docs/superpowers/plans/2026-04-28-ai-council-partner-agents-plan.md` | 6 missing partner agents implementation |

## Notes

- `crewai_git/` is a bare git clone of the upstream fork at `github.com/Zolikabacsi/crewai`
- Crypto agent subdirectories (`backtest/`, `data/`, `execution/`, `optimizer/`, `state/`, `strategy/`) are empty — crypto execution framework not yet implemented
- Vault at `~/srv/vault/Second Brain/` contains CFO analyses and raw documents
- `partner_prompts/` is a duplicate of `ai_council/prompts/` — canonical source is `ai_council/prompts/`
- Slack integration uses incoming webhooks — no bot user needed for send-only notifications