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
        tweets = soup.find_all("div", class_="timeline-item")
        if not tweets:
            tweets = soup.select("div[class*='tweet']")
        for tweet in tweets:
            if len(items) >= max_results:
                break
            content_el = tweet.select_one(".tweet-content")
            if not content_el:
                continue
            text = content_el.get_text(strip=True)
            if not text or text in seen:
                continue
            seen.add(text)
            tid = tweet.get("id", "") or str(hash(text))
            author_el = tweet.select_one(".username") or tweet.select_one("a[href*='/']")
            author = ""
            if author_el:
                author = author_el.get_text(strip=True).lstrip("@")
            url_el = tweet.select_one("a.tweet-link") or tweet.select_one("a[href*='/status/']")
            tweet_url = ""
            if url_el:
                href = url_el.get("href", "")
                if href.startswith("/"):
                    href = instance + href
                tweet_url = href
            date_el = tweet.select_one(".tweet-date a") or tweet.select_one("time")
            created_str = ""
            if date_el:
                created_str = date_el.get("datetime", "") or date_el.get_text(strip=True)
            created_dt = None
            try:
                for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                    try:
                        created_dt = datetime.strptime(created_str[:19].replace("T", " "), fmt)
                        break
                    except ValueError:
                        continue
            except Exception:
                pass
            if created_dt and created_dt < self.limit_date:
                continue
            items.append({
                "id": f"x_scrape_{tid}",
                "title": text[:120],
                "content": text,
                "url": tweet_url,
                "author": author,
                "created_utc": created_dt.timestamp() if created_dt else None,
                "created_at": created_str,
                "raw_json": None,
                "item_type": "tweet",
                "source_name": "X (Twitter)",
                "source_type": "x",
            })
        return items
