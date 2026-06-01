import requests, time, hashlib, json
from pathlib import Path
from datetime import datetime

CACHE_DIR = Path("/tmp/x_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_TTL = 1800

def _cached_get(url, headers, timeout=10):
    cache_key = hashlib.md5(f"x:{url}".encode()).hexdigest()
    cache_file = CACHE_DIR / f"{cache_key}.json"
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            if time.time() - data["ts"] < CACHE_TTL:
                return data["content"], True
        except: cache_file.unlink(missing_ok=True)
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.status_code == 200:
            cache_file.write_text(json.dumps({"ts": time.time(), "content": r.text[:50000]}))
            return r.text[:50000], False
    except: pass
    return None, False

NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.skrep.in",
    "https://nitter.poast.org",
    "https://nitter.lucabased.xyz",
    "https://nitter.woodland.cafe",
    "https://nitter.cc",
]

class XIngestor:
    def __init__(self, query=None, **kwargs):
        self.query = query or ""
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "es-419,es;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

    def _try_instance(self, base_url, limit):
        url = f"{base_url}/search?f=tweets&q={requests.utils.quote(self.query)}&l"
        html, _ = _cached_get(url, self.headers, timeout=8)
        if not html or len(html) < 500: return None
        items = []
        now = datetime.now()
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            tweets = soup.select("div.tweet-body")[:limit + 3]
            for t in tweets:
                if len(items) >= limit: break
                text_el = t.select_one("div.tweet-content")
                if not text_el: continue
                text = text_el.get_text(strip=True).replace("\n", " ")
                link_el = t.select_one("a.tweet-link")
                link = f"https://x.com{link_el['href']}" if link_el else ""
                author_el = t.select_one("a.username")
                author = author_el.text.strip().replace("@", "") if author_el else "unknown"
                time_el = t.select_one("span.tweet-date")
                timestamp = time_el["title"] if time_el else now.isoformat()
                items.append({
                    "id": f"x_{hashlib.md5(text.encode()).hexdigest()[:10]}",
                    "title": text[:150],
                    "content": text[:300],
                    "url": link,
                    "author": author,
                    "created_utc": now.timestamp(),
                    "created_at": timestamp,
                    "raw_json": None, "item_type": "x_post",
                    "source_name": "X (Twitter)", "source_type": "x",
                })
        except: pass
        return items[:limit] if items else None

    def fetch(self, **kwargs):
        limit = kwargs.get("limit", kwargs.get("max_results", 5))
        if not self.query: return []
        for instance in NITTER_INSTANCES:
            result = self._try_instance(instance, limit)
            if result:
                return result
        return []
