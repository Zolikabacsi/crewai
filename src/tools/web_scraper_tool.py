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

                # Log into HN if credentials are available
                self._hn_login(context)

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

    def _hn_login(self, context) -> None:
        """Log into HN using credentials from environment."""
        import os
        username = os.getenv("HN_USERNAME", "")
        password = os.getenv("HN_PASSWORD", "")
        if not username or not password:
            return

        try:
            page = context.new_page()
            page.goto("https://news.ycombinator.com/login", timeout=15000, wait_until="domcontentloaded")
            page.wait_for_timeout(1000)
            page.fill("input[name='acct']", username)
            page.fill("input[name='pw']", password)
            page.click("input[type='submit']")
            page.wait_for_timeout(2000)
            page.close()
        except Exception:
            pass  # login failure is non-fatal

    def _scrape_reddit(self, context) -> str:
        """Scrape Reddit — navigate into posts, extract content for monetization analysis."""
        lines = []
        for sub in ["sidehustle", "Entrepreneur", "passive_income"]:
            try:
                page = context.new_page()
                url = f"https://old.reddit.com/r/{sub}/search.json?q=side+hustle+OR+passive+income+OR+make+money&sort=top&t=month&restrict_sr=1"
                resp = page.goto(url, timeout=20000)
                page.wait_for_timeout(2000)
                content = page.content()
                page.close()

                if resp.status != 200:
                    lines.append(f"[Reddit/r/{sub}] HTTP {resp.status}")
                    continue

                soup = BeautifulSoup(content, "html.parser")
                # Get post links from search results
                post_links = soup.select(".result a[data-type='Submission']")[:5]
                if not post_links:
                    post_links = soup.select(".titleline > a")[:5]

                posts = []
                for a in post_links:
                    title = a.get_text(strip=True)
                    href = a.get("href", "")
                    if href.startswith("/"):
                        href = f"https://old.reddit.com{href}"
                    posts.append({"title": title, "url": href})

                # Filter out non-opportunities
                filtered = RedditPostParser.filter_opportunities(posts)

                # Navigate into each post to get body
                for post in filtered[:3]:
                    page2 = context.new_page()
                    try:
                        resp2 = page2.goto(post["url"] + ".json", timeout=20000)
                        page2.wait_for_timeout(1500)
                        import json as json_module
                        data = json_module.loads(page2.content()) if resp2.status == 200 else {}
                        post_body = ""
                        if isinstance(data, list) and len(data) > 1:
                            children = data[0].get("data", {}).get("children", [])
                            if children:
                                post_body = children[0].get("data", {}).get("selftext", "") or ""
                        page2.close()

                        scores = RedditPostParser.score_monetization(post_body)
                        summary = RedditPostParser.extract_summary(post_body)
                        income_str = f"€{scores['income']}/mo" if scores['income'] != "?" else "€?/mo"
                        lines.append(
                            f"[Reddit/r/{sub}] {post['title']}\n"
                            f"  Income: {income_str} | Time: {scores['time_hrs_week']} hrs/wk\n"
                            f"  {summary}\n"
                            f"  URL: {post['url']}"
                        )
                    except Exception:
                        page2.close()
                        continue
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
        """Scrape HN front page for side hustle / business opportunities.

        People post income reports, "I built X and make €Y/mo", SaaS launches,
        freelance wins, etc. Filter OUT job offers and "Ask HN" threads.
        """
        try:
            page = context.new_page()
            resp = page.goto(
                "https://news.ycombinator.com/",
                timeout=20000,
                wait_until="domcontentloaded",
            )
            page.wait_for_timeout(3000)
            content = page.content()
            page.close()

            soup = BeautifulSoup(content, "html.parser")
            titles = soup.select(".titleline > a")[:20]
            lines = []

            for t in titles:
                text = t.get_text(strip=True)
                href = t.get("href", "")
                url = href if href.startswith("http") else f"https://news.ycombinator.com/{href}"

                # Skip job/career threads
                skip_patterns = ["ask hn: who is hiring", "who wants to be hired",
                                 "hiring", "job:", "careers", "position:"]
                if any(p in text.lower() for p in skip_patterns):
                    continue

                # Check for side hustle signals in the title
                hustle_patterns = [
                    "i make", "i earned", "i built", "i launched", "i started",
                    "my saas", "side hustle", "passive income", "€/mo", "€k",
                    "$k/mo", "making $", "making €", "revenue", "profit",
                    "freelance", "consulting", "affiliate", "digital product",
                    "dropshipping", "print on demand", "monthly income",
                ]
                if not any(p in text.lower() for p in hustle_patterns):
                    # Still include — scrape the linked page to check body
                    pass

                lines.append(f"[HN] {text}\n  URL: {url}")

            return "\n".join(lines) if lines else "[HN] No opportunities found on front page"
        except Exception as e:
            return f"[HN] Error: {e}"

    def _scrape_hn_hiring(self, context) -> str:
        """Scrape HN 'Who is hiring' for side hustle / business opportunities, not job offers.

        Filters OUT: anything with a company name + job title + location combo (employment).
        Filters IN: side project income, freelance, SaaS, consulting, digital products, etc.
        """
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

            all_opps = []
            for thread_link in threads:
                thread_title = thread_link.get_text(strip=True)
                thread_url = thread_link.get("href", "")
                target = thread_url if thread_url.startswith("http") else f"https://news.ycombinator.com/{thread_url}"

                page2 = context.new_page()
                resp2 = page2.goto(target, timeout=25000, wait_until="domcontentloaded")
                page2.wait_for_timeout(3000)
                thread_html = page2.content()
                page2.close()

                jobs = HNHiringParser.parse_job_comments(thread_html)
                for job in jobs:
                    if self._is_side_hustle_opportunity(job["description"]):
                        job["source"] = f"HN {thread_title}"
                        job["url"] = target
                        all_opps.append(job)

            lines = []
            for job in all_opps[:10]:
                income_str = f"${job['income']}/mo" if job["income"] != "?" else "$?/mo"
                lines.append(
                    f"[HN Hiring] {job['title']}\n"
                    f"  Income: {income_str} | Time: {job['time']} hrs/wk\n"
                    f"  {job['description'][:200]}\n"
                    f"  URL: {job['url']}"
                )
            return "\n\n".join(lines) if lines else "[HN Hiring] No side hustle opportunities found this month"
        except Exception as e:
            return f"[HN Hiring] Error: {e}"

    @staticmethod
    def _is_side_hustle_opportunity(text: str) -> bool:
        """Return True if text describes a side hustle / business opportunity, not a job offer."""
        if not text:
            return False
        lower = text.lower()
        # Employment signals — these mean it's a job listing, not a side hustle
        job_signals = [
            "full-time", "full time", "part-time", "part time", "remote (us)",
            "san francisco", "new york", "seattle", "los angeles", "austin",
            "boston", "chicago", "toronto", "on-site", "on site", "hybrid",
            "|",  # company | location | type pattern
        ]
        for sig in job_signals:
            if sig in lower:
                return False

        # Side hustle / business signals — these mean it's an opportunity
        hustle_signals = [
            "i make", "i built", "i earned", "side hustle", "passive income",
            "freelance", "consulting", "saas", "affiliate", "digital product",
            "monthly", "per month", "/mo", "€", "£",
            "my project", "my site", "my blog", "i started", "i launched",
            "dropshipping", "print on demand", "side project", "earn extra",
        ]
        return any(sig in lower for sig in hustle_signals)

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
        """First line ≥10 chars that's NOT meta HN discussion is the job title."""
        # Skip HN meta-discussion lines — these are comments ABOUT the thread, not job posts
        skip_prefixes = (
            "there is something up", "thank you for flagging", "this is a classic",
            "i don't think that product", "what was their citizenship",
            "you need to get in touch", "i feel all hiring", "ask hn",
            "against malaria", "hi ", "please reach out", "head of engineering",
        )
        lines = text.split("\n")
        for line in lines:
            line = line.strip()
            if len(line) < 10:
                continue
            # Guard: skip obvious meta-discussion lines
            lowered = line.lower()
            if any(lowered.startswith(p) for p in skip_prefixes):
                continue
            # Skip lines that are just URLs or email addresses
            if lowered.startswith("http") or "@" in lowered and lowered.index("@") < 15:
                continue
            return line[:80]
        return None  # explicit fallback — caller guards with `if title:`

    @staticmethod
    def _extract_salary(text: str) -> str:
        """Look for salary mentions like $120k, $182k-$272k, €80/hr.
        Handles ranges by taking the first number and multiplying k-suffix by 1000.
        """
        m = re.search(r'[€$£](\d+)k?', text, re.IGNORECASE)
        if m:
            num = int(m.group(1))
            # k-suffix means thousands
            if m.group(0).endswith('k') or m.group(0).endswith('K'):
                num *= 1000
            return str(num)
        return "?"

    @staticmethod
    def _estimate_time(text: str) -> str:
        if "part-time" in text.lower() or "part time" in text.lower():
            return "20"
        if "contract" in text.lower() or "freelance" in text.lower():
            return "10"
        return "40"


