import requests
import time
import hashlib
import json
from pathlib import Path
from datetime import datetime

# Configuración de caché en disco
CACHE_DIR = Path("/tmp/x_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_TTL = 1800  # 30 minutos

def _cached_get(url, headers, timeout=10):
    """GET con caché en disco."""
    cache_key = hashlib.md5(f"x:{url}".encode()).hexdigest()
    cache_file = CACHE_DIR / f"{cache_key}.json"
    
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            if time.time() - data["ts"] < CACHE_TTL:
                return data["content"], True
        except:
            cache_file.unlink(missing_ok=True)
            
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.status_code == 200:
            cache_file.write_text(json.dumps({"ts": time.time(), "content": r.text[:50000]}))
            return r.text[:50000], False
    except:
        pass
    return None, False


class XIngestor:
    def __init__(self, query=None, **kwargs):
        self.query = query or ""
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "es-419,es;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

    def fetch(self, **kwargs):  # ✅ Firma flexible
        """Obtiene posts de X con caché, timeout y límites estrictos."""
        limit = kwargs.get("limit", kwargs.get("max_results", 5))
        
        if not self.query:
            return []

        items = []
        now = datetime.now()
        
        # Usa Nitter público o endpoint de búsqueda compatible (ajusta si tu versión usa API privada)
        url = f"https://nitter.net/search?f=tweets&q={requests.utils.quote(self.query)}&l"
        
        html, _ = _cached_get(url, self.headers, timeout=10)
        if not html:
            return items

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            tweets = soup.select("div.tweet-body")[:limit + 3]
            
            for t in tweets:
                if len(items) >= limit:
                    break
                    
                link_el = t.select_one("a.tweet-link")
                text_el = t.select_one("div.tweet-content")
                time_el = t.select_one("span.tweet-date")
                author_el = t.select_one("a.username")
                
                if not text_el:
                    continue
                    
                text = text_el.get_text(strip=True).replace("\n", " ")
                link = f"https://x.com{link_el['href']}" if link_el else ""
                author = author_el.text.strip().replace("@", "") if author_el else "unknown"
                timestamp = time_el["title"] if time_el else now.isoformat()
                
                items.append({
                    "id": f"x_{hashlib.md5(text.encode()).hexdigest()[:10]}",
                    "title": text[:150],
                    "content": text[:300],
                    "url": link,
                    "author": author,
                    "created_utc": now.timestamp(),
                    "created_at": timestamp,
                    "raw_json": None,
                    "item_type": "x_post",
                    "source_name": "X (Twitter)",
                    "source_type": "x",
                })
        except Exception:
            pass

        return items[:limit]
