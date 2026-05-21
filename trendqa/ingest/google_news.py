import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta


class GoogleNewsIngestor:
    def __init__(self, query=None, days=90):
        self.limit_date = datetime.now() - timedelta(days=days)
        self.query_words = [w for w in (query.lower().split() if query else []) if len(w) > 2 and w != "paraguay"]
        self.query = query or ""
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "es-419,es;q=0.9",
        }

    def fetch(self, max_results=15):
        items = []
        if not self.query:
            return items
        try:
            url = f"https://news.google.com/search?q={requests.utils.quote(self.query)}&hl=es-419&gl=PY&ceid=PY:es-419"
            r = requests.get(url, headers=self.headers, timeout=8)
            if r.status_code != 200:
                return items
            soup = BeautifulSoup(r.text, "html.parser")

            articles = (
                soup.select("article")
                or soup.select("div[jscontroller]")
                or soup.select("div[class*='article']")
                or soup.select("div[class*='card']")
                or soup.find_all("div", class_=re.compile(r"article|story|card"))
                or [soup]
            )

            seen = set()
            for art in articles[:max_results]:
                title = ""
                for sel in (
                    "h3 a",
                    "h4 a",
                    "a[href*='./articles/']",
                    "a[class*='title']",
                    "h3",
                    "h4",
                    "a[class*='story']",
                    img_alt := ("img[alt]", lambda e: e.get("alt", "")),
                ):
                    if isinstance(sel, tuple):
                        el = art.select_one(sel[0])
                        if el:
                            title = sel[1](el)
                    else:
                        el = art.select_one(sel)
                        if el:
                            title = el.get_text(strip=True) or el.get("title", "")
                    if title:
                        break

                if not title:
                    continue
                title = title.strip()
                if not title or title in seen:
                    continue
                seen.add(title)

                link = ""
                for sel in (
                    "h3 a",
                    "h4 a",
                    "a[href*='./articles/']",
                    "a[href*='./']",
                    "a[href]",
                ):
                    el = art.select_one(sel)
                    if el:
                        href = el.get("href", "")
                        if href.startswith("./"):
                            href = "https://news.google.com" + href[1:]
                        if href and href != "#":
                            link = href
                            break

                snippet = ""
                for sel in (
                    "span[role='text']",
                    "p",
                    "div[class*='snippet']",
                    "span[class*='summary']",
                ):
                    el = art.select_one(sel)
                    if el:
                        snippet = el.get_text(strip=True)
                        if snippet:
                            break

                source_name = ""
                for sel in (
                    "div[aria-label*=':']",
                    "time",
                    "span[class*='source']",
                    "a[class*='source']",
                ):
                    el = art.select_one(sel)
                    if el:
                        txt = el.get_text(strip=True)
                        if txt and len(txt) < 80:
                            source_name = txt
                            break

                if not source_name:
                    m = re.search(r"/([^/]+?)(?:\?|$)", link)
                    if m:
                        source_name = m.group(1).replace("-", " ").title()

                created_str = ""
                time_el = art.select_one("time")
                if time_el:
                    created_str = time_el.get("datetime", "") or time_el.get_text(strip=True)

                created_dt = None
                for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                    try:
                        created_dt = datetime.strptime(created_str[:19], fmt)
                        break
                    except Exception:
                        continue

                if created_dt and created_dt < self.limit_date:
                    continue

                content = title
                if snippet:
                    content += ". " + snippet

                items.append({
                    "id": f"gn_{hash(title)}",
                    "title": title,
                    "content": content,
                    "url": link,
                    "author": source_name or "Google News",
                    "created_utc": created_dt.timestamp() if created_dt else None,
                    "created_at": created_str or datetime.now().isoformat(),
                    "raw_json": None,
                    "item_type": "news_article",
                    "source_name": f"Google News - {source_name}" if source_name else "Google News",
                    "source_type": "google_news",
                })
        except Exception:
            pass
        return items
