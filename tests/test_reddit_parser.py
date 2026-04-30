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


def test_score_monetization_income_euro():
    """Euro amounts under 10000 are treated as monthly figures."""
    from src.tools.web_scraper_tool import RedditPostParser
    scores = RedditPostParser.score_monetization("I make €800/month from freelance work")
    assert scores["income"] == "800"


def test_score_monetization_income_annual():
    """Euro amounts over 10000 are divided by 12 (assumed annual salary)."""
    from src.tools.web_scraper_tool import RedditPostParser
    scores = RedditPostParser.score_monetization("My SaaS makes €60000/yr")
    assert scores["income"] == "5000"


def test_score_monetization_time_passive():
    """'passive' keyword maps to 5 hrs/wk."""
    from src.tools.web_scraper_tool import RedditPostParser
    scores = RedditPostParser.score_monetization("Passive income from rental properties")
    assert scores["time_hrs_week"] == "5"


def test_score_monetization_time_freelance():
    """'freelance' keyword maps to 15 hrs/wk."""
    from src.tools.web_scraper_tool import RedditPostParser
    scores = RedditPostParser.score_monetization("Freelance copywriting on the side")
    assert scores["time_hrs_week"] == "15"


def test_score_monetization_empty_body():
    """Empty body returns '?' for income and time."""
    from src.tools.web_scraper_tool import RedditPostParser
    scores = RedditPostParser.score_monetization("")
    assert scores["income"] == "?"
    assert scores["time_hrs_week"] == "?"


def test_extract_summary_empty_body():
    """Empty body returns '[no summary available]' sentinel."""
    from src.tools.web_scraper_tool import RedditPostParser
    summary = RedditPostParser.extract_summary("")
    assert summary == "[no summary available]"


def test_extract_summary_normal_body():
    """First line > 20 chars is returned as summary."""
    from src.tools.web_scraper_tool import RedditPostParser
    body = "Here's my side hustle story.\n\nI've been making €500/mo from tutoring."
    summary = RedditPostParser.extract_summary(body)
    assert "side hustle" in summary.lower()
    assert len(summary) <= 200