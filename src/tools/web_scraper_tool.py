"""Web scraper tool — uses Playwright to scrape side hustle opportunities."""

from crewai.tools import BaseTool
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import re


SUBREDDITS = ["startups", "Entrepreneur", "sidehustle", "passive_income"]


class WebScraperTool(BaseTool):
    name: str = "WebScraperTool"
    description: str = (
        "Use this tool to scrape side hustle opportunities from web sources. "
        "Pass source='reddit', source='indiehackers', source='producthunt', "
        "source='hackernews', source='substack', or source='all'. "
        "Returns a list of opportunities with title, description, and source URL."
    )

    def _run(self, source: str = "all") -> str:
        results = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
                )

                if source in ("reddit", "all"):
                    results.append(self._scrape_reddit(context))
                if source in ("indiehackers", "all"):
                    results.append(self._scrape_indiehackers(context))
                if source in ("hackernews", "all"):
                    results.append(self._scrape_hackernews(context))
                if source in ("substack", "all"):
                    results.append(self._scrape_substack(context))
                if source in ("producthunt", "all"):
                    results.append(self._scrape_producthunt(context))

                context.close()
                browser.close()
        except Exception as e:
            return f"Playwright error: {e}"

        output = "\n\n".join(r for r in results if r)
        return output or "No results found."

    def _scrape_reddit(self, context) -> str:
        """Scrape Reddit via JSON API - no JS needed."""
        lines = []
        for sub in SUBREDDITS:
            try:
                page = context.new_page()
                url = f"https://old.reddit.com/r/{sub}/search.json?q=side+hustle+OR+passive+income+OR+monetize&sort=top&t=month"
                resp = page.goto(url, timeout=20000)
                page.wait_for_timeout(2000)
                content = page.content()
                page.close()

                if resp.status == 200:
                    soup = BeautifulSoup(content, "html.parser")
                    posts = soup.select(".link")[:5]
                    for post in posts:
                        title_el = post.select_one(".title a, .search-title")
                        score_el = post.select_one(".score")
                        link_el = post.select_one(".title a")
                        if title_el:
                            title = title_el.get_text(strip=True)
                            score = score_el.get_text(strip=True) if score_el else "?"
                            href = link_el.get("href", "") if link_el else ""
                            lines.append(
                                f"[Reddit/r/{sub}] {title}\n  Score: {score} | URL: https://reddit.com{href}"
                            )
                else:
                    lines.append(f"[Reddit/r/{sub}] HTTP {resp.status} (blocked)")
            except Exception as e:
                lines.append(f"[Reddit/r/{sub}] Error: {e}")
        return "\n".join(lines) if lines else "[Reddit] Could not reach Reddit"

    def _scrape_indiehackers(self, context) -> str:
        """IndieHackers requires login — try the public posts feed as fallback."""
        try:
            page = context.new_page()
            # Try the public forum page
            resp = page.goto(
                "https://www.indiehackers.com/forum/general",
                timeout=25000,
                wait_until="domcontentloaded",
            )
            page.wait_for_timeout(4000)
            content = page.content()
            page.close()

            soup = BeautifulSoup(content, "html.parser")
            # Forum posts have a different structure
            posts = soup.select(".forum-post, .post-item, [data-testid='forum-post']")[:5]
            if not posts:
                return "[IndieHackers] Requires login — try the website directly"

            lines = []
            for post in posts:
                title_el = post.select_one("h2, h3, .title")
                link_el = post.select_one("a")
                if title_el:
                    title = title_el.get_text(strip=True)
                    href = link_el.get("href", "") if link_el else ""
                    lines.append(f"[IndieHackers] {title}\n  URL: https://www.indiehackers.com{href}")
            return "\n".join(lines) if lines else "[IndieHackers] No public posts available"
        except Exception as e:
            return f"[IndieHackers] Error: {e}"

    def _scrape_hackernews(self, context) -> str:
        """Scrape Hacker News 'Who is hiring' threads — rich source of side hustle ideas."""
        try:
            page = context.new_page()
            # HN hiring threads are goldmines for freelance/remote work
            resp = page.goto(
                "https://news.ycombinator.com/submitted?id=whoishiring",
                timeout=20000,
                wait_until="domcontentloaded",
            )
            page.wait_for_timeout(3000)
            content = page.content()
            page.close()

            soup = BeautifulSoup(content, "html.parser")
            titles = soup.select(".titleline > a")[:8]
            lines = []

            for t in titles:
                text = t.get_text(strip=True)
                href = t.get("href", "")
                # Filter to 'who is hiring' threads (monthly threads contain many opportunities)
                lines.append(f"[HackerNews] {text}\n  URL: https://news.ycombinator.com/{href}")

            return "\n".join(lines) if lines else "[HackerNews] No threads found"

        except Exception as e:
            return f"[HackerNews] Error: {e}"

    def _scrape_substack(self, context) -> str:
        """Scrape Substack's trending business/money newsletter posts."""
        try:
            page = context.new_page()
            resp = page.goto(
                "https://substack.com/discover/discover?category=money",
                timeout=20000,
                wait_until="domcontentloaded",
            )
            page.wait_for_timeout(4000)
            content = page.content()
            page.close()

            soup = BeautifulSoup(content, "html.parser")
            # Substack uses different class names — look for post cards
            posts = soup.select(".post-preview, .substack-post-card, article")[:5]
            if not posts:
                # Try generic article links
                posts = soup.select("a[href*='/p/']")[:5]

            lines = []
            for post in posts:
                title_el = post.select_one("h2, h3, .post-title, .title")
                if title_el:
                    title = title_el.get_text(strip=True)
                    href = post.get("href") or ""
                    if not href and title_el:
                        parent = title_el.find_parent("a")
                        if parent:
                            href = parent.get("href", "")
                    lines.append(f"[Substack] {title}\n  URL: {href}")

            return "\n".join(lines) if lines else "[Substack] No posts found"

        except Exception as e:
            return f"[Substack] Error: {e}"

    def _scrape_producthunt(self, context) -> str:
        """Scrape Product Hunt trending."""
        try:
            page = context.new_page()
            page.goto(
                "https://www.producthunt.com/posts?sort=top",
                timeout=25000,
                wait_until="domcontentloaded",
            )
            page.wait_for_timeout(5000)

            content = page.content()
            page.close()

            soup = BeautifulSoup(content, "html.parser")
            # Try multiple selectors for product items
            posts = (
                soup.select("[data-test='post-item']")[:5]
                or soup.select(".posts-feed__post")[:5]
                or soup.select("a[href*='/posts/']")[:5]
            )
            lines = []

            for p in posts:
                title_el = p.select_one("h3, [data-test='post-title'], .feed-item__title")
                link = p.get("href", "") if isinstance(p, Exception) else ""
                if title_el:
                    text = title_el.get_text(strip=True)
                    parent_a = title_el.find_parent("a") if title_el else None
                    if parent_a and not link:
                        link = parent_a.get("href", "")
                    if link and not link.startswith("http"):
                        link = f"https://www.producthunt.com{link}"
                    lines.append(f"[ProductHunt] {text}\n  URL: {link}")

            return "\n".join(lines) if lines else "[ProductHunt] No posts found"

        except Exception as e:
            return f"[ProductHunt] Error: {e}"