import requests
import time
import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime

# Configuración de caché en disco
CACHE_DIR = Path("/tmp/rss_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_TTL = 1800  # 30 minutos

def _cached_get(url, headers, timeout=10):
    """GET con caché en disco para feeds RSS."""
    cache_key = hashlib.md5(f"rss:{url}".encode()).hexdigest()
    cache_file = CACHE_DIR / f"{cache_key}.xml"
    
    if cache_file.exists():
        if time.time() - cache_file.stat().st_mtime < CACHE_TTL:
            return cache_file.read_text(errors="ignore"), True
            
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.status_code == 200:
            cache_file.write_text(r.text, encoding="utf-8")
            return r.text, False
    except Exception:
        pass
    return None, False


class RSSIngestor:
    def __init__(self, query=None, pais="paraguay", **kwargs):
        self.query = query or ""
        self.pais = pais.lower()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/rss+xml, application/xml, text/xml, */*"
        }

    def _is_ecommerce_relevant(self, title, content):
        """Filtra artículos que NO son sobre e-commerce/compras online."""
        text = f"{title} {content}".lower()
        
        # ✅ Señales que CONFIRMAN contexto e-commerce
        ecommerce_signals = [
            "tienda online", "e-commerce", "marketplace", "compra online", 
            "envío", "courier", "delivery", "pedido", "carrito", "checkout",
            "mercadolibre", "shopify", "paypal", "tarjeta", "pago online",
            "seguimiento", "tracking", "aduana", "importación", "devolución"
        ]
        
        # ✅ Señales que DESCARTAN contexto (política, deportes, notas rojas, etc.)
        exclude_signals = [
            "gobierno del estado", "mesa de diálogo", "comisión de seguimiento",
            "política sectorial", "gobernanza", "transparencia pública",
            "torneo", "partido", "sec 2026", "baseball", "fútbol",
            "muerte de", "homicidio", "bloqueos", "protesta", "manifestación",
            "salud y defensoría", "hueycantenango", "chilapa"
        ]
        
        if any(exc in text for exc in exclude_signals):
            return False
        return any(sig in text for sig in ecommerce_signals)

    def fetch(self, **kwargs):
        """Obtiene artículos RSS con caché, timeout, país y filtro de relevancia."""
        limit = kwargs.get("limit", kwargs.get("max_results", 10))
        if not self.query:
            return []

        items = []
        now = datetime.now()
        
        # Feeds ajustados por país
        gl, ceid = {"paraguay": ("PY", "PY:es-419"), "argentina": ("AR", "AR:es-419"), "mexico": ("MX", "MX:es-419"), "colombia": ("CO", "CO:es-419"), "brasil": ("BR", "BR:pt-419")}.get(self.pais, ("PY", "PY:es-419"))        
        feeds = [
            f"https://news.google.com/rss/search?q={requests.utils.quote(self.query)}&hl=es-419&gl={gl}&ceid={ceid}",
            f"https://www.reddit.com/search.rss?q={requests.utils.quote(self.query)}&restrict_sr=off&sort=new&t=month",
        ]

        for url in feeds:
            if len(items) >= limit:
                break
                
            xml_content, _ = _cached_get(url, self.headers, timeout=8)
            if not xml_content:
                continue

            try:
                root = ET.fromstring(xml_content)
                channel = root.find("channel")
                if channel is None:
                    continue
                    
                for entry in channel.findall("item"):
                    if len(items) >= limit:
                        break
                        
                    title_el = entry.find("title")
                    link_el = entry.find("link")
                    desc_el = entry.find("description")
                    pub_el = entry.find("pubDate")
                    
                    title = title_el.text.strip() if title_el is not None and title_el.text else ""
                    if not title or len(title) < 8:
                        continue
                    
                    # ✅ AQUÍ ESTÁ EL FILTRO EXACTO
                    if not self._is_ecommerce_relevant(title, desc_el.text or ""):
                        continue
                        
                    items.append({
                        "id": f"rss_{hashlib.md5(title.encode()).hexdigest()[:10]}",
                        "title": title[:250],
                        "content": (desc_el.text or "")[:400],
                        "url": link_el.text or "",
                        "author": "RSS Feed",
                        "created_utc": None,
                        "created_at": pub_el.text if pub_el is not None else now.isoformat(),
                        "raw_json": None,
                        "item_type": "rss_article",
                        "source_name": "RSS (Medios/Foros)",
                        "source_type": "rss",
                    })
            except ET.ParseError:
                continue

        return items[:limit]