class RedditPostParser:
    """Parse Reddit posts into structured opportunity records."""

    @staticmethod
    def filter_opportunities(posts: list[dict]) -> list[dict]:
        """Remove non-opportunity posts (job listings, meta posts)."""
        skip_patterns = ["ask hn", "who is hiring", "who wants to be hired",
                         "monthly thread", "meta discussion"]
        result = []
        for post in posts:
            title_lower = post.get("title", "").lower()
            if any(p in title_lower for p in skip_patterns):
                continue
            result.append(post)
        return result

    @staticmethod
    def score_monetization(post_body: str) -> dict:
        """Score post for monetization signals and estimate income/time."""
        body_lower = post_body.lower()
        scores = {
            "income": "?",
            "time_hrs_week": "?",
            "startup_cost": "low",
        }

        # Income signals
        if "€" in post_body or "$" in post_body:
            m = re.search(r'[€$]([\d,]+)', post_body)
            if m:
                raw = m.group(1).replace(",", "")
                try:
                    monthly = int(raw)
                    if monthly < 10000:
                        scores["income"] = str(monthly)
                    else:
                        scores["income"] = str(monthly // 12)
                except ValueError:
                    pass

        # Time signals
        if "passive" in body_lower or "automated" in body_lower:
            scores["time_hrs_week"] = "5"
        elif "side hustle" in body_lower or "freelance" in body_lower:
            scores["time_hrs_week"] = "15"
        else:
            scores["time_hrs_week"] = "?"

        # Startup cost
        if any(x in body_lower for x in ["no money", "free", "zero cost", "under €100"]):
            scores["startup_cost"] = "low"
        elif any(x in body_lower for x in ["investment", "cost", "expense", "paid"]):
            scores["startup_cost"] = "medium"

        return scores

    @staticmethod
    def extract_summary(post_body: str) -> str:
        """Extract the first meaningful sentence as summary."""
        if not post_body:
            return "[no summary available]"
        lines = [l.strip() for l in post_body.split("\n") if l.strip()]
        for line in lines:
            if len(line) > 20:
                return line[:200]
        return post_body[:200] if post_body else "[no summary available]"