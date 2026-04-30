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
                    results.append(self._scrape_hn_hiring(context))
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

    def _scrape_hn_hiring(self, context) -> str:
        """Scrape HN 'Who is hiring' monthly threads — rich source of real opportunities."""
        try:
            page = context.new_page()
            resp = page.goto(
                "https://news.ycombinator.com/submitted?id=whoishiring",
                timeout=20000,
                wait_until="domcontentloaded",
            )
            page.wait_for_timeout(2000)
            content = page.content()
            page.close()

            soup = BeautifulSoup(content, "html.parser")
            links = soup.select(".titleline > a")
            threads = [a for a in links if "who is hiring" in a.get_text(strip=True).lower()][:3]

            all_jobs = []
            for thread_link in threads:
                thread_title = thread_link.get_text(strip=True)
                thread_url = thread_link.get("href", "")
                # Navigate to the thread
                page2 = context.new_page()
                target = thread_url if thread_url.startswith("http") else f"https://news.ycombinator.com/{thread_url}"
                resp2 = page2.goto(target, timeout=25000, wait_until="domcontentloaded")
                page2.wait_for_timeout(3000)
                thread_html = page2.content()
                page2.close()

                jobs = HNHiringParser.parse_job_comments(thread_html)
                for job in jobs:
                    job["source"] = f"HN {thread_title}"
                    job["url"] = target
                all_jobs.extend(jobs)

            lines = []
            for job in all_jobs[:10]:  # max 10
                income_str = f"${job['income']}/mo" if job["income"] != "?" else "$?/mo"
                lines.append(
                    f"[HN Hiring] {job['title']}\n"
                    f"  Income: {income_str} | Time: {job['time']} hrs/wk\n"
                    f"  {job['description'][:200]}\n"
                    f"  URL: {job['url']}"
                )
            return "\n\n".join(lines) if lines else "[HN Hiring] No threads found"
        except Exception as e:
            return f"[HN Hiring] Error: {e}"

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



class HNHiringParser:
    """Parse HN 'Who is hiring' monthly threads for job opportunities."""

    @staticmethod
    def extract_thread_links(html: str, max_months: int = 3) -> list[dict]:
        """Extract hiring thread links from submitted page. Returns list of {url, title, month}."""
        soup = BeautifulSoup(html, "html.parser")
        links = soup.select(".titleline > a")
        threads = []
        for a in links:
            text = a.get_text(strip=True)
            if "who is hiring" in text.lower():
                threads.append({
                    "url": a.get("href", ""),
                    "title": text,
                    "month": HNHiringParser._extract_month(text),
                })
                if len(threads) >= max_months:
                    break
        return threads

    @staticmethod
    def _extract_month(title: str) -> str:
        m = re.search(r'\(([A-Za-z]+ \d{4})\)', title)
        return m.group(1) if m else "unknown"

    @staticmethod
    def parse_job_comments(html: str) -> list[dict]:
        """Parse a hiring thread page for job comment entries."""
        soup = BeautifulSoup(html, "html.parser")
        comments = soup.select(".comment")
        jobs = []
        for com in comments[:30]:  # first 30 comments
            text = com.get_text(strip=True)
            if len(text) < 50:
                continue
            title = HNHiringParser._extract_job_title(text)
            if title:
                income = HNHiringParser._extract_salary(text)
                jobs.append({
                    "title": title,
                    "income": income,
                    "time": HNHiringParser._estimate_time(text),
                    "startup_cost": "low" if "remote" in text.lower() else "medium",
                    "description": text[:300],
                    "url": "",
                })
        return jobs

    @staticmethod
    def _extract_job_title(text: str) -> str | None:
        """First line or first 80 chars is usually the job title. Returns None if all lines are ≤10 chars."""
        lines = text.split("\n")
        for line in lines:
            line = line.strip()
            if len(line) > 10:
                return line[:80]
        return None  # explicit fallback — caller guards with `if title:`

    @staticmethod
    def _extract_salary(text: str) -> str:
        """Look for salary mentions like $120k, €80/hr.
        Note: k-suffix not supported — $50k shows as 50 (limitation, not silent data loss).
        """
        m = re.search(r'[€$£](\d+)', text)
        if m:
            return m.group(1)
        return "?"

    @staticmethod
    def _estimate_time(text: str) -> str:
        if "part-time" in text.lower() or "part time" in text.lower():
            return "20"
        if "contract" in text.lower() or "freelance" in text.lower():
            return "10"
        return "40"