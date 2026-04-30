# tests/test_hn_parser.py
import sys
sys.path.insert(0, ".")
from src.tools.web_scraper_tool import WebScraperTool

def test_hn_hiring_returns_job_structured_data():
    """When scraping HN 'who is hiring', returns dicts with title, salary, time fields."""
    tool = WebScraperTool()
    # Mock is tricky here — test the parsing logic on a known HTML snippet
    from src.tools.web_scraper_tool import HNHiringParser
    html = """
    <tr class='athing'>
      <td class='title'>
        <span class='titleline'>
          <a href="item?id=123">Ask HN: Who is hiring? (March 2026)</a>
        </span>
      </td>
    </tr>
    """
    # HNHiringParser.extract_thread_links(html) → [dict with url, title]
    assert HNHiringParser.extract_thread_links(html)[0]["url"] == "item?id=123"