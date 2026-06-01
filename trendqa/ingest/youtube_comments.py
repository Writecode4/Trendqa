import requests, time, hashlib, json, os, re
from pathlib import Path
from datetime import datetime
from html import unescape

CACHE_DIR = Path(os.environ.get("TEMP", "/tmp")) / "yt_comments_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_TTL = 1800

def _cached_get(url, headers, timeout=10):
    cache_key = hashlib.md5(f"ytc:{url}".encode()).hexdigest()
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

class YouTubeCommentsIngestor:
    def __init__(self, query=None, **kwargs):
        self.query = query or ""
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "es-419,es;q=0.9",
        }

    def _get_video_ids(self, limit=3):
        search_url = f"https://www.youtube.com/results?search_query={requests.utils.quote(self.query)}"
        html, _ = _cached_get(search_url, self.headers, timeout=10)
        if not html: return []
        ids = re.findall(r'\/watch\?v=([a-zA-Z0-9_-]{11})', html)
        seen = set()
        unique = []
        for vid in ids:
            if vid not in seen:
                seen.add(vid)
                unique.append(vid)
                if len(unique) >= limit: break
        return unique

    def _extract_comments(self, video_id, limit=5):
        watch_url = f"https://www.youtube.com/watch?v={video_id}&hl=es"
        html, _ = _cached_get(watch_url, self.headers, timeout=10)
        if not html: return []
        match = re.search(r'var ytInitialData\s*=\s*({.*?});', html, re.DOTALL)
        if not match: return []
        comments = []
        try:
            data = json.loads(match.group(1))
            sections = (
                data.get("contents", {})
                .get("twoColumnWatchNextResults", {})
                .get("results", {})
                .get("results", {})
                .get("contents", [])
            )
            for section in sections:
                item_section = section.get("itemSectionRenderer", {})
                contents = item_section.get("contents", [])
                for cont in contents:
                    comment_thread = cont.get("commentThreadRenderer", {})
                    comment = comment_thread.get("comment", {})
                    renderer = comment.get("commentRenderer", {})
                    if not renderer: continue
                    text = renderer.get("contentText", {}).get("runs", [{}])
                    comment_text = "".join(
                        seg.get("text", "") for seg in text
                    )
                    author = renderer.get("authorText", {}).get("simpleText", "desconocido")
                    if comment_text:
                        comments.append({
                            "text": unescape(comment_text)[:500],
                            "author": author,
                        })
                        if len(comments) >= limit: break
                if len(comments) >= limit: break
        except: pass
        return comments

    def fetch(self, **kwargs):
        limit = kwargs.get("limit", kwargs.get("max_results", 10))
        if not self.query: return []
        items = []
        now = datetime.utcnow()
        video_ids = self._get_video_ids(limit=3)
        for vid in video_ids:
            if len(items) >= limit: break
            comments = self._extract_comments(vid, limit=max(2, limit // max(len(video_ids), 1)))
            for c in comments:
                if len(items) >= limit: break
                items.append({
                    "id": f"ytc_{hashlib.md5(c['text'].encode()).hexdigest()[:10]}",
                    "title": c["text"][:150],
                    "content": c["text"],
                    "url": f"https://youtube.com/watch?v={vid}",
                    "author": c["author"],
                    "created_utc": now.timestamp(),
                    "created_at": now.isoformat(),
                    "raw_json": None,
                    "item_type": "youtube_comment",
                    "source_name": "YouTube Comentarios",
                    "source_type": "youtube_comments",
                })
        return items[:limit]
