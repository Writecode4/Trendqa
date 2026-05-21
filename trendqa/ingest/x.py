import re
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup


NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.poast.org",
    "https://nitter.1d4.us",
    "https://nitter.kavin.rocks",
    "https://nitter.freedit.eu",
    "https://nitter.lqdv.xyz",
    "https://nitter.esmaeilpour.xyz",
    "https://nitter.unixfox.eu",
    "https://nitter.sethforprivacy.com",
    "https://nitter.catsarchy.xyz",
]


class XIngestor:
    def __init__(self, query="courier paraguay", days=90):
        self.limit_date = datetime.now() - timedelta(days=days)
        self.query = query
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-419,es;q=0.9,en;q=0.7",
        }

    def fetch(self, max_results=30):
        for instance in NITTER_INSTANCES:
            try:
                items = self._scrape_instance(instance, max_results)
                if items:
                    return items
            except Exception:
                continue
        return []

    def _scrape_instance(self, instance, max_results):
        url = f"{instance}/search?q={requests.utils.quote(self.query)}&f=tweets"
        r = requests.get(url, headers=self.headers, timeout=20)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        items = []
        seen = set()

        tweet_blocks = (
            soup.find_all("div", class_="timeline-item")
            or soup.select("div[class*='tweet']")
            or soup.select("div[class*='timeline'] > div")
            or soup.find_all("div", class_=re.compile(r"tweet|timeline|status"))
            or soup.find_all("article")
            or [soup]
        )

        for tweet in tweet_blocks:
            if len(items) >= max_results:
                break

            text = ""
            for sel in (
                ".tweet-content",
                "div[class*='content'] p",
                "p",
                "div[class*='text']",
                "span[class*='text']",
                "div[class*='message']",
                "div[class*='body']",
            ):
                el = tweet.select_one(sel)
                if el:
                    text = el.get_text(strip=True)
                    if len(text) > 10:
                        break

            if not text or len(text) < 5:
                continue
            if text in seen:
                continue
            seen.add(text)

            tid = tweet.get("id", "") or str(hash(text))

            author = ""
            for sel in (
                ".username",
                "a[href*='/']",
                "span[class*='name']",
                "div[class*='author']",
                "a[class*='user']",
            ):
                el = tweet.select_one(sel)
                if el:
                    candidate = el.get_text(strip=True).lstrip("@")
                    if candidate and len(candidate) < 50 and not candidate.startswith("http"):
                        author = candidate
                        break

            tweet_url = ""
            for sel in (
                "a.tweet-link",
                "a[href*='/status/']",
                "a[class*='link']",
                "a[href]",
            ):
                el = tweet.select_one(sel)
                if el:
                    href = el.get("href", "")
                    if href and "/status/" in href:
                        if href.startswith("/"):
                            href = instance + href
                        tweet_url = href
                        break

            created_dt = None
            created_str = ""
            for sel in (
                ".tweet-date a",
                "time",
                "span[class*='date']",
                "a[class*='date']",
                "span[class*='time']",
            ):
                el = tweet.select_one(sel)
                if el:
                    created_str = el.get("datetime", "") or el.get("title", "") or el.get_text(strip=True)
                    if created_str:
                        break

            if created_str:
                for fmt in (
                    "%Y-%m-%dT%H:%M:%S%z",
                    "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d",
                ):
                    try:
                        cleaned = created_str[:19].replace("T", " ")
                        created_dt = datetime.strptime(cleaned, fmt)
                        break
                    except Exception:
                        continue

            if created_dt and created_dt < self.limit_date:
                continue

            items.append({
                "id": f"x_scrape_{tid}",
                "title": text[:120],
                "content": text,
                "url": tweet_url,
                "author": author,
                "created_utc": created_dt.timestamp() if created_dt else None,
                "created_at": created_str or datetime.now().isoformat(),
                "raw_json": None,
                "item_type": "tweet",
                "source_name": "X (Twitter)",
                "source_type": "x",
            })
        return items
