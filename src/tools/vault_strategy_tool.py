"""Vault strategy tool — reads the crypto-futures-strategy library and matches conditions."""

from crewai.tools import BaseTool
from pathlib import Path

# Primary vault location; fall back to alternate path
VAULT_ROOT = Path.home() / "srv" / "vault" / "crypto-futures-strategies"
if not VAULT_ROOT.exists():
    VAULT_ROOT = Path.home() / "srv" / "crewai" / "vault" / "crypto-futures-strategies"

# Keyword → filename mapping
KEYWORD_MAP = {
    "funding_negative": "funding-rate-arbitrage.md",
    "short squeeze": "funding-rate-arbitrage.md",
    "funding_positive": "funding-rate-arbitrage.md",
    "top signal": "funding-rate-arbitrage.md",
    "breakout": "momentum-breakout.md",
    "altcoin": "altcoin-lev-swing.md",
    "mes": "mes-micro-scalp.md",
    "scalp": "mes-micro-scalp.md",
    "catalyst": "macro-catalyst-gapping.md",
    "news": "macro-catalyst-gapping.md",
    "macro": "macro-catalyst-gapping.md",
}


def _resolve_vault() -> Path:
    if VAULT_ROOT.exists():
        return VAULT_ROOT
    # Search common locations
    for candidate in [
        Path.home() / "srv" / "vault" / "crypto-futures-strategies",
        Path.home() / "srv" / "crewai" / "vault" / "crypto-futures-strategies",
        Path.home() / ".config" / "superpowers" / "worktrees" / "crewai" / "crypto-research" / "vault",
    ]:
        if candidate.exists():
            return candidate
    return VAULT_ROOT  # return primary even if missing — error handled in _run


def _strategy_title(content: str) -> str:
    """Extract strategy name from the first '# Strategy: ...' line."""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("# Strategy:"):
            # Extract text after '# Strategy: '
            name = line.split("# Strategy:", 1)[1].strip()
            return name
    return "Unknown Strategy"


def _summarize(content: str) -> str:
    """Return entry conditions and exit rules from a strategy document."""
    lines = content.splitlines()
    sections = []
    in_relevant = False
    relevant_headers = {
        "entry",
        "exit",
        "entry condition",
        "exit rule",
        "signal a",
        "signal b",
    }

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            header = stripped[3:].strip().lower()
            in_relevant = any(k in header for k in relevant_headers)
            sections.append(f"\n{line}")
        elif in_relevant:
            sections.append(f"\n{line}")

    return "".join(sections).strip()


class VaultStrategyTool(BaseTool):
    name: str = "VaultStrategyTool"
    description: str = (
        "Reads the crypto-futures-strategy vault library. "
        "Use action='list' to enumerate all available strategies. "
        "Use action='match' with a condition keyword to find the best-fit strategy; "
        "returns strategy name, entry conditions, and exit rules. "
        "Keywords: funding_negative / short squeeze / funding_positive / top signal → funding-rate-arbitrage; "
        "breakout → momentum-breakout; altcoin → altcoin-lev-swing; "
        "mes / scalp → mes-micro-scalp; catalyst / news / macro → macro-catalyst-gapping."
    )

    def _run(self, action: str = "list", condition: str = "") -> str:
        vault = _resolve_vault()

        # ── LIST ─────────────────────────────────────────────────────────────────
        if action == "list":
            if not vault.exists():
                return f"Vault not found at {vault}"

            strategies = []
            for md_file in sorted(vault.glob("*.md")):
                try:
                    content = md_file.read_text(errors="ignore")
                    title = _strategy_title(content)
                    strategies.append(f"- {md_file.stem}: {title}")
                except Exception:
                    strategies.append(f"- {md_file.stem}: (error reading)")
            return "Available strategies:\n" + "\n".join(strategies)

        # ── MATCH ────────────────────────────────────────────────────────────────
        if action == "match":
            if not vault.exists():
                return f"Vault not found at {vault}"

            condition_lower = condition.lower().strip()

            # 1. Check keyword map (filename priority)
            filename = KEYWORD_MAP.get(condition_lower)
            if filename:
                file_path = vault / filename
                if file_path.exists():
                    content = file_path.read_text(errors="ignore")
                    title = _strategy_title(content)
                    summary = _summarize(content)
                    return f"Strategy: {title}\n{summary}"

            # 2. Full-text search across all strategy files
            matched = []
            for md_file in sorted(vault.glob("*.md")):
                try:
                    content = md_file.read_text(errors="ignore")
                    if condition_lower in content.lower():
                        title = _strategy_title(content)
                        summary = _summarize(content)
                        matched.append(f"File: {md_file.name}\nStrategy: {title}\n{summary}")
                except Exception:
                    continue

            if matched:
                return "\n---\n".join(matched)

            return f"No strategy found matching '{condition}'"

        return f"Unknown action '{action}'. Use action='list' or action='match'."
