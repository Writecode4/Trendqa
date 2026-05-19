import re
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup


class RedditIngestor:
    def __init__(self, query=None, subreddit="Paraguay", days=90):
        self.subreddit = subreddit
        self.limit_date = datetime.now() - timedelta(days=days)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0"
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

    def get_comments(self, post_id, limit=20):
        url = f"https://www.reddit.com/comments/{post_id}.json?sort=top&limit={limit}"
        try:
            r = requests.get(url, headers=self.headers, timeout=15)
            if r.status_code != 200:
                return []
            data = r.json()
            comments = data[1].get("data", {}).get("children", [])
            out = []
            for c in comments:
                body = c.get("data", {}).get("body", "")
                if body and body not in ("[deleted]", "[removed]"):
                    out.append(body.strip())
                replies = c.get("data", {}).get("replies", {})
                if isinstance(replies, dict):
                    more_children = replies.get("data", {}).get("children", [])
                    for rc in more_children:
                        rbody = rc.get("data", {}).get("body", "")
                        if rbody and rbody not in ("[deleted]", "[removed]"):
                            out.append(rbody.strip())
            return out[:limit]
        except Exception:
            return []

    def _scrape_with_bs(self, url, max_posts):
        """Fallback: scrape Reddit HTML directamente con BS cuando la API falla."""
        items = []
        try:
            r = requests.get(url, headers={**self.headers, "Accept": "text/html"}, timeout=15)
            if r.status_code != 200:
                return items
            soup = BeautifulSoup(r.text, "html.parser")
            posts = (
                soup.select("div[data-testid='post-container']")
                or soup.select("div.Post")
                or soup.select("div[class*='post']")
                or soup.select("div[class*='Post']")
                or soup.find_all("div", class_=re.compile(r"post|Post|thread"))
                or [soup]
            )
            for post in posts[:max_posts]:
                title = ""
                for sel in ("h3", "h2", "a[class*='title']", "a[data-click-id='title']"):
                    el = post.select_one(sel)
                    if el:
                        title = el.get_text(strip=True)
                        if title:
                            break
                if not title:
                    continue

                body = ""
                for sel in ("div[class*='text'] p", "p", "div[class*='content']", "div[class*='body']"):
                    el = post.select_one(sel)
                    if el:
                        body = el.get_text(strip=True)[:500]
                        if body:
                            break

                author = ""
                for sel in ("a[class*='author']", "span[class*='author']", "a[data-testid='author']"):
                    el = post.select_one(sel)
                    if el:
                        author = el.get_text(strip=True)
                        if author:
                            break

                link = ""
                for sel in ("a[data-click-id='title']", "a[class*='title']", "a[href*='/r/']"):
                    el = post.select_one(sel)
                    if el:
                        href = el.get("href", "")
                        if href.startswith("/"):
                            href = "https://reddit.com" + href
                        link = href
                        if link:
                            break

                created_str = ""
                time_el = post.select_one("time") or post.select_one("a[data-testid='post_timestamp']")
                if time_el:
                    created_str = time_el.get("datetime", "") or time_el.get_text(strip=True)

                created_dt = None
                for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                    try:
                        created_dt = datetime.strptime(created_str[:19].replace("T", " "), fmt)
                        break
                    except Exception:
                        continue

                if created_dt and created_dt < self.limit_date:
                    continue

                content = title
                if body:
                    content += "\n\n" + body

                items.append({
                    "id": f"reddit_html_{hash(title + link)}",
                    "title": title[:200],
                    "content": content,
                    "url": link,
                    "author": author or None,
                    "created_utc": created_dt.timestamp() if created_dt else None,
                    "created_at": created_str or datetime.now().isoformat(),
                    "raw_json": None,
                    "item_type": "reddit_post",
                    "source_name": f"r/{self.subreddit}",
                    "source_type": "reddit",
                })
        except Exception:
            pass
        return items

    def _fetch_json(self, url, limit):
        """Método principal: API JSON de Reddit."""
        try:
            r = requests.get(url, headers=self.headers, timeout=15)
            if r.status_code != 200:
                return []
            posts = r.json().get("data", {}).get("children", [])
            items = []
            seen = set()
            for p in posts:
                d = p.get("data", {})
                post_id = d.get("id")
                created_utc = d.get("created_utc")
                if not post_id or post_id in seen or not self.is_recent(created_utc):
                    continue
                title = (d.get("title") or "").strip()
                body = (d.get("selftext") or "").strip()
                comments = self.get_comments(post_id)
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
                seen.add(post_id)
            return items
        except Exception:
            return []

    def fetch(self, limit=25):
        items = []

        # Estrategia 1: API JSON con múltiples queries y órdenes
        queries = [self.query] if self.query else [
            "courier paraguay", "comprar de amazon", "bancard", "via miami",
            "marketplace facebook paraguay", "tienda instagram py", "estafa compras",
        ]
        for sort in ("new", "relevance", "top"):
            for q in queries:
                url = f"https://www.reddit.com/r/{self.subreddit}/search.json?q={q}&restrict_sr=1&sort={sort}&limit={limit}"
                fetched = self._fetch_json(url, limit)
                items.extend(fetched)
                if len(items) >= limit * 3:
                    break
            if len(items) >= limit * 3:
                break

        # Estrategia 2: Front page del subreddit via API
        if len(items) < 5:
            url = f"https://www.reddit.com/r/{self.subreddit}.json?limit={limit}"
            fetched = self._fetch_json(url, limit)
            items.extend(fetched)

        # Estrategia 3: Buscar en r/Asuncion también
        if len(items) < 5 and self.query:
            url = f"https://www.reddit.com/r/Asuncion/search.json?q={self.query}&restrict_sr=1&sort=new&limit={limit}"
            fetched = self._fetch_json(url, limit)
            for it in fetched:
                it["source_name"] = "r/Asuncion"
            items.extend(fetched)

        # Estrategia 4: Fallback — scrape HTML directamente
        if len(items) < 5:
            for q in (queries if self.query else queries[:2]):
                url = f"https://www.reddit.com/r/{self.subreddit}/search?q={q}&sort=new"
                fetched = self._scrape_with_bs(url, limit)
                items.extend(fetched)
                if items:
                    break

        # Remover duplicados manteniendo orden
        seen_ids = set()
        deduped = []
        for it in items:
            if it["id"] not in seen_ids:
                seen_ids.add(it["id"])
                deduped.append(it)

        return deduped
