"""Second Brain Knowledge Tool — search + read across the full Aestas vault.

This tool provides all agents with live access to the Second Brain vault:
  /home/zoltan/srv/vault/Second Brain/raw/

It covers all Aestas divisions:
  Aestas_CFO, Aestas_CTO, Aestas_COO, Aestas_CMO,
  Aestas_CMedO, Aestas_Brand, Aestas_Researcher

Usage:
    tool = SecondBrainKnowledgeTool()
    result = tool.search(query="pricing strategy Sweden", sections=["CFO", "CMO"])
    result = tool.read_section(section="CFO")
"""

from crewai.tools import BaseTool
from pathlib import Path
import re
from typing import Optional

VAULT_ROOT = Path.home() / "srv" / "vault" / "Second Brain" / "raw"

# All Aestas sections in the vault
AESTAS_SECTIONS = [
    "Aestas_CFO",
    "Aestas_CTO",
    "Aestas_COO",
    "Aestas_CMO",
    "Aestas_CMedO",
    "Aestas_Brand",
    "Aestas_Researcher",
]

# Section → description for the tool description
SECTION_DESCRIPTIONS = {
    "Aestas_CFO": "Financial models, analyses, ROI reports, pricing",
    "Aestas_CTO": "Architecture reviews, tech decisions, build vs buy",
    "Aestas_COO": "Capacity plans, processes, RACI matrices",
    "Aestas_CMO": "Campaigns, content, copy, SEO briefs, social posts",
    "Aestas_CMedO": "Clinical guidelines, regulations, safety",
    "Aestas_Brand": "Brand story, positioning, voice, visual identity",
    "Aestas_Researcher": "Market research, competitive analysis",
}


class SecondBrainKnowledgeTool(BaseTool):
    """Search and read across the Aestas Second Brain vault.

    Covers: CFO, CTO, COO, CMO, CMedO, Brand, Researcher sections.
    Returns relevant file excerpts with source attribution.
    """

    name: str = "SecondBrainKnowledge"
    description: str = (
        "Search and read Aestas Second Brain vault for relevant context. "
        "Covers: CFO (finances/pricing), CTO (tech), COO (operations), "
        "CMO (marketing), CMedO (clinical), Brand, Researcher. "
        "Use when a question might benefit from existing analyses, "
        "decisions, or domain knowledge already captured in the vault. "
        "Args: query (str, required) — search keyword/phrase. "
        "sections (list[str], optional) — filter to specific sections."
    )

    def _run(self, query: str = "", sections: Optional[list[str]] = None) -> str:
        """Search the vault for files matching the query.

        Args:
            query: Keyword or phrase to search for
            sections: Optional list of section names to limit search
                     (e.g. ["CFO", "CMO"] or ["CMedO"])

        Returns:
            Formatted string with matching file paths and context
        """
        if not query:
            return "Error: query parameter is required"

        sections_to_search = sections or AESTAS_SECTIONS
        sections_to_search = [f"Aestas_{s}" if not s.startswith("Aestas_") else s for s in sections_to_search]

        all_results = []

        for section in sections_to_search:
            section_path = VAULT_ROOT / section
            if not section_path.exists():
                all_results.append(f"[{section}] — section not found in vault")
                continue

            section_results = self._search_section(section_path, query)
            if section_results:
                all_results.append(f"## {section}")
                all_results.append(f"(Contains: {SECTION_DESCRIPTIONS.get(section, 'N/A')})")
                all_results.append("")
                all_results.extend(section_results)
                all_results.append("")

        if not all_results:
            return f"No results found for '{query}' in Second Brain vault"

        return "\n".join(all_results)

    def _search_section(self, section_path: Path, query: str) -> list[str]:
        """Search a vault section for the query."""
        results = []
        query_lower = query.lower()

        for md_file in section_path.rglob("*.md"):
            try:
                content = md_file.read_text(errors="ignore")
                if query_lower not in content.lower():
                    continue

                rel_path = md_file.relative_to(VAULT_ROOT)
                results.append(f"### 📄 {rel_path}")
                results.append("")

                # Find matching lines with context
                lines = content.split("\n")
                matches = []
                for i, line in enumerate(lines):
                    if query_lower in line.lower():
                        # Include 1 line of context before
                        start = max(0, i - 1)
                        # Up to 3 lines of match context
                        context_lines = lines[start : i + 3]
                        for j, ctx_line in enumerate(context_lines, start=start + 1):
                            ctx_line = ctx_line.strip()
                            if ctx_line:
                                matches.append(f"  L{j}: {ctx_line}")
                        if matches:
                            matches.append("")

                if matches:
                    results.extend(matches[:15])  # Limit output per file
                    results.append("")

            except Exception:
                continue

        # Also search PDF files (just report their existence)
        for pdf_file in section_path.rglob("*.pdf"):
            try:
                content = pdf_file.read_text(errors="ignore")
                if query_lower in content.lower():
                    rel_path = pdf_file.relative_to(VAULT_ROOT)
                    results.append(f"### 📄 {rel_path} *(PDF — binary content)*")
                    results.append("")
            except Exception:
                continue

        return results[:20]  # Max 20 items per section

    def read_section(self, section: str = "") -> str:
        """Read the full content of a vault section (index of all files).

        Useful for getting an overview of what a section contains.

        Args:
            section: Section name (e.g. "CFO", "CTO", or "Aestas_CFO")

        Returns:
            List of all files in the section with their paths
        """
        section_name = f"Aestas_{section}" if not section.startswith("Aestas_") else section
        section_path = VAULT_ROOT / section_name

        if not section_path.exists():
            return f"Section not found: {section_name}"

        files = []
        for f in sorted(section_path.rglob("*")):
            if f.is_file():
                rel = f.relative_to(section_path)
                size = f.stat().st_size
                files.append(f"  • {rel} ({size:,} bytes)")

        if not files:
            return f"No files in section: {section_name}"

        header = f"# {section_name}\n"
        header += f"Description: {SECTION_DESCRIPTIONS.get(section_name, 'N/A')}\n"
        header += f"Total files: {len(files)}\n\n"
        return header + "\n".join(files)


# ── Standalone helper (for use in daemon prompts) ─────────────────────────────

def get_vault_context(question: str, sections: Optional[list[str]] = None, max_chars: int = 4000) -> str:
    """Fetch relevant vault context for a question (used in daemon prompts).

    This is a standalone function (no CrewAI dependency) that can be called
    from daemon scripts to pre-fetch context before calling Claude Code.

    Args:
        question: The user's question
        sections: Optional list of sections to search (default: all)
        max_chars: Truncate output at this many chars

    Returns:
        Formatted vault context string, or empty string if nothing found
    """
    tool = SecondBrainKnowledgeTool()
    result = tool._run(query=question, sections=sections)
    if result and "No results found" not in result and "not found" not in result.lower():
        if len(result) > max_chars:
            result = result[:max_chars] + f"\n\n... [truncated, {len(result) - max_chars} chars omitted]"
        return result
    return ""
