import re
import requests
from datetime import datetime
from bs4 import BeautifulSoup


class ReviewsIngestor:
    def __init__(self, query=None):
        self.query_words = [w for w in (query.lower().split() if query else []) if len(w) > 2 and w != "paraguay"]
        self.query = query or ""
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0",
            "Accept-Language": "es-419,es;q=0.9",
        }
        self.items = [
            {"title": "Opinión sobre courier A", "content": "Buen precio, pero soporte lento en temporadas altas."},
            {"title": "Opinión sobre courier B", "content": "Entrega rápida y seguimiento claro, aunque cuesta un poco más."},
            {"title": "Experiencia con courier C", "content": "Perdieron mi paquete una vez. La reposición tardó 2 meses."},
            {"title": "Recomendación de tienda online PY", "content": "Excelente atención al cliente, envío gratuito desde 200.000 Gs."},
            {"title": "Queja sobre marketplace", "content": "Producto llegó dañado, el vendedor no respondió. Tuve que reclamar por la tarjeta."},
            {"title": "Opinión sobre pagos online", "content": "Bancard funciona bien, pero las comisiones son altas para montos chicos."},
            {"title": "Reseña de Amazon vía courier", "content": "Comprar por Amazon sale más barato que en tiendas locales aunque tarda 15 días."},
            {"title": "Experiencia con compra internacional", "content": "Aduana me cobró más de lo esperado. El courier no avisó antes del despacho."},
            {"title": "Opinión sobre tienda Instagram PY", "content": "Buena atención por WhatsApp, envío rápido dentro de Asunción."},
            {"title": "Recomendación de celulares PY", "content": "Más barato comprar en tienda local con garantía que importar. Solo conviene si es un modelo exclusivo."},
        ]

    def _scrape_review_html(self, url):
        """Fallback: scrape reseñas de sitios de opinión."""
        out = []
        try:
            r = requests.get(url, headers=self.headers, timeout=15)
            if r.status_code != 200:
                return out
            soup = BeautifulSoup(r.text, "html.parser")
            review_blocks = (
                soup.select("div[class*='review']")
                or soup.select("div[class*='opinion']")
                or soup.select("div[class*='comment']")
                or soup.select("div[class*='testimonial']")
                or soup.select("div[class*='feedback']")
                or soup.find_all("div", class_=re.compile(r"review|opinion|comment|testimonial|feedback"))
                or []
            )
            seen = set()
            for block in review_blocks[:15]:
                text = block.get_text(strip=True)
                if not text or len(text) < 20 or text in seen:
                    continue
                seen.add(text)

                title = ""
                for sel in ("h3", "h4", "strong", "div[class*='title']", "span[class*='name']"):
                    el = block.select_one(sel)
                    if el:
                        title = el.get_text(strip=True)[:150]
                        if title:
                            break
                if not title:
                    title = text[:120]

                author = ""
                for sel in ("span[class*='author']", "span[class*='user']", "div[class*='author']"):
                    el = block.select_one(sel)
                    if el:
                        author = el.get_text(strip=True)
                        if author:
                            break

                if self.query_words and not any(w in text.lower() for w in self.query_words):
                    continue

                out.append({
                    "id": f"review_scrape_{hash(text)}",
                    "title": title[:200],
                    "content": text[:1000],
                    "url": url,
                    "author": author or None,
                    "created_utc": datetime.now().timestamp(),
                    "created_at": datetime.now().isoformat(),
                    "raw_json": None,
                    "item_type": "review_item",
                    "source_name": "Reviews scrapeadas",
                    "source_type": "review",
                })
        except Exception:
            pass
        return out

    def fetch(self):
        now = datetime.now()
        out = []

        # Estrategia 1: Reviews hardcodeadas
        for i, item in enumerate(self.items):
            if self.query_words and not any(w in item["title"].lower() or w in item["content"].lower() for w in self.query_words):
                continue
            out.append({
                "id": f"review_{i}",
                "title": item["title"],
                "content": item["content"],
                "url": None,
                "author": None,
                "created_utc": now.timestamp(),
                "created_at": now.isoformat(),
                "raw_json": None,
                "item_type": "review_item",
                "source_name": "Reviews Internas",
                "source_type": "review",
            })

        # Estrategia 2: Scrape reseñas externas
        if not out:
            review_urls = [
                f"https://www.google.com/search?q={'courier' if not self.query else self.query}+opiniones+paraguay",
                f"https://www.google.com/search?q={'courier' if not self.query else self.query}+reseña+paraguay",
            ]
            for url in review_urls:
                scraped = self._scrape_review_html(url)
                out.extend(scraped)
                if out:
                    break

        return out
