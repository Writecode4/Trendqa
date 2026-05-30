import requests
import time
import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime

CACHE_DIR = Path("/tmp/youtube_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_TTL = 1800

def _cached_get(url, headers, timeout=10):
    cache_key = hashlib.md5(f"yt:{url}".encode()).hexdigest()
    cache_file = CACHE_DIR / f"{cache_key}.xml"
    if cache_file.exists():
        if time.time() - cache_file.stat().st_mtime < CACHE_TTL:
            return cache_file.read_text(errors="ignore"), True
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.status_code == 200:
            cache_file.write_text(r.text, encoding="utf-8")
            return r.text, False
    except Exception:
        pass
    return None, False


class YouTubeIngestor:
    def __init__(self, query=None, **kwargs):
        self.query = query or ""
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/atom+xml, application/xml, text/xml, */*"
        }

    def _parse_video_id(self, url):
        if "/watch?v=" in url:
            return url.split("v=")[-1].split("&")[0]
        return url.rstrip("/").split("/")[-1]

    def fetch(self, **kwargs):
        limit = kwargs.get("limit", kwargs.get("max_results", 10))
        if not self.query:
            return []

        url = f"https://www.youtube.com/feeds/videos.xml?q={requests.utils.quote(self.query)}"
        xml_text, _ = _cached_get(url, self.headers, timeout=10)
        if not xml_text:
            return []

        items = []
        now = datetime.utcnow()
        try:
            root = ET.fromstring(xml_text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("atom:entry", ns):
                if len(items) >= limit:
                    break
                try:
                    title_el = entry.find("atom:title", ns)
                    title = title_el.text.strip() if title_el is not None else ""

                    link_el = entry.find("atom:link", ns)
                    link = link_el.get("href", "") if link_el is not None else ""

                    author_el = entry.find("atom:author", ns)
                    author = author_el.find("atom:name", ns).text.strip() if author_el is not None else "unknown"

                    published_el = entry.find("atom:published", ns)
                    published = published_el.text.strip() if published_el is not None else now.isoformat()

                    vid_id = self._parse_video_id(link)
                    content = f"Video: {title}. Ver en: {link}"

                    items.append({
                        "id": f"yt_{vid_id}" if vid_id else f"yt_{hashlib.md5(title.encode()).hexdigest()[:10]}",
                        "title": title[:200],
                        "content": content[:500],
                        "url": link,
                        "author": author,
                        "created_utc": now.timestamp(),
                        "created_at": published,
                        "raw_json": None,
                        "item_type": "youtube_video",
                        "source_name": "YouTube",
                        "source_type": "youtube",
                    })
                except Exception:
                    continue
        except ET.ParseError:
            pass

        return items[:limit]
