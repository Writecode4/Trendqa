import json
import os
import random
import re
import time
from collections import Counter
from groq import Groq, RateLimitError

from .normalize import TextNormalizer


def _safe_parse_json(raw_text):
    """Extrae JSON de forma segura, limpiando markdown y manejando respuestas vacías."""
    if not raw_text or not isinstance(raw_text, str):
        return None
    try:
        text = raw_text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("\n", 1)[0]
        text = text.strip()
        if not text:
            return None
        return json.loads(text)
    except (json.JSONDecodeError, IndexError, ValueError):
        return None


class TrendAnalyzer:
    def __init__(self):
        self.normalizer = TextNormalizer()
        self.stopwords = {
            "de", "la", "el", "y", "que", "en", "a", "los", "las", "un", "una",
            "por", "con", "del", "se", "para", "es", "al", "lo", "como", "más",
            "pero", "sus", "le", "ya", "o", "este", "sí", "porque", "cuando"
        }

    def tokenize(self, text):
        text = self.normalizer.clean_text(text)
        return [
            w for w in text.split()
            if len(w) > 2 and w not in self.stopwords
        ]

    def extract_keywords(self, items, top_n=20):
        words = []
        for item in items:
            text = f"{item.get('title', '')} {item.get('content', '')}"
            words.extend(self.tokenize(text))
        return Counter(words).most_common(top_n)

    def analyze_items(self, items):
        normalized = [self.normalizer.normalize_item(dict(i)) for i in items]
        keywords = self.extract_keywords(normalized, top_n=20)
        sources = Counter(i.get("source_type", "unknown") for i in normalized)
        return {
            "total_items": len(normalized),
            "sources": dict(sources),
            "top_keywords": [{"keyword": k, "count": v} for k, v in keywords],
            "items": normalized
        }


CATEGORY_KEYWORDS = {
    "experiencia_compra": ["compra", "pedido", "devolución", "devolver", "garantía", "garantia", "rastreo", "reclamo", "cancelar", "cambio", "soporte", "falla", "defecto", "roto", "dañado", "reembolso"],
    "pagos_financiacion": ["pago", "bancard", "tarjeta", "cuota", "financiación", "financiacion", "billetera", "wallet", "paypal", "transferencia", "débito", "crédito", "cripto", "qr", "factura"],
    "confianza_seguridad": ["estafa", "confiable", "seguro", "inseguro", "reseña falsa", "engaño", "fraude", "verificar", "opiniones", "reputación", "robo", "pésimo", "horrible", "no recomiendo"],
    "plataformas_canales": ["marketplace", "tienda online", "instagram", "facebook", "shopify", "mercadolibre", "vender", "ecommerce", "canal", "plataforma"],
    "logistica_envios": ["courier", "envío", "envios", "delivery", "aduana", "paquete", "seguimiento", "tracking", "entrega", "llegada", "demora", "transporte", "logística", "logistica", "importación", "via miami"],
    "marketing_descubrimiento": ["oferta", "descuento", "promo", "barato", "económico", "comparar", "comparación", "cupón", "cupon", "liquidación", "rebaja", "valor"],
    "marcas_proveedores": ["marca", "proveedor", "empresa", "fabricante", "distribuidor", "tienda", "producto original", "mayorista", "proveeduria"],
}


def _categorize_by_keywords(text):
    text_lower = text.lower()
    scores = {}
    for cat, words in CATEGORY_KEYWORDS.items():
        score = sum(2 if w in text_lower else 0 for w in words)
        if score > 0:
            scores[cat] = score
    if scores:
        return max(scores, key=scores.get)
    return "otros"


class QuestionAnalyzer:
    CATEGORIES = (
        "logistica_envios", "pagos_financiacion", "experiencia_compra",
        "confianza_seguridad", "plataformas_canales", "marketing_descubrimiento",
        "marcas_proveedores", "otros"
    )

    def __init__(self, max_items=5, pais=None):
        if not pais or pais.lower() not in {"paraguay", "argentina", "mexico"}:
            raise ValueError(f"QuestionAnalyzer requiere 'pais' válido. Recibido: '{pais}'")
        
        self.max_items = max_items
        self.pais = pais.title()  # Argentina, Mexico, Paraguay
        api_key = os.getenv("GROQ_API_KEY")
        self.client = None
        self.model = None
        if api_key:
            try:
                self.client = Groq(api_key=api_key)
                self.model = "llama-3.3-70b-versatile"
            except Exception:
                pass

    def _parse_retry_after(self, error_msg):
        msg = str(error_msg)
        match = re.search(r"try again in (\d+)m([0-9.]+)?s", msg)
        if match:
            return int(match.group(1)) * 60 + float(match.group(2) or 0)
        match = re.search(r"try again in ([0-9.]+)s", msg)
        if match:
            return float(match.group(1))
        return 60

    def analyze_post(self, title, content, retries=2):
        if not self.client:
            return self._fallback(title, content)

        CAT_DESC = {
            "experiencia_compra": "pedidos, compras, devoluciones, garantía, rastreo, reclamos, cambios, soporte post-venta",
            "pagos_financiacion": "métodos de pago, tarjetas, cuotas, financiación, billeteras digitales, seguridad en pagos",
            "confianza_seguridad": "confiabilidad de tiendas, estafas, reseñas falsas, verificación, reputación online",
            "plataformas_canales": "marketplaces, tienda propia, Instagram, Facebook, Shopify, MercadoLibre, dónde vender",
            "logistica_envios": "costos, tiempos, cobertura, seguimiento de envíos, couriers, puntos de entrega, aduana",
            "marketing_descubrimiento": "ofertas, descuentos, promociones, comparación de precios, cupones, liquidación",
            "marcas_proveedores": "marcas mencionadas, proveedores, fabricantes, distribuidores, tiendas específicas",
            "otros": "temas no cubiertos en las categorías anteriores",
        }
        cat_list = "\n".join(f'  - "{k}": {v}' for k, v in CAT_DESC.items())

        prompt = f"""Analizá el siguiente post sobre e-commerce en {self.pais} y extraé las preguntas o dudas que el usuario está planteando.

Título: {title[:200]}
Contenido: {content[:500]}

Respondé SOLO con un JSON array. Cada elemento debe tener:
- "pregunta": la pregunta textual
- "categoria": una de las siguientes (elegí la que mejor describa el tema de la pregunta):
{cat_list}
- "confianza": número entre 0 y 1

Ejemplo:
[{{"pregunta": "Alguien sabe si hace envíos al interior?", "categoria": "logistica_envios", "confianza": 0.9}}]

Si no hay preguntas claras, devolvé [].
"""
        for attempt in range(retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                )
                
                raw = response.choices[0].message.content if response.choices else None
                if not raw:
                    return self._fallback(title, content)

                data = _safe_parse_json(raw)
                if data is None:
                    return self._fallback(title, content)

                if isinstance(data, dict):
                    return data.get("preguntas", data.get("questions", []))
                return data if isinstance(data, list) else []

            except RateLimitError as e:
                msg = str(e)
                if "tokens per day" in msg or "over capacity" in msg or "503" in msg:
                    return self._fallback(title, content)
                wait = self._parse_retry_after(msg)
                wait = min(wait, 15)
                if attempt < retries - 1:
                    time.sleep(wait)
            except Exception:
                if attempt < retries - 1:
                    time.sleep(3)
        return self._fallback(title, content)

    def _fallback(self, title, content):
        text = f"{title} {content}"
        cat = _categorize_by_keywords(text)
        return [{
            "pregunta": title[:200] if title else text[:200],
            "categoria": cat,
            "confianza": 0.6 if cat != "otros" else 0.3,
        }]

    def analyze_items(self, items):
        random.shuffle(items)
        items = items[:self.max_items]
        results = []
        for i, item in enumerate(items):
            print(f"Analizando {i + 1}/{len(items)}: {item.get('title', '')[:60]}...")
            questions = self.analyze_post(
                item.get("title", ""),
                item.get("content", "")
            )
            for q in questions:
                results.append({
                    "item_id": item.get("id"),
                    "question": q.get("pregunta", q.get("question", "")),
                    "category": q.get("categoria", q.get("category", "otros")),
                    "confidence": q.get("confianza", q.get("confidence", 0.5)),
                    "model_used": self.model or "keyword_fallback",
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "source_type": item.get("source_type", "unknown"),
                    "source_name": item.get("source_name", ""),
                })
            time.sleep(0.5)
        return results


BRAND_KEYWORDS = [
    "mercado libre", "mercadolibre", "shopify", "amazon", "ebay", "aliexpress",
    "shein", "wish", "temu", "amway", "herbalife", "natura", "avon",
    "bancard", "visa", "mastercard", "paypal", "cripto", "binance",
    "personal", "tigo", "claro", "vox", "wom",
    "sodimac", "easy", "stock", "biggie", "superseis",
    "pedidosya", "bigbox", "courier", "dhl", "fedex", "ups",
    "paraguay", "argentina", "mexico", "instagram", "facebook", "whatsapp", "google",
]

