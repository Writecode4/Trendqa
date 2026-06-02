"""
Standalone pipeline para GitHub Actions.
Recolecta items LATAM-wide por categoría, analiza en batch con AI,
guarda en MySQL con país detectado, y registra resumen.
"""
import os
import sys
import json
import time
import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("run_pipeline")

from trendqa.db import Database
from trendqa.processing.analyzer import BatchQuestionAnalyzer, TrendAnalyzer, BrandExtractor

SEARCH_TERMS = {
    "experiencia_compra": ["compra", "pedido", "devolución", "garantía", "rastreo", "reclamo", "cancelar", "cambio", "soporte", "seguimiento", "reembolso", "atención al cliente", "postventa"],
    "pagos_financiacion": ["pago", "tarjeta", "cuota", "financiación", "bancard", "billetera", "wallet", "paypal", "transferencia", "débito", "crédito", "cripto", "binance"],
    "confianza_seguridad": ["estafa", "confiable", "seguro", "reseña falsa", "engaño", "fraude", "verificar", "opiniones", "reputación", "confianza", "seguridad"],
    "plataformas_canales": ["marketplace", "tienda online", "instagram", "facebook", "shopify", "mercadolibre", "vender", "ecommerce", "courier", "envío", "paquetería"],
    "logistica_envios": ["envío", "courier", "delivery", "paquete", "entrega", "aduana", "importación", "tracking", "logística", "retraso", "demora", "despacho", "seguimiento"],
    "marketing_descubrimiento": ["oferta", "descuento", "promo", "precio barato", "comparación", "cupón", "liquidación", "rebaja", "económico", "promoción", "publicidad", "visibilidad"],
    "marcas_proveedores": ["marca", "proveedor", "empresa", "fabricante", "distribuidor", "tienda", "producto original", "mayorista", "minorista", "local", "internacional", "nacional", "reconocida", "desconocida"],
}

from trendqa.ingest.reddit import RedditIngestor
from trendqa.ingest.rss import RSSIngestor
from trendqa.ingest.faq import FAQIngestor
from trendqa.ingest.reviews import ReviewsIngestor
from trendqa.ingest.google_news import GoogleNewsIngestor
from trendqa.ingest.youtube import YouTubeIngestor
from trendqa.ingest.youtube_comments import YouTubeCommentsIngestor
from trendqa.ingest.shopee import ShopeeIngestor
from trendqa.ingest.tiktok import TikTokIngestor
from trendqa.ingest.x import XIngestor
from trendqa.ingest.mercadolibre import MercadoLibreIngestor
from trendqa.ingest.trends import GoogleTrendsIngestor

from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from collections import Counter


def expand_terms(q):
    base = SEARCH_TERMS.get(q, [q])
    return list(set(base))


def _fetch_safe(name, ingestor_cls, query, timeout=10, **kwargs):
    try:
        ingestor = ingestor_cls(query=query, **{k: v for k, v in kwargs.items() if k != "timeout"})
        def _run():
            try:
                return ingestor.fetch(**{k: v for k, v in kwargs.items() if k != "timeout"})
            except TypeError:
                return ingestor.fetch()
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run)
            return future.result(timeout=timeout)
    except TimeoutError:
        logger.warning(f"Timeout {name} ({timeout}s)")
        return []
    except Exception as e:
        logger.warning(f"{name} falló: {e}")
        return []


def collect_items_for_category(q):
    items = []
    terms = expand_terms(q)
    seen_ids = set()
    for t in terms[:3]:
        tasks = [
            ("Reddit", RedditIngestor, t, 10),
            ("X", XIngestor, t, 8),
            ("RSS", RSSIngestor, t, 10),
            ("MercadoLibre", MercadoLibreIngestor, t, 10),
            ("GoogleNews", GoogleNewsIngestor, t, 15),
            ("YouTube", YouTubeIngestor, t, 10),
            ("YouTubeComentarios", YouTubeCommentsIngestor, t, 12),
            ("Shopee", ShopeeIngestor, t, 10),
            ("TikTok", TikTokIngestor, t, 8),
        ]
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(_fetch_safe, name, cls, t, lim): name for name, cls, _, lim in tasks}
            for future in as_completed(futures, timeout=20):
                try:
                    res = future.result()
                    if res:
                        for item in res:
                            if item.get("id") not in seen_ids:
                                seen_ids.add(item.get("id"))
                                items.append(item)
                except Exception as e:
                    logger.warning(f"Error en hilo: {e}")
        for faq_res in _fetch_safe("FAQ", FAQIngestor, t, limit=10, timeout=10) or []:
            if faq_res.get("id") not in seen_ids:
                seen_ids.add(faq_res.get("id"))
                items.append(faq_res)
        for rev_res in _fetch_safe("Reviews", ReviewsIngestor, t, limit=10, timeout=10) or []:
            if rev_res.get("id") not in seen_ids:
                seen_ids.add(rev_res.get("id"))
                items.append(rev_res)
        if items:
            break

    try:
        from trendqa.dashboard import _filter_sports, _filter_crime
        items = _filter_sports(items)
        items = _filter_crime(items)
    except Exception:
        pass

    try:
        trends = GoogleTrendsIngestor().get_trend_bundle(q)
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        items.append({
            "id": f"trends_{q}",
            "title": f"Tendencias: {q}",
            "content": f"Relacionados: {', '.join(trends.get('related_top', [])[:5])}. En ascenso: {', '.join(trends.get('related_rising', [])[:5])}.",
            "url": None, "author": None, "created_utc": None, "created_at": now,
            "raw_json": None, "item_type": "trends_bundle",
            "source_name": "Google Trends", "source_type": "trends",
        })
    except Exception as e:
        logger.warning(f"Google Trends falló: {e}")

    return items


def save_batch(db, items, questions, topic):
    id_map = {}
    for item in items:
        sid = db.ensure_source(item.get("source_name", "unknown"), item.get("source_type", "unknown"))
        item["source_id"] = sid
        item["topic"] = topic
        item["pais"] = None
        orig_id = item.get("id")
        actual_id = db.save_item(item)
        id_map[orig_id] = actual_id

    saved = 0
    for q in questions:
        detected_pais = q.get("detected_pais") or "otros_latam"
        topic_key = f"{topic}_{detected_pais}"
        db.save_question(
            item_id=id_map.get(q["item_id"], q["item_id"]),
            question=q["question"],
            category=q["category"],
            confidence=q["confidence"],
            model_used=q["model_used"],
            topic=topic_key,
        )
        saved += 1
    return saved


def run():
    logger.info("=== Iniciando pipeline LATAM ===")
    db = Database()
    db.prune_old_data(days=90)
    analyzer = BatchQuestionAnalyzer()
    total_items = 0
    total_questions = 0
    categories_run = 0

    for category in SEARCH_TERMS:
        logger.info(f"[{category}] Recolectando items...")
        items = collect_items_for_category(category)
        if not items:
            logger.info(f"[{category}] 0 items, saltando")
            continue
        logger.info(f"[{category}] {len(items)} items recolectados, analizando...")
        questions = analyzer.analyze_batch(items, category)
        if not questions:
            logger.info(f"[{category}] Sin preguntas detectadas")
            continue
        saved = save_batch(db, items, questions, category)
        logger.info(f"[{category}] {saved} preguntas guardadas en BD")
        total_items += len(items)
        total_questions += saved
        categories_run += 1
        time.sleep(1)

    logger.info(f"=== Pipeline completo: {categories_run} categorias, {total_items} items, {total_questions} preguntas ===")


if __name__ == "__main__":
    run()
