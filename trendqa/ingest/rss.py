import feedparser
import hashlib
import json
from datetime import datetime, timedelta


class RSSIngestor:
    def __init__(self, days=90):
        self.limit_date = datetime.now() - timedelta(days=days)
        self.feeds = {
            "ABC Economía": "https://www.abc.com.py/arc/outboundfeeds/rss/category/economía/?outputType=xml",
            "Última Hora Economía": "https://www.ultimahora.com/rss/economia.xml",
            "La Nación Economía": "https://www.lanacion.com.py/rss/economia/",
            "MarketData": "https://marketdata.com.py/feed/"
        }

    def fetch(self):
        items = []
        seen = set()

        for name, url in self.feeds.items():
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries:
                    link = entry.get("link", "")
                    if not link or link in seen:
                        continue

                    published = entry.get("published_parsed") or entry.get("updated_parsed")
                    dt_published = None
                    if published:
                        dt_published = datetime(*published[:6])
                        if dt_published < self.limit_date:
                            continue

                    title = (entry.get("title") or "").strip()
                    summary = (entry.get("summary") or entry.get("description") or "").strip()

                    items.append({
                        "id": f"rss_{hashlib.md5(link.encode()).hexdigest()}",
                        "title": title,
                        "content": summary,
                        "url": link,
                        "author": entry.get("author"),
                        "created_utc": dt_published.timestamp() if dt_published else None,
                        "created_at": dt_published.isoformat() if dt_published else None,
                        "raw_json": json.dumps(dict(entry), default=str)[:20000],
                        "item_type": "rss_article",
                        "source_name": name,
                        "source_type": "rss"
                    })
                    seen.add(link)
            except Exception:
                continue

        return items