import requests, time, hashlib, os
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup

CACHE_DIR = Path(os.environ.get("TEMP", "/tmp")) / "mercadolibre_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_TTL = 1800

def _cached_get(url, headers, timeout=10):
    cache_key = hashlib.md5(f"ml:{url}".encode()).hexdigest()
    cache_file = CACHE_DIR / f"{cache_key}.html"
    if cache_file.exists():
        try:
            if time.time() - cache_file.stat().st_mtime < CACHE_TTL:
                return cache_file.read_text(errors="ignore"), True
        except: cache_file.unlink(missing_ok=True)
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.status_code == 200:
            cache_file.write_text(r.text, encoding="utf-8")
            return r.text, False
    except: pass
    return None, False

_ML_DOMAIN_MAP = {
    "argentina": "mercadolibre.com.ar",
    "mexico": "mercadolibre.com.mx",
    "paraguay": "mercadolibre.com.py",
    "colombia": "mercadolibre.com.co",
    "brasil": "mercadolibre.com.br",
    "chile": "mercadolibre.cl",
    "uruguay": "mercadolibre.com.uy",
}

class MercadoLibreIngestor:
    def __init__(self, query=None, pais="paraguay"):
        self.query = query or ""
        self.pais = pais.lower()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "es-419,es;q=0.9",
        }

    def fetch(self, **kwargs):
        limit = kwargs.get("limit", kwargs.get("max_results", 5))
        if not self.query: return []
        items, now = [], datetime.now()
        domain = _ML_DOMAIN_MAP.get(self.pais, "mercadolibre.com.py")
        url = f"https://www.{domain}/search?q={requests.utils.quote(self.query)}"
        html, _ = _cached_get(url, self.headers, timeout=10)
        if not html: return items
        try:
            soup = BeautifulSoup(html, "html.parser")
            for listing in soup.select("ol.ui-search-layout li.ui-search-layout__item"):
                if len(items) >= limit: break
                title_el = listing.select_one("h2.ui-search-item__title")
                if not title_el: continue
                title = title_el.text.strip()
                if not title or len(title) < 5: continue
                link_el = listing.select_one("a.ui-search-link")
                link = link_el.get("href", "") if link_el else ""
                price_el = listing.select_one("span.andes-money-amount__fraction")
                price = price_el.text.strip() if price_el else ""
                cond_el = listing.select_one("span.ui-search-item__group__element")
                condition = cond_el.text.strip()[:50] if cond_el else ""
                items.append({
                    "id": f"ml_{hashlib.md5(title.encode()).hexdigest()[:10]}",
                    "title": title[:200],
                    "content": f"Precio: {price} - {condition}".strip()[:250],
                    "url": link,
                    "author": f"MercadoLibre ({domain})",
                    "created_utc": now.timestamp(), "created_at": now.isoformat(),
                    "raw_json": None, "item_type": "product_listing",
                    "source_name": f"MercadoLibre ({domain})", "source_type": "mercadolibre",
                })
        except: pass
        return items[:limit]
