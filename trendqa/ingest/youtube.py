import requests, time, hashlib, json, os, re
from pathlib import Path
from datetime import datetime

CACHE_DIR = Path("/tmp/youtube_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_TTL = 1800

def _cached_get(url, headers, timeout=10):
    cache_key = hashlib.md5(f"yt:{url}".encode()).hexdigest()
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

class YouTubeIngestor:
    def __init__(self, query=None, **kwargs):
        self.query = query or ""
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "es-419,es;q=0.9",
        }

    def fetch(self, **kwargs):
        limit = kwargs.get("limit", kwargs.get("max_results", 10))
        if not self.query: return []
        url = f"https://www.youtube.com/results?search_query={requests.utils.quote(self.query)}"
        html, _ = _cached_get(url, self.headers, timeout=10)
        if not html: return []
        items, now = [], datetime.utcnow()
        try:
            match = re.search(r'var ytInitialData\s*=\s*({.*?});', html, re.DOTALL)
            if not match: return items
            data = json.loads(match.group(1))
            contents = (data.get("contents", {})
                .get("twoColumnSearchResultsRenderer", {})
                .get("primaryContents", {})
                .get("sectionListRenderer", {})
                .get("contents", []))
            for section in contents:
                items_list = (section.get("itemSectionRenderer", {})
                    .get("contents", []))
                for item_data in items_list:
                    if len(items) >= limit: break
                    renderer = item_data.get("videoRenderer", {})
                    if not renderer: continue
                    title_runs = renderer.get("title", {}).get("runs", [])
                    title = "".join(r.get("text", "") for r in title_runs)
                    if not title: continue
                    vid_id = renderer.get("videoId", "")
                    author_runs = renderer.get("ownerText", {}).get("runs", [])
                    author = "".join(r.get("text", "") for r in author_runs) if author_runs else "unknown"
                    length = renderer.get("lengthText", {}).get("simpleText", "")
                    views = renderer.get("viewCountText", {}).get("simpleText", "")
                    items.append({
                        "id": f"yt_{vid_id}" if vid_id else f"yt_{hashlib.md5(title.encode()).hexdigest()[:10]}",
                        "title": title[:200],
                        "content": f"Duración: {length} - {views}".strip()[:250],
                        "url": f"https://youtube.com/watch?v={vid_id}",
                        "author": author,
                        "created_utc": now.timestamp(),
                        "created_at": now.isoformat(),
                        "raw_json": None, "item_type": "youtube_video",
                        "source_name": "YouTube", "source_type": "youtube",
                    })
        except: pass
        return items[:limit]
