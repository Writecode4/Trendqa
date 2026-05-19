import re
import requests
from datetime import datetime
from bs4 import BeautifulSoup


class FAQIngestor:
    def __init__(self, query=None):
        self.query_words = [w for w in (query.lower().split() if query else []) if len(w) > 2 and w != "paraguay"]
        self.query = query or ""
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0",
            "Accept-Language": "es-419,es;q=0.9",
        }
        self.items = [
            {"question": "¿Cuál es el mejor courier para Paraguay?", "answer": "Depende del costo, tiempo y soporte. Conviene comparar reseñas y tiempos de entrega."},
            {"question": "¿Cuánto tarda un envío internacional?", "answer": "Varía según origen, courier y aduana. Puede ir de pocos días a varias semanas."},
            {"question": "¿Qué es vía Miami?", "answer": "Es una modalidad logística para consolidar compras en EE. UU. antes de enviarlas a Paraguay."},
            {"question": "¿Cómo rastrear un pedido?", "answer": "Usando el código de seguimiento del courier en su sitio web. Algunos también notifican por WhatsApp."},
            {"question": "¿Hay impuestos de importación?", "answer": "Sí, la aduana paraguaya aplica aranceles según el tipo de producto y valor. Los courriers suelen gestionarlo."},
            {"question": "¿Cuál es la franquicia para compras internacionales?", "answer": "Actualmente hasta USD 500 sin tributos para particulares, vía courier. Cantidad limitada al año."},
            {"question": "¿Conviene comprar en Amazon o mejor en tiendas locales?", "answer": "Depende del tipo de producto, precio final con envío e impuestos, y urgencia de entrega."},
            {"question": "¿Bancard, cuál es la mejor tarjeta para compras online?", "answer": "Depende de promociones, cuotas sin interés y beneficios. Las Visa y Mastercard internacionales son las más aceptadas."},
            {"question": "¿Cómo evitar estafas en compras online?", "answer": "Verificar reputación del vendedor, usar medios de pago seguros, revisar políticas de devolución."},
            {"question": "¿Facebook Marketplace Paraguay es seguro?", "answer": "Depende del vendedor. Preferir entrega personal y verificar antes de pagar. Usar transferencia solo con referencias."},
        ]

    def _scrape_external_faq(self, url):
        """Fallback: buscar FAQs en sitios de referencia."""
        out = []
        try:
            r = requests.get(url, headers=self.headers, timeout=15)
            if r.status_code != 200:
                return out
            soup = BeautifulSoup(r.text, "html.parser")
            faq_blocks = (
                soup.select("div[class*='faq']")
                or soup.select("div[class*='accordion']")
                or soup.select("div[class*='question']")
                or soup.select("details")
                or soup.select("div[class*='answer']")
                or []
            )
            for block in faq_blocks[:10]:
                q_el = block.select_one("h3, h4, strong, div[class*='question'], summary")
                a_el = block.select_one("p, div[class*='answer'], div[class*='content']")
                if q_el and a_el:
                    q_text = q_el.get_text(strip=True)
                    a_text = a_el.get_text(strip=True)
                    if q_text and a_text and len(q_text) > 10 and len(a_text) > 10:
                        if self.query_words:
                            haystack = f"{q_text.lower()} {a_text.lower()}"
                            if not any(w in haystack for w in self.query_words):
                                continue
                        out.append({
                            "id": f"faq_scrape_{hash(q_text)}",
                            "title": q_text[:200],
                            "content": a_text,
                            "url": url,
                            "author": None,
                            "created_utc": datetime.now().timestamp(),
                            "created_at": datetime.now().isoformat(),
                            "raw_json": None,
                            "item_type": "faq_item",
                            "source_name": "FAQ Externa (scrape)",
                            "source_type": "faq",
                        })
        except Exception:
            pass
        return out

    def fetch(self):
        now = datetime.now()
        out = []

        # Estrategia 1: FAQ hardcoded
        for i, item in enumerate(self.items):
            if self.query_words and not any(w in item["question"].lower() or w in item["answer"].lower() for w in self.query_words):
                continue
            out.append({
                "id": f"faq_{i}",
                "title": item["question"],
                "content": item["answer"],
                "url": None,
                "author": None,
                "created_utc": now.timestamp(),
                "created_at": now.isoformat(),
                "raw_json": None,
                "item_type": "faq_item",
                "source_name": "FAQ Interna",
                "source_type": "faq",
            })

        # Estrategia 2: Scrape FAQs externas
        if not out:
            faq_sites = [
                "https://www.aduana.gov.py/faq",
                "https://www.bancard.com.py/faq",
                f"https://www.google.com/search?q=FAQ+{'courier' if not self.query else self.query}+paraguay",
            ]
            for url in faq_sites:
                scraped = self._scrape_external_faq(url)
                out.extend(scraped)
                if out:
                    break

        return out
