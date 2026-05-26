import json
import time
import hashlib
import requests
import os
from pathlib import Path
from datetime import datetime

# Configuración de caché (compatible Windows/Linux)
CACHE_DIR = Path(os.getenv("TEMP", "/tmp")) / "reddit_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_TTL = 1800  # 30 minutos
MAX_RESPONSE_SIZE = 200_000

def _cached_get(url, headers, timeout=10):
    """GET con caché en disco y límite de tamaño."""
    cache_key = hashlib.md5(url.encode()).hexdigest()
    cache_file = CACHE_DIR / f"{cache_key}.json"

    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            if time.time() - data["ts"] < CACHE_TTL:
                return data["content"], True
        except:
            cache_file.unlink(missing_ok=True)

    try:
        r = requests.get(url, headers=headers, timeout=timeout, stream=True)
        if r.status_code != 200:
            return None, False
        content = b""
        for chunk in r.iter_content(chunk_size=8192):
            content += chunk
            if len(content) >= MAX_RESPONSE_SIZE:
                break
        text = content.decode("utf-8", errors="ignore")[:MAX_RESPONSE_SIZE]
        if '"children"' in text:
            cache_file.write_text(json.dumps({"ts": time.time(), "content": text}))
        return text, False
    except Exception:
        return None, False


class RedditIngestor:
    def __init__(self, query=None, subreddit=None, **kwargs):
        self.query = query or ""
        self.subreddit = subreddit
        self.headers = {
            "User-Agent": "TrendQA/1.0 (https://api.sikuri.lat; trendqa@contact.com)",
            "Accept": "application/json"
        }

    def fetch(self, **kwargs):
        """Obtiene posts de Reddit con parseo 100% defensivo."""
        limit = kwargs.get("limit", kwargs.get("max_results", 10))
        if not self.query:
            return []

        items = []
        url = f"https://www.reddit.com/search.json?q={requests.utils.quote(self.query)}&limit=25&sort=new&t=month"
        if self.subreddit:
            url = f"https://www.reddit.com/r/{self.subreddit}/search.json?q={requests.utils.quote(self.query)}&restrict_sr=on&limit=25&sort=new"

        html, _ = _cached_get(url, self.headers, timeout=12)
        if not html:
            return []

        try:
            data = json.loads(html)
            if not isinstance(data, dict): return []
            data_section = data.get("data")
            if not isinstance(data_section, dict): return []
            posts = data_section.get("children", [])
            if not isinstance(posts, list): return []
        except Exception:
            return []

        now = datetime.now()
        for post in posts:
            try:
                if len(items) >= limit:
                    break
                if not isinstance(post, dict):
                    continue
                    
                d = post.get("data")
                if not isinstance(d, dict):
                    continue

                title = d.get("title")
                if not isinstance(title, str) or not title.strip():
                    continue

                # Timestamp seguro (maneja int, float, string o None)
                utc = d.get("created_utc")
                if utc:
                    try:
                        created_at = datetime.fromtimestamp(float(utc)).isoformat()
                    except Exception:
                        created_at = now.isoformat()
                else:
                    created_at = now.isoformat()

                items.append({
                    "id": f"reddit_{d.get('id', hash(title))}",
                    "title": title.strip()[:250],
                    "content": (d.get("selftext") or d.get("link_flair_text") or "")[:400],
                    "url": f"https://reddit.com{d.get('permalink', '')}",
                    "author": d.get("author") or "anonymous",
                    "created_utc": utc,
                    "created_at": created_at,
                    "raw_json": None,
                    "item_type": "reddit_post",
                    "source_name": "Reddit",
                    "source_type": "reddit",
                })
            except Exception:
                # Si un post específico está corrupto, lo saltamos sin romper el loop
                continue

        return items[:limit]
