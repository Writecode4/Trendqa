import re
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup


class RedditIngestor:
    def __init__(self, query=None, subreddit="Paraguay", days=90):
        self.subreddit = subreddit
        self.limit_date = datetime.now() - timedelta(days=days)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0",
            "Accept": "application/json, text/html, */*",
        }
        self.query = query or ""
        self.query_words = [w for w in (query.lower().split() if query else []) if len(w) > 2 and w != "paraguay"]

    def is_recent(self, created_utc):
        if not created_utc:
            return False
        try:
            return datetime.fromtimestamp(created_utc) > self.limit_date
        except Exception:
            return False

    def get_comments(self, post_id, limit=10):
        url = f"https://www.reddit.com/comments/{post_id}.json?sort=top&limit={limit}"
        try:
            r = requests.get(url, headers=self.headers, timeout=10)
            if r.status_code != 200:
                return []
            data = r.json()
            comments = data[1].get("data", {}).get("children", [])
            out = []
            for c in comments:
                body = c.get("data", {}).get("body", "")
                if body and body not in ("[deleted]", "[removed]"):
                    out.append(body.strip())
            return out[:limit]
        except Exception:
            return []

    def _fetch_json(self, url, limit):
        try:
            r = requests.get(url, headers=self.headers, timeout=10)
            if r.status_code != 200:
                return []
            posts = r.json().get("data", {}).get("children", [])
            items = []
            for p in posts:
                d = p.get("data", {})
                post_id = d.get("id")
                created_utc = d.get("created_utc")
                if not post_id or not self.is_recent(created_utc):
                    continue
                title = (d.get("title") or "").strip()
                body = (d.get("selftext") or "").strip()
                comments = self.get_comments(post_id) if body else []
                content = title
                if body:
                    content += "\n\n" + body
                if comments:
                    content += "\n\nTOP COMMENTS:\n" + " | ".join(comments)
                items.append({
                    "id": post_id,
                    "title": title,
                    "content": content,
                    "url": f"https://reddit.com{d.get('permalink', '')}",
                    "author": d.get("author"),
                    "created_utc": created_utc,
                    "created_at": datetime.fromtimestamp(created_utc).isoformat() if created_utc else None,
                    "raw_json": None,
                    "item_type": "reddit_post",
                    "source_name": f"r/{self.subreddit}",
                    "source_type": "reddit",
                })
            return items
        except Exception:
            return []

    def _scrape_html(self, url, limit):
        items = []
        try:
            r = requests.get(url, headers={**self.headers, "Accept": "text/html"}, timeout=10)
            if r.status_code != 200:
                return items
            soup = BeautifulSoup(r.text, "html.parser")
            posts = (
                soup.select("div[data-testid='post-container']")
                or soup.select("div.Post")
                or soup.find_all("div", class_=re.compile(r"post|Post"))
                or [soup]
            )
            for post in posts[:limit]:
                title = ""
                for sel in ("h3", "a[data-click-id='title']"):
                    el = post.select_one(sel)
                    if el:
                        title = el.get_text(strip=True)
                        if title:
                            break
                if not title:
                    continue
                body = ""
                el = post.select_one("p")
                if el:
                    body = el.get_text(strip=True)[:500]
                link = ""
                el = post.select_one("a[data-click-id='title'], a[class*='title']")
                if el:
                    href = el.get("href", "")
                    if href.startswith("/"):
                        href = "https://reddit.com" + href
                    link = href
                items.append({
                    "id": f"reddit_html_{hash(title)}",
                    "title": title[:200],
                    "content": f"{title}\n\n{body}" if body else title,
                    "url": link,
                    "author": None,
                    "created_utc": None,
                    "created_at": datetime.now().isoformat(),
                    "raw_json": None,
                    "item_type": "reddit_post",
                    "source_name": f"r/{self.subreddit}",
                    "source_type": "reddit",
                })
        except Exception:
            pass
        return items

    def fetch(self, limit=25):
        items = []
        seen = set()

        # Query única optimizada: busca en new + relevance, no los 3 sorts
        q = self.query or "courier paraguay"

        for sort in ("relevance", "new"):
            url = f"https://www.reddit.com/r/{self.subreddit}/search.json?q={q}&restrict_sr=1&sort={sort}&limit={limit}"
            fetched = self._fetch_json(url, limit)
            for it in fetched:
                if it["id"] not in seen:
                    seen.add(it["id"])
                    items.append(it)
            if len(items) >= 5:
                break

        # Fallback: front page si no hay resultados
        if len(items) < 3:
            url = f"https://www.reddit.com/r/{self.subreddit}.json?limit={limit}"
            fetched = self._fetch_json(url, limit)
            for it in fetched:
                if it["id"] not in seen:
                    seen.add(it["id"])
                    items.append(it)

        # Fallback BS HTML
        if len(items) < 3:
            url = f"https://www.reddit.com/r/{self.subreddit}/search?q={q}&sort=new"
            fetched = self._scrape_html(url, limit)
            for it in fetched:
                if it["id"] not in seen:
                    seen.add(it["id"])
                    items.append(it)

        return items[:limit * 2]
