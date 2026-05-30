import requests, time, hashlib, json, os
from pathlib import Path
from datetime import datetime

CACHE_DIR = Path(os.environ.get("TEMP", "/tmp")) / "mercadolibre_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_TTL = 1800

def _cached_get(url, headers, timeout=10):
    cache_key = hashlib.md5(f"ml:{url}".encode()).hexdigest()
    cache_file = CACHE_DIR / f"{cache_key}.json"
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            if time.time() - data["ts"] < CACHE_TTL: return data["content"], True
        except: cache_file.unlink(missing_ok=True)
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.status_code == 200:
            cache_file.write_text(json.dumps({"ts": time.time(), "content": r.text[:50000]}))
            return r.text[:50000], False
    except: pass
    return None, False

# ✅ Mapeo multi-país para MercadoLibre
_ML_SITE_MAP = {
    "argentina": "MLA",
    "mexico": "MLM",
    "paraguay": "MLU",
    "uruguay": "MLU",
    "colombia": "MCO",
    "brasil": "MLB",
}

class MercadoLibreIngestor:
    def __init__(self, query=None, pais="paraguay"):
        self.query = query or ""
        self.pais = pais.lower()
        self.headers = {
            "User-Agent": "TrendQA/1.0 (https://api.sikuri.lat)",
            "Accept": "application/json"
        }

    def fetch(self, **kwargs):
        limit = kwargs.get("limit", kwargs.get("max_results", 5))
        if not self.query: return []
        items, now = [], datetime.now()
        site_id = _ML_SITE_MAP.get(self.pais, "MLU")
        url = f"https://api.mercadolibre.com/sites/{site_id}/search?q={requests.utils.quote(self.query)}&limit=15"
        data, _ = _cached_get(url, self.headers, timeout=8)
        if not data: return items
        try:
            res = json.loads(data)
            results = res.get("results", [])
            if not isinstance(results, list): return items
        except: return items
        for listing in results[:limit + 3]:
            if len(items) >= limit: break
            if not isinstance(listing, dict): continue
            title = listing.get("title", "").strip()
            if not title or len(title) < 5: continue
            items.append({
                "id": f"ml_{listing.get('id', hash(title))}",
                "title": title[:200],
                "content": f"{listing.get('category_id', '')} - {listing.get('condition', 'Nuevo')}".strip()[:250],
                "url": listing.get("permalink", ""),
                "author": f"MercadoLibre {site_id}",
                "created_utc": now.timestamp(), "created_at": now.isoformat(),
                "raw_json": None, "item_type": "product_listing",
                "source_name": f"MercadoLibre ({site_id})", "source_type": "mercadolibre",
            })
        return items[:limit]
