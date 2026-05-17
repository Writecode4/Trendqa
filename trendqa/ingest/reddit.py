import requests
from datetime import datetime, timedelta


class RedditIngestor:
    def __init__(self, subreddit="Paraguay", days=90):
        self.subreddit = subreddit
        self.limit_date = datetime.now() - timedelta(days=days)
        self.headers = {
            "User-Agent": "trendqa/1.0 by JuanCarlos"
        }
        self.keywords = [
            "courier paraguay", "comprar de amazon", "bancard", "via miami",
            "marketplace facebook paraguay", "tienda instagram py", "estafa compras"
        ]

    def is_recent(self, created_utc):
        if not created_utc:
            return False
        try:
            return datetime.fromtimestamp(created_utc) > self.limit_date
        except Exception:
            return False

    def get_comments(self, post_id, limit=10):
        url = f"https://www.reddit.com/comments/{post_id}.json?sort=top&limit={limit}"
        try:
            r = requests.get(url, headers=self.headers, timeout=15)
            if r.status_code != 200:
                return []
            data = r.json()
            comments = data[1].get("data", {}).get("children", [])
            out = []
            for c in comments:
                body = c.get("data", {}).get("body", "")
                if body and body not in ("[deleted]", "[removed]"):
                    out.append(body.strip())
            return out[:10]
        except Exception:
            return []

    def fetch(self, limit=25):
        items = []
        seen = set()

        for query in self.keywords:
            url = f"https://www.reddit.com/r/{self.subreddit}/search.json?q={query}&restrict_sr=1&sort=new&limit={limit}"
            try:
                r = requests.get(url, headers=self.headers, timeout=15)
                if r.status_code != 200:
                    continue

                posts = r.json().get("data", {}).get("children", [])
                for p in posts:
                    d = p.get("data", {})
                    post_id = d.get("id")
                    created_utc = d.get("created_utc")

                    if not post_id or post_id in seen or not self.is_recent(created_utc):
                        continue

                    title = (d.get("title") or "").strip()
                    body = (d.get("selftext") or "").strip()
                    comments = self.get_comments(post_id)

                    content = title
                    if body:
                        content += "\n\n" + body
                    if comments:
                        content += "\n\nTOP COMMENTS:\n" + " | ".join(comments)

                    items.append({
                        "id": post_id,
                        "title": title,
                        "content": content,
                        "url": f"https://reddit.com{d.get('permalink', '')}",
                        "author": d.get("author"),
                        "created_utc": created_utc,
                        "created_at": datetime.fromtimestamp(created_utc).isoformat() if created_utc else None,
                        "raw_json": None,
                        "item_type": "reddit_post",
                        "source_name": f"r/{self.subreddit}",
                        "source_type": "reddit"
                    })
                    seen.add(post_id)
            except Exception:
                continue

        return items