import re, time, hashlib, os
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup

CACHE_DIR = Path(os.getenv("TEMP", "/tmp")) / "reddit_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_TTL = 1800

def _cached_get(url, headers, timeout=10):
    cache_key = hashlib.md5(url.encode()).hexdigest()
    cache_file = CACHE_DIR / f"{cache_key}.html"
    if cache_file.exists():
        if time.time() - cache_file.stat().st_mtime < CACHE_TTL:
            return cache_file.read_text(errors="ignore"), True
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.status_code == 200:
            cache_file.write_text(r.text, encoding="utf-8")
            return r.text, False
    except: pass
    return None, False

import requests

class RedditIngestor:
    def __init__(self, query=None, subreddit=None, **kwargs):
        self.query = query or ""
        self.subreddit = subreddit
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "es-419,es;q=0.9",
        }

    def fetch(self, **kwargs):
        limit = kwargs.get("limit", kwargs.get("max_results", 10))
        if not self.query: return []
        items = []
        url = f"https://old.reddit.com/search?q={requests.utils.quote(self.query)}&sort=new&t=month&limit={limit*2}"
        if self.subreddit:
            url = f"https://old.reddit.com/r/{self.subreddit}/search?q={requests.utils.quote(self.query)}&restrict_sr=on&sort=new&t=month&limit={limit*2}"
        html, _ = _cached_get(url, self.headers, timeout=12)
        if not html: return []
        now = datetime.now()
        try:
            soup = BeautifulSoup(html, "html.parser")
            for post in soup.select("div.thing"):
                if len(items) >= limit: break
                title_el = post.select_one("a.title")
                if not title_el: continue
                title = title_el.text.strip()
                if not title or len(title) < 5: continue
                link = title_el.get("href", "")
                if link.startswith("/r/"):
                    link = f"https://reddit.com{link}"
                author_el = post.select_one("a.author")
                author = author_el.text.strip() if author_el else "anonymous"
                time_el = post.select_one("time")
                created_at = time_el["datetime"] if time_el and time_el.has_attr("datetime") else now.isoformat()
                tagline = post.select_one("p.tagline")
                extra = tagline.get_text(" ", strip=True)[:150] if tagline else ""
                items.append({
                    "id": f"reddit_{post.get('data-fullname', hashlib.md5(title.encode()).hexdigest()[:8])}",
                    "title": title[:250],
                    "content": extra[:400],
                    "url": link,
                    "author": author,
                    "created_utc": None,
                    "created_at": created_at,
                    "raw_json": None, "item_type": "reddit_post",
                    "source_name": "Reddit", "source_type": "reddit",
                })
        except: pass
        return items[:limit]
