import re, os, json, hashlib, time
from datetime import datetime
from pathlib import Path
import requests
from bs4 import BeautifulSoup

# Configuración de caché
CACHE_DIR = Path("/tmp/faq_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_TTL = 3600  # 1 hora
MAX_RESPONSE_SIZE = 100_000  # 100KB límite

def _cached_get(url, headers, timeout=10):
    """GET con caché en disco."""
    cache_key = hashlib.md5(f"faq:{url}".encode()).hexdigest()
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
            content = r.text[:MAX_RESPONSE_SIZE]
            cache_file.write_text(json.dumps({"ts": time.time(), "content": content}))
            return content, False
    except:
        pass
    return None, False


_FAQ_BY_COUNTRY = {
    "paraguay": [
        {"q": "¿Cuál es el mejor courier para Paraguay?", "a": "Depende del costo, tiempo y soporte. Conviene comparar reseñas y tiempos de entrega."},
        {"q": "¿Cuánto tarda un envío internacional?", "a": "Varía según origen, courier y aduana. Puede ir de pocos días a varias semanas."},
        {"q": "¿Qué es vía Miami?", "a": "Es una modalidad logística para consolidar compras en EE. UU. antes de enviarlas a Paraguay."},
        {"q": "¿Cómo rastrear un pedido?", "a": "Usando el código de seguimiento del courier en su sitio web."},
        {"q": "¿Hay impuestos de importación?", "a": "Sí, la aduana paraguaya aplica aranceles según el tipo de producto y valor."},
        {"q": "¿Cuál es la franquicia para compras internacionales?", "a": "Actualmente hasta USD 500 sin tributos para particulares, vía courier."},
        {"q": "¿Cómo evitar estafas en compras online?", "a": "Verificar reputación del vendedor, usar medios de pago seguros, revisar políticas de devolución."},
    ],
    "brasil": [
        {"q": "Qual o melhor frete para o Brasil?", "a": "Depende do custo, prazo e confiabilidade. Comparar avaliações de Correios e transportadoras."},
        {"q": "Quanto tempo leva uma entrega internacional?", "a": "Varia conforme a origem, transportadora e alfândega. Pode levar de dias a semanas."},
        {"q": "Como rastrear um pedido?", "a": "Use o código de rastreamento da transportadora no site oficial."},
        {"q": "Quais os impostos de importação no Brasil?", "a": "A Receita Federal aplica tributos conforme o tipo de produto e valor declarado."},
        {"q": "Qual a franquia para compras internacionais?", "a": "Compras até USD 50 entre pessoas físicas são isentas de imposto de importação."},
        {"q": "Como evitar golpes em compras online?", "a": "Verificar reputação do vendedor, usar meios de pagamento seguros, revisar políticas de devolução."},
        {"q": "Como funciona o Mercado Libre no Brasil?", "a": "É o maior marketplace da América Latina, com proteção ao comprador e diversas opções de frete."},
    ],
}

_SCRAPE_URLS_BY_COUNTRY = {
    "paraguay": ["https://www.aduana.gov.py/faq", "https://www.bancard.com.py/ayuda"],
    "brasil": ["https://www.gov.br/receitafederal/pt-br/assuntos/aduana-e-comercio-exterior", "https://www.gov.br/procon/pt-br"],
}

_ACCEPT_LANG_BY_COUNTRY = {
    "paraguay": "es-419,es;q=0.9",
    "brasil": "pt-BR,pt;q=0.9",
}

class FAQIngestor:
    def __init__(self, query=None, **kwargs):
        self.query = query or ""
        self.pais = kwargs.get("pais", "paraguay").lower()
        # Filtrar palabras clave relevantes
        self.query_words = [
            w for w in (query.lower().split() if query else [])
            if len(w) > 3 and w not in {self.pais, "para", "que", "como", "cuanto", "cual", "para", "qual"}
        ]
        self.query_pattern = re.compile(
            r'|'.join(re.escape(w) for w in self.query_words), re.I
        ) if self.query_words else None
        
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": _ACCEPT_LANG_BY_COUNTRY.get(self.pais, "es-419,es;q=0.9"),
        }
        
        self._base_faqs = _FAQ_BY_COUNTRY.get(self.pais, _FAQ_BY_COUNTRY["paraguay"])

    def _matches_query(self, text):
        if not self.query_pattern:
            return True
        return bool(self.query_pattern.search(text))

    def fetch(self, **kwargs):  # ✅ Firma flexible: acepta cualquier kwarg
        """Obtiene FAQs con caché y límites estrictos."""
        # Extraer parámetros opcionales (sin romper si no existen)
        limit = kwargs.get("limit", kwargs.get("max_results", 5))
        
        now = datetime.now()
        now_ts = now.timestamp()
        now_iso = now.isoformat()
        items = []

        # 1. FAQs hardcoded (instantáneo)
        for i, item in enumerate(self._base_faqs):
            if len(items) >= limit:
                break
            if self._matches_query(f"{item['q']} {item['a']}"):
                items.append({
                    "id": f"faq_hard_{i}",
                    "title": item["q"],
                    "content": item["a"],
                    "url": None,
                    "author": None,
                    "created_utc": now_ts,
                    "created_at": now_iso,
                    "raw_json": None,
                    "item_type": "faq_item",
                    "source_name": "FAQ Interna",
                    "source_type": "faq",
                })

        # 2. Scraping externo SOLO si faltan resultados y hay query
        if len(items) < limit and self.query_words:
            faq_sites = _SCRAPE_URLS_BY_COUNTRY.get(self.pais, _SCRAPE_URLS_BY_COUNTRY["paraguay"])
            for url in faq_sites:
                if len(items) >= limit:
                    break
                html, _ = _cached_get(url, self.headers, timeout=8)
                if html:
                    soup = BeautifulSoup(html, "html.parser")
                    blocks = soup.select("details, [class*='faq'], [class*='question']")[:3]
                    for block in blocks:
                        if len(items) >= limit:
                            break
                        q_el = block.select_one("summary, h3, strong")
                        a_el = block.select_one("p, [class*='answer']")
                        if q_el and a_el:
                            q_text = q_el.get_text(strip=True)[:200]
                            a_text = a_el.get_text(strip=True)[:300]
                            if q_text and a_text and self._matches_query(f"{q_text} {a_text}"):
                                items.append({
                                    "id": f"faq_scrape_{hashlib.md5(q_text.encode()).hexdigest()[:10]}",
                                    "title": q_text,
                                    "content": a_text,
                                    "url": url,
                                    "author": None,
                                    "created_utc": now_ts,
                                    "created_at": now_iso,
                                    "raw_json": None,
                                    "item_type": "faq_item",
                                    "source_name": "FAQ Externa",
                                    "source_type": "faq",
                                })

        return items[:limit]  # ✅ Garantizar límite
