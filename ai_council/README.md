# AI Council - Strategic Advisory Board Crew

A CrewAI-based multi-agent system that simulates an advisory board of AI partners (CEO, CFO, Coach, Intelligence, etc.) to provide strategic guidance on business topics.

## Usage

```bash
cd ~/srv/crewai/ai_council
source ../.venv/bin/activate
python -m src.main "Should I launch a subscription or one-time pricing model?"
```

## Partners

- **Co-Founder**: Strategic sparring partner
- **Coach**: Founder mindset and performance
- **Intelligence**: Market and competitive analysis
- **Devil's Advocate**: Stress testing and risk identification
- **Advisor**: Synthesis and final recommendation
- Plus 8 more C-Suite partners available

## Project Structure

```
ai_council/
├── prompts/          # Partner prompt definitions
├── src/
│   ├── config.py     # Configuration
│   ├── crew.py       # Crew orchestration
│   ├── main.py       # CLI entry point
│   ├── agents/       # Agent definitions
│   └── tasks/        # Task definitions
└── .env              # API credentials
```