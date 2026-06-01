import requests, time, hashlib, json, os, re
from pathlib import Path
from datetime import datetime

CACHE_DIR = Path(os.environ.get("TEMP", "/tmp")) / "tiktok_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_TTL = 1800

def _cached_get(url, headers, timeout=10):
    cache_key = hashlib.md5(f"tt:{url}".encode()).hexdigest()
    cache_file = CACHE_DIR / f"{cache_key}.json"
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            if time.time() - data["ts"] < CACHE_TTL: return data["content"], True
        except: cache_file.unlink(missing_ok=True)
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.status_code == 200:
            cache_file.write_text(json.dumps({"ts": time.time(), "content": r.text[:100000]}))
            return r.text[:100000], False
    except: pass
    return None, False

_TRENDS = {
    "brasil": "https://ads.tiktok.com/business/creativecenter/popular/pad",
    "mexico": "https://ads.tiktok.com/business/creativecenter/popular/pad",
}

class TikTokIngestor:
    def __init__(self, query=None, pais="paraguay"):
        self.query = query or ""
        self.pais = pais.lower()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-419,es;q=0.9",
        }

    def _search_web(self, limit=5):
        url = f"https://www.tiktok.com/search?q={requests.utils.quote(self.query)}&lang=es"
        html, _ = _cached_get(url, self.headers, timeout=10)
        if not html: return []
        items = []
        try:
            ids = re.findall(r'/video/(\d+)', html)
            texts = re.findall(r'<span[^>]*>([^<]{10,300})</span>', html)
            seen = set()
            for i, vid in enumerate(ids):
                if vid in seen: continue
                seen.add(vid)
                text = texts[i] if i < len(texts) else ""
                items.append({
                    "id": f"tt_{vid}",
                    "title": text[:150] if text else f"TikTok {vid[:8]}",
                    "content": text[:300] if text else "",
                    "url": f"https://www.tiktok.com/@user/video/{vid}",
                    "author": "TikTok",
                    "created_utc": time.time(),
                    "created_at": datetime.now().isoformat(),
                    "raw_json": None,
                    "item_type": "tiktok_video",
                    "source_name": "TikTok",
                    "source_type": "tiktok",
                })
                if len(items) >= limit: break
        except: pass
        return items

    def fetch(self, **kwargs):
        limit = kwargs.get("limit", kwargs.get("max_results", 5))
        if not self.query: return []
        return self._search_web(limit=limit)
