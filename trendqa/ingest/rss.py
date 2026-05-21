import re
import feedparser
import hashlib
import json
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup


class RSSIngestor:
    def __init__(self, query=None, days=90):
        self.limit_date = datetime.now() - timedelta(days=days)
        self.query_words = [w for w in (query.lower().split() if query else []) if len(w) > 2 and w != "paraguay"]
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0",
            "Accept-Language": "es-419,es;q=0.9",
        }
        self.feeds = {
            "ABC Economía": "https://www.abc.com.py/arc/outboundfeeds/rss/category/economía/?outputType=xml",
            "Última Hora Economía": "https://www.ultimahora.com/rss/economia.xml",
            "La Nación Economía": "https://www.lanacion.com.py/rss/economia/",
            "MarketData": "https://marketdata.com.py/feed/",
            "ABC Negocios": "https://www.abc.com.py/arc/outboundfeeds/rss/category/negocios/?outputType=xml",
            "Última Hora Negocios": "https://www.ultimahora.com/rss/negocios.xml",
        }

    def _parse_entry(self, entry, source_name):
        link = entry.get("link", "")
        if not link:
            return None

        published = entry.get("published_parsed") or entry.get("updated_parsed")
        dt_published = None
        if published:
            dt_published = datetime(*published[:6])
            if dt_published < self.limit_date:
                return None

        title = (entry.get("title") or "").strip()
        summary = (entry.get("summary") or entry.get("description") or "").strip()

        if self.query_words:
            haystack = f"{title.lower()} {summary.lower()}"
            if not any(w in haystack for w in self.query_words):
                return None

        return {
            "id": f"rss_{hashlib.md5(link.encode()).hexdigest()}",
            "title": title,
            "content": summary,
            "url": link,
            "author": entry.get("author"),
            "created_utc": dt_published.timestamp() if dt_published else None,
            "created_at": dt_published.isoformat() if dt_published else None,
            "raw_json": json.dumps(dict(entry), default=str)[:20000],
            "item_type": "rss_article",
            "source_name": source_name,
            "source_type": "rss",
        }

    def _scrape_feed_html(self, url, source_name):
        """Fallback: scrape HTML de la página principal del medio cuando el feed XML falla."""
        items = []
        try:
            r = requests.get(url, headers=self.headers, timeout=20)
            if r.status_code != 200:
                return items
            soup = BeautifulSoup(r.text, "html.parser")
            articles = (
                soup.select("article")
                or soup.select("div[class*='article']")
                or soup.select("div[class*='story']")
                or soup.select("div[class*='post']")
                or soup.select("div[class*='entry']")
                or soup.find_all("div", class_=re.compile(r"article|story|post|entry|card|item"))
                or [soup]
            )
            seen = set()
            for art in articles[:15]:
                title = ""
                for sel in ("h2 a", "h3 a", "h2", "h3", "a[class*='title']", "img[alt]"):
                    el = art.select_one(sel)
                    if el:
                        title = el.get("alt", "") if el.name == "img" else el.get_text(strip=True)
                        if title:
                            break
                if not title or title in seen:
                    continue
                seen.add(title)

                link = ""
                for sel in ("h2 a", "h3 a", "a[href]", "a[class*='link']"):
                    el = art.select_one(sel)
                    if el:
                        href = el.get("href", "")
                        if href and href != "#" and not href.startswith("#"):
                            if href.startswith("/"):
                                # Intentar extraer dominio base
                                from urllib.parse import urlparse
                                parsed = urlparse(url)
                                href = f"{parsed.scheme}://{parsed.netloc}{href}"
                            link = href
                            break

                summary = ""
                for sel in ("p", "div[class*='summary']", "span[class*='summary']", "div[class*='excerpt']", "div[class*='description']"):
                    el = art.select_one(sel)
                    if el:
                        summary = el.get_text(strip=True)[:500]
                        if summary:
                            break

                if self.query_words:
                    haystack = f"{title.lower()} {summary.lower()}"
                    if not any(w in haystack for w in self.query_words):
                        continue

                items.append({
                    "id": f"rss_html_{hashlib.md5((title + link).encode()).hexdigest()}",
                    "title": title[:200],
                    "content": summary or title,
                    "url": link,
                    "author": None,
                    "created_utc": datetime.now().timestamp(),
                    "created_at": datetime.now().isoformat(),
                    "raw_json": None,
                    "item_type": "rss_article",
                    "source_name": f"{source_name} (scrape)",
                    "source_type": "rss",
                })
        except Exception:
            pass
        return items

    def fetch(self):
        items = []
        seen = set()

        # Estrategia 1: feedparser
        for name, url in self.feeds.items():
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries:
                    parsed = self._parse_entry(entry, name)
                    if parsed and parsed["url"] not in seen:
                        seen.add(parsed["url"])
                        items.append(parsed)
            except Exception:
                continue

        # Estrategia 2: Si no hay suficientes items, scrape HTML directo de los sitios
        if len(items) < 5:
            html_feeds = {
                "ABC Color": "https://www.abc.com.py/",
                "Última Hora": "https://www.ultimahora.com/",
                "La Nación": "https://www.lanacion.com.py/",
                "MarketData": "https://marketdata.com.py/",
            }
            for name, url in html_feeds.items():
                scraped = self._scrape_feed_html(url, name)
                for s in scraped:
                    if s["url"] not in seen:
                        seen.add(s["url"])
                        items.append(s)

        # Estrategia 3: Scrapear sección de economía directa si el query es económico
        if len(items) < 5:
            econ_urls = [
                ("ABC Economía (scrape)", "https://www.abc.com.py/economia/"),
                ("Última Hora Economía (scrape)", "https://www.ultimahora.com/economia/"),
            ]
            for name, url in econ_urls:
                scraped = self._scrape_feed_html(url, name)
                for s in scraped:
                    if s["url"] not in seen:
                        seen.add(s["url"])
                        items.append(s)

        return items