def _extract_brands_keyword(text):
    text_lower = text.lower()
    found = []
    for kw in BRAND_KEYWORDS:
        if kw in text_lower:
            found.append(kw.title())
    seen = []
    for f in found:
        if f not in seen:
            seen.append(f)
    return seen[:3]


class BrandExtractor:
    def __init__(self, pais=None):
        self.pais = pais.title() if pais else "Latam"
        api_key = os.getenv("GROQ_API_KEY")
        self.client = None
        self.model = None
        if api_key:
            try:
                self.client = Groq(api_key=api_key)
                self.model = "llama-3.3-70b-versatile"
            except Exception:
                pass

    def extract(self, items, retries=1):
        if not items:
            return []

        text = " ".join(
            f"{i.get('title', '')} {i.get('content', '')}" for i in items[:15]
        )[:3000]

        if self.client:
            prompt = f"""De los siguientes textos sobre e-commerce en {self.pais}, extraé las 2 marcas o empresas más mencionadas. Respondé SOLO con un JSON array de strings, ej: ["Courier A", "Bancard"]. Si no hay marcas claras, devolvé [].

Textos: {text}
"""
            for attempt in range(retries):
                try:
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.1,
                    )
                    raw = response.choices[0].message.content if response.choices else None
                    if not raw:
                        break
                    brands = _safe_parse_json(raw)
                    if isinstance(brands, list) and brands:
                        return [str(b) for b in brands[:2]]
                except RateLimitError as e:
                    msg = str(e)
                    if "tokens per day" in msg or "over capacity" in msg or "503" in msg:
                        break
                except Exception:
                    break

        brands = _extract_brands_keyword(text)
        if brands:
            return brands
        return ["Marca no identificada", "Verificar tendencia"]


POSITIVE_WORDS = ["bueno", "excelente", "rápido", "recomiendo", "confiable", "fácil", "seguro", "barato", "eficiente", "calidad"]
NEGATIVE_WORDS = ["malo", "pésimo", "horrible", "estafa", "robo", "lento", "caro", "no recomiendo", "pérdida", "dañado", "queja"]


def _analyze_sentiment(text):
    text_lower = text.lower()
    pos = sum(1 for w in POSITIVE_WORDS if w in text_lower)
    neg = sum(1 for w in NEGATIVE_WORDS if w in text_lower)
    if pos > neg: return "positivo"
    if neg > pos: return "negativo"
    return "neutral"


class AnswerAnalyzer:
    def __init__(self, pais=None):
        self.pais = pais.title() if pais else "Latam"
        api_key = os.getenv("GROQ_API_KEY")
        self.client = None
        self.model = None
        if api_key:
            try:
                self.client = Groq(api_key=api_key)
                self.model = "llama-3.3-70b-versatile"
            except Exception:
                pass

    def _extract_comments(self, content):
        if "TOP COMMENTS:" in content:
            parts = content.split("TOP COMMENTS:")
            comments = parts[-1].split(" | ")
            return [c.strip() for c in comments if len(c.strip()) > 10]
        return []

    def analyze(self, item_title, item_content):
        comments = self._extract_comments(item_content)
        if not comments:
            return {"hay_respuestas": False, "sentimiento": "sin_datos", "resumen": None}

        text = " | ".join(comments)[:1000]

        if self.client:
            prompt = f"""Analizá estos comentarios/respuestas sobre e-commerce en {self.pais}.

Comentarios: {text}

Respondé SOLO con un JSON:
{{"sentimiento": "positivo|negativo|mixto", "resuelve_duda": "si|no|parcial", "resumen": "una frase del sentimiento general"}}
"""
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                )
                raw = response.choices[0].message.content if response.choices else None
                if raw:
                    data = _safe_parse_json(raw)
                    if isinstance(data, dict):
                        return {
                            "hay_respuestas": True,
                            "sentimiento": data.get("sentimiento", "neutral"),
                            "resuelve_duda": data.get("resuelve_duda", "no"),
                            "resumen": data.get("resumen", ""),
                            "cantidad_comentarios": len(comments),
                        }
            except Exception:
                pass

        sent = _analyze_sentiment(text)
        return {
            "hay_respuestas": True,
            "sentimiento": sent,
            "resuelve_duda": "parcial",
            "resumen": f"{len(comments)} comentarios, tono {sent}",
            "cantidad_comentarios": len(comments),
        }
