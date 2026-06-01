import requests, time, hashlib, json, os
from pathlib import Path
from datetime import datetime

CACHE_DIR = Path(os.environ.get("TEMP", "/tmp")) / "shopee_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_TTL = 1800

def _cached_get(url, headers, timeout=10):
    cache_key = hashlib.md5(f"sp:{url}".encode()).hexdigest()
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

_SHOPEE_SITES = {
    "brasil": "shopee.com.br",
    "mexico": "shopee.com.mx",
    "colombia": "shopee.com.co",
    "argentina": "shopee.com.ar",
    "chile": "shopee.cl",
}

class ShopeeIngestor:
    def __init__(self, query=None, pais="paraguay"):
        self.query = query or ""
        self.pais = pais.lower()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "es-419,es;q=0.9",
            "Referer": "https://shopee.com.br/",
            "x-requested-with": "XMLHttpRequest",
        }

    def fetch(self, **kwargs):
        limit = kwargs.get("limit", kwargs.get("max_results", 5))
        if not self.query: return []
        items, now = [], datetime.now()
        domain = _SHOPEE_SITES.get(self.pais, "shopee.com.br")
        url = f"https://{domain}/api/v4/search/search_items?by=relevancy&keyword={requests.utils.quote(self.query)}&limit={limit+5}&newest=0&order=desc&page_type=search&version=2"
        data, _ = _cached_get(url, self.headers, timeout=8)
        if not data: return items
        try:
            res = json.loads(data)
            results = res.get("data", {}).get("items", [])
            if not isinstance(results, list): return items
        except: return items
        for entry in results[:limit + 3]:
            if len(items) >= limit: break
            if not isinstance(entry, dict): continue
            item_base = entry.get("item_basic", entry)
            title = item_base.get("name", "").strip()
            if not title or len(title) < 5: continue
            items.append({
                "id": f"sp_{item_base.get('itemid', hash(title))}",
                "title": title[:200],
                "content": f"Precio: {item_base.get('price_min', 0)} - Vendidos: {item_base.get('historical_sold', 0)}".strip()[:250],
                "url": f"https://{domain}/product/{item_base.get('shopid','')}/{item_base.get('itemid','')}",
                "author": f"Shopee {domain}",
                "created_utc": now.timestamp(), "created_at": now.isoformat(),
                "raw_json": None, "item_type": "product_listing",
                "source_name": f"Shopee ({domain})", "source_type": "shopee",
            })
        return items[:limit]
