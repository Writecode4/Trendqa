import requests
import time
import hashlib
import json
from pathlib import Path
from datetime import datetime

# Configuración de caché en disco
CACHE_DIR = Path("/tmp/reviews_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_TTL = 3600  # 1 hora

def _cached_get(url, headers, timeout=10):
    """GET con caché en disco."""
    cache_key = hashlib.md5(f"reviews:{url}".encode()).hexdigest()
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


class ReviewsIngestor:
    def __init__(self, query=None, **kwargs):
        self.query = query or ""
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "es-419,es;q=0.9",
        }

    def fetch(self, **kwargs):  # ✅ Firma flexible
        """Obtiene reviews con caché y límites estrictos."""
        limit = kwargs.get("limit", kwargs.get("max_results", 5))
        
        # Reviews internas de ejemplo (reemplaza con tu lógica real si apunta a DB/archivo)
        base_reviews = [
            {"text": "El envío tardó más de lo esperado, pero el producto llegó bien.", "rating": 3},
            {"text": "Excelente atención post-venta, resolvieron mi duda en minutos.", "rating": 5},
            {"text": "La página no me dejaba aplicar el cupón de descuento.", "rating": 2},
            {"text": "Buen precio, pero la pasarela de pago falló dos veces.", "rating": 3},
            {"text": "Muy claro el proceso de rastreo, llegó antes de la fecha estimada.", "rating": 5},
        ]

        now = datetime.now()
        items = []
        
        for i, rev in enumerate(base_reviews):
            if len(items) >= limit:
                break
            # Filtrar por query si aplica
            if self.query and self.query.lower() not in rev["text"].lower():
                continue
                
            items.append({
                "id": f"review_int_{i}",
                "title": f"Review #{i+1}",
                "content": rev["text"],
                "url": None,
                "author": "Usuario Anónimo",
                "created_utc": now.timestamp(),
                "created_at": now.isoformat(),
                "raw_json": None,
                "item_type": "user_review",
                "source_name": "Reviews Internas",
                "source_type": "review",
            })

        # Fallback: si tu versión original hacía scraping externo, descomenta y ajusta:
        # if len(items) < limit:
        #     url = f"https://tusitio.com/api/reviews?q={requests.utils.quote(self.query)}"
        #     data, _ = _cached_get(url, self.headers, timeout=8)
        #     if data:
        #         # parsear y extender items...

        return items[:limit]
