# tests/test_hustle_format.py
import sys
sys.path.insert(0, ".")

def test_rich_card_format():
    from slack.slack_client import build_rich_card
    card = build_rich_card(
        title="Freelance AI Consultant",
        income="800-1500",
        time="15",
        summary="Setup AI workflows for small businesses",
        source="HN Who is hiring (Mar 2026)",
        url="https://news.ycombinator.com/item?id=123",
        coach="High-margin, growing demand. Watch for saturation.",
    )
    assert "Freelance AI Consultant" in card
    assert "800-1500" in card
    assert "15 hrs/wk" in card
    assert "HN Who is hiring" in card
    assert "High-margin" in card

def test_coach_unavailable_fallback():
    from slack.slack_client import build_rich_card
    card = build_rich_card(
        title="SaaS Tool",
        income="2000",
        time="5",
        summary="Passive income from a niche tool",
        source="Reddit/r/sidehustle",
        url="https://reddit.com/r/sidehustle/posts/123",
        coach=None,
    )
    assert "Coach assessment unavailable" in card
    assert "placeholder" not in card.lower()
