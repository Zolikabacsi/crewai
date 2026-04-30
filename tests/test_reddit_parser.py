# tests/test_reddit_parser.py
import sys
sys.path.insert(0, ".")

def test_skip_ask_hn_posts():
    """Posts with 'Ask HN' in title should be filtered out."""
    from src.tools.web_scraper_tool import RedditPostParser
    posts = [
        {"title": "Ask HN: Who wants to be hired?", "url": "http://example.com/1"},
        {"title": "My side hustle making €5k/mo", "url": "http://example.com/2"},
    ]
    filtered = RedditPostParser.filter_opportunities(posts)
    assert len(filtered) == 1
    assert "side hustle" in filtered[0]["title"].lower()