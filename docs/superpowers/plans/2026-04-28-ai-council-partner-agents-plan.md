# AI Council: Wire Up 6 Partner Agents — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 6 missing partner agents to the AI Council so all prompt files have corresponding agent classes.

**Architecture:** Each partner is a CrewAI `Agent` subclass that loads its prompt from a `.md` file in `ai_council/prompts/` using the existing `load_prompt()` utility. No new tools or dependencies.

**Tech Stack:** crewai, existing `load_prompt()`, `FileReadTool`

---

## File Map

```
srv/crewai/ai_council/src/agents/
└── agents.py         # Modify: add 6 agent classes + update get_council_agents()
```

---

### Task 1: Wire up 6 partner agents

**Files:**
- Modify: `srv/crewai/ai_council/src/agents/agents.py`

- [ ] **Step 1: Read current agents.py to confirm structure**

Verify the file ends after `BoardMemberPartner` and the `get_council_agents()` / `get_core_agents()` functions.

- [ ] **Step 2: Add 6 agent classes after `BoardMemberPartner`**

Add these classes before the `get_council_agents()` function:

```python
class ContentStrategyPartner(Agent):
    def __init__(self):
        prompt = load_prompt("CONTENT_STRATEGY_PARTNER_PROMPT.md")
        super().__init__(
            role="Content Strategy Partner",
            goal="Content strategy and execution guidance",
            backstory=prompt,
            verbose=Config.VERBOSE,
            tools=[FileReadTool()],
            llm=get_llm(),
        )


class CustomerPartner(Agent):
    def __init__(self):
        prompt = load_prompt("CUSTOMER_PARTNER_STRATEGIC_THINKING.md")
        super().__init__(
            role="Customer Partner",
            goal="Customer perspective and validation",
            backstory=prompt,
            verbose=Config.VERBOSE,
            tools=[FileReadTool()],
            llm=get_llm(),
        )


class DemandGenPartner(Agent):
    def __init__(self):
        prompt = load_prompt("DEMAND_GEN_STRATEGY_PARTNER_PROMPT.md")
        super().__init__(
            role="Demand Generation Partner",
            goal="Demand generation and growth strategy",
            backstory=prompt,
            verbose=Config.VERBOSE,
            tools=[FileReadTool()],
            llm=get_llm(),
        )


class FirstPrinciplesPartner(Agent):
    def __init__(self):
        prompt = load_prompt("FIRST_PRINCIPLES_PARTNER_Strategic_Prompt.md")
        super().__init__(
            role="First Principles Partner",
            goal="First-principles reasoning and root cause analysis",
            backstory=prompt,
            verbose=Config.VERBOSE,
            tools=[FileReadTool()],
            llm=get_llm(),
        )


class HeadOfProductPartner(Agent):
    def __init__(self):
        prompt = load_prompt("HEAD_OF_PRODUCT_PARTNER_PROMPT.md")
        super().__init__(
            role="Head of Product Partner",
            goal="Product strategy and roadmap guidance",
            backstory=prompt,
            verbose=Config.VERBOSE,
            tools=[FileReadTool()],
            llm=get_llm(),
        )


class StartupGTMPartner(Agent):
    def __init__(self):
        prompt = load_prompt("StartupGTM_AI_Partners_Council_System.md")
        super().__init__(
            role="Startup GTM Partner",
            goal="Go-to-market strategy and launch planning",
            backstory=prompt,
            verbose=Config.VERBOSE,
            tools=[FileReadTool()],
            llm=get_llm(),
        )
```

- [ ] **Step 3: Update `get_council_agents()` to include all 6**

In `get_council_agents()`, add to the returned list:

```python
def get_council_agents():
    return [
        CEOPartner(),
        CFOPartner(),
        CMOPartner(),
        CTOPartner(),
        COOPartner(),
        CoFounderPartner(),
        CoachPartner(),
        IntelligencePartner(),
        DevilsAdvocatePartner(),
        AdvisorPartner(),
        InvestorPartner(),
        BoardMemberPartner(),
        ContentStrategyPartner(),
        CustomerPartner(),
        DemandGenPartner(),
        FirstPrinciplesPartner(),
        HeadOfProductPartner(),
        StartupGTMPartner(),
    ]
```

- [ ] **Step 4: Verify the file parses without error**

Run: `cd ~/srv/crewai/ai_council && source ../.venv/bin/activate && python -c "from src.agents.agents import get_council_agents; print(f'Agents loaded: {len(get_council_agents())}')"`
Expected: Output showing 18 agents

- [ ] **Step 5: Commit**

```bash
cd ~/srv/crewai
git add ai_council/src/agents/agents.py
git commit -m "feat(ai_council): wire up 6 missing partner agents

Adds: ContentStrategy, Customer, DemandGen, FirstPrinciples,
HeadOfProduct, StartupGTM partners to get_council_agents().

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

---

### Task 2: Smoke test — verify all agents initialize

**Files:**
- Modify: `srv/crewai/ai_council/src/agents/agents.py`

- [ ] **Step 1: Run agent initialization test**

Run: `cd ~/srv/crewai/ai_council && source ../.venv/bin/activate && python -c "
from src.agents.agents import get_council_agents
agents = get_council_agents()
for a in agents:
    print(f'- {a.role}')
print(f'Total: {len(agents)} agents')
"`
Expected: 18 agent roles listed, no errors

- [ ] **Step 2: Commit**

```bash
cd ~/srv/crewai
git add ai_council/src/agents/agents.py
git commit -m "test(ai_council): verify all 18 agents initialize cleanly

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

---

## Spec Coverage Check

| Spec Requirement | Task |
|---|---|
| Wire up 6 missing partner agents | Task 1 |
| Include in `get_council_agents()` | Task 1 Step 3 |
| Verify no errors | Task 2 |

**No gaps found.**