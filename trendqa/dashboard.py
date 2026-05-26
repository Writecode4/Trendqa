import os
import re
import time
import json
import logging
import hashlib
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from threading import Lock
from dotenv import load_dotenv
from flask import Blueprint, render_template, request, send_file, abort
import io

from trendqa.db import Database
from trendqa.processing.analyzer import QuestionAnalyzer, TrendAnalyzer, BrandExtractor, AnswerAnalyzer

# Ingestores
from trendqa.ingest.reddit import RedditIngestor
from trendqa.ingest.rss import RSSIngestor
from trendqa.ingest.trends import GoogleTrendsIngestor
from trendqa.ingest.faq import FAQIngestor
from trendqa.ingest.reviews import ReviewsIngestor
from trendqa.ingest.x import XIngestor
from trendqa.ingest.mercadolibre import MercadoLibreIngestor
from trendqa.ingest.google_news import GoogleNewsIngestor

BASE = Path(__file__).resolve().parent.parent
load_dotenv(BASE / ".env")

dashboard_bp = Blueprint("dashboard", __name__)
logger = logging.getLogger(__name__)

# ==========================================
# ✅ CONFIGURACIÓN & CONSTANTES
# ==========================================
VALID_COUNTRIES = {"paraguay", "argentina", "mexico"}

SEARCH_TERMS = {
    "experiencia_compra": ["compra", "pedido", "devolución", "garantía", "rastreo", "reclamo", "cancelar", "cambio", "soporte", "seguimiento"],
    "pagos_financiacion": ["pago", "tarjeta", "cuota", "financiación", "bancard", "billetera", "wallet", "paypal", "transferencia", "débito", "crédito", "cripto"],
    "confianza_seguridad": ["estafa", "confiable", "seguro", "reseña falsa", "engaño", "fraude", "verificar", "opiniones", "reputación"],
    "plataformas_canales": ["marketplace", "tienda online", "instagram", "facebook", "shopify", "mercadolibre", "vender", "ecommerce"],
    "logistica_envios": ["envío", "courier", "delivery", "paquete", "entrega", "aduana", "importación", "tracking", "logística"],
    "marketing_descubrimiento": ["oferta", "descuento", "promo", "precio barato", "comparación", "cupón", "liquidación", "rebaja", "económico"],
    "marcas_proveedores": ["marca", "proveedor", "empresa", "fabricante", "distribuidor", "tienda", "producto original", "mayorista"],
}

SOURCE_RELIABILITY = {
    "reddit": "Alta", "rss": "Media", "trends": "Media", "faq": "Referencial",
    "review": "Referencial", "x": "Alta", "mercadolibre": "Alta", "google_news": "Media",
}
SOURCE_LABELS = {
    "reddit": "Reddit r/Paraguay", "rss": "RSS (medios)", "trends": "Google Trends",
    "faq": "FAQ Interna", "review": "Reviews Internas", "x": "X (Twitter)",
    "mercadolibre": "MercadoLibre PY", "google_news": "Google News",
}

RECOMMENDED_ACTIONS = {
    "experiencia_compra": {"default": ("Revisar proceso post-venta y fortalecer comunicación de seguimiento.", "servicio"), "reddit": ("Responder con datos concretos y crear contenido sobre proceso de compra.", "contenido"), "faq": ("Actualizar FAQ con pasos detallados de compra y devolución.", "contenido"), "review": ("Contactar al cliente, resolver su caso y mejorar proceso.", "servicio")},
    "pagos_financiacion": {"default": ("Evaluar ampliar métodos de pago y comunicar opciones disponibles.", "anuncios"), "reddit": ("Publicar thread aclaratorio sobre opciones de pago y seguridad.", "contenido"), "faq": ("Actualizar FAQ con métodos de pago y financiación.", "contenido"), "review": ("Responder y evaluar si hay fricción en checkout.", "servicio")},
    "confianza_seguridad": {"default": ("Reforzar comunicación de confianza y crear contenido sobre seguridad.", "contenido"), "reddit": ("Participar con datos objetivos y desmentir mitos.", "contenido"), "faq": ("Crear sección de confianza con garantías y certificaciones.", "contenido"), "review": ("Responder públicamente y escalar si es queja grave.", "servicio")},
    "plataformas_canales": {"default": ("Analizar presencia en canales y crear contenido comparativo.", "contenido"), "reddit": ("Participar con análisis de plataformas y recomendar según caso.", "contenido"), "faq": ("Crear guía de canales y plataformas disponibles.", "contenido"), "review": ("Agradecer y preguntar por su experiencia en cada canal.", "servicio")},
    "logistica_envios": {"default": ("Crear propuesta de entrega transparente con tiempos y seguimiento.", "contenido"), "reddit": ("Responder en Reddit con datos concretos sobre tiempos y cobertura.", "contenido"), "faq": ("Actualizar FAQ con tiempos reales y puntos de entrega.", "contenido"), "review": ("Contactar al cliente y mejorar comunicación logística.", "servicio")},
    "marketing_descubrimiento": {"default": ("Analizar estructura de precios y crear contenido de ofertas.", "pricing"), "reddit": ("Participar con datos de valor y evaluar lanzar promoción.", "oferta"), "faq": ("Actualizar precios visibles y promociones activas.", "anuncios"), "review": ("Agregar testimonio y considerar ajustar pricing.", "pricing")},
    "marcas_proveedores": {"default": ("Monitorear menciones de marca y crear contenido de tracking.", "contenido"), "reddit": ("Responder con información de marcas y tendencias.", "contenido"), "faq": ("Incluir directorio de marcas y proveedores.", "contenido"), "review": ("Derivar a compras si aplica.", "contenido")},
    "otros": {"default": ("Revisar y clasificar manualmente.", "contenido"), "reddit": ("Monitorear antes de accionar.", "contenido"), "faq": ("Archivar como referencia interna.", "contenido"), "review": ("Archivar como referencia interna.", "contenido")},
}
ACCION_TIPO_LABEL = {"contenido": "Atacar contenido", "oferta": "Lanzar oferta", "pricing": "Ajustar pricing", "servicio": "Mejorar servicio", "anuncios": "Activar anuncios", "mvp": "Entrar con MVP"}

CHURN_CATEGORIAS_ALTAS = {"experiencia_compra", "confianza_seguridad"}
CHURN_KEYWORDS = ["devolver", "cancelar", "queja", "mal servicio", "estafa", "robo", "no funciona", "pésimo", "horrible", "nunca", "mentira", "no recomiendo", "alternativa", "otra empresa", "cambiar", "me voy", "competencia"]

OPORTUNIDAD_PONDERACION = {"volumen": 0.35, "dolor": 0.30, "solucionabilidad": 0.20, "tendencia": 0.15}
SOLUCIONABILIDAD = {"logistica_envios": 3, "pagos_financiacion": 3, "experiencia_compra": 3, "confianza_seguridad": 2, "plataformas_canales": 2, "marketing_descubrimiento": 2, "marcas_proveedores": 1, "otros": 0}
CAT_BUSINESS_IMPACT = {"experiencia_compra": "Aumenta retención si se reduce fricción post-venta", "pagos_financiacion": "Reduce abandono de carrito si se amplían métodos de pago", "confianza_seguridad": "Aumenta conversión si se fortalece confianza del consumidor", "plataformas_canales": "Guía decisión de dónde vender y en qué canales invertir", "logistica_envios": "Aumenta conversión si se reduce incertidumbre logística", "marketing_descubrimiento": "Protege margen si se comunica valor y ofertas", "marcas_proveedores": "Revela tendencias de marca y oportunidades de distribución", "otros": "Requiere clasificación manual para determinar impacto"}
ETIQUETA_RANKING = {0: "Baja prioridad — señal decorativa, sin impacto económico claro", 1: "Prioridad media — oportunidad condicional, validar antes de actuar", 2: "Alta prioridad — señal con impacto directo en ingresos o costos", 3: "Crítica — demanda alta + dolor alto + poca solución visible"}

# ==========================================
# ✅ CACHE INTERNO THREAD-SAFE (0 dependencias externas)
# ==========================================
_CACHE_STORE = {}
_CACHE_LOCK = Lock()

def _cache_get(key):
    with _CACHE_LOCK:
        if key in _CACHE_STORE:
            val, exp = _CACHE_STORE[key]
            if time.time() < exp:
                return val
            del _CACHE_STORE[key]
    return None

def _cache_set(key, val, ttl=900):
    with _CACHE_LOCK:
        _CACHE_STORE[key] = (val, time.time() + ttl)

# ==========================================
# ✅ FUNCIONES AUXILIARES
# ==========================================
def expand_terms(q, pais=None):
    base = SEARCH_TERMS.get(q, [q])
    ecommerce_modifiers = {
        "paraguay": ["online", "e-commerce", "tienda virtual", "marketplace", "courier"],
        "argentina": ["online", "e-commerce", "tienda virtual", "mercadolibre", "envío"],
        "mexico": ["online", "e-commerce", "tienda en línea", "mercadolibre", "paquetería"],
    }
    if pais and pais.lower() in ecommerce_modifiers:
        modifiers = ecommerce_modifiers[pais.lower()]
        expanded = [term for term in base]
        for term in base:
            for mod in modifiers[:2]:
                expanded.append(f"{term} {mod}")
        return list(set(expanded))
    return list(set(base))

def _fetch_safe(name, ingestor_cls, query, timeout=10, **kwargs):
    try:
        ingestor = ingestor_cls(query=query, **{k:v for k,v in kwargs.items() if k != 'timeout'})
        def _run_fetch():
            try: return ingestor.fetch(**{k:v for k,v in kwargs.items() if k not in ('timeout', 'limit', 'max_results')})
            except TypeError: return ingestor.fetch()
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run_fetch)
            return future.result(timeout=timeout)
    except TimeoutError:
        logger.warning(f"⏱️ {name} timeout ({timeout}s)")
        return []
    except Exception as e:
        logger.warning(f"⚠️ {name} falló: {e}")
        return []

def collect_items_parallel(q, pais="paraguay", max_workers=4):
    items = []
    terms = expand_terms(q)
    t = terms[0] if terms else q
    tasks = [
        ("Reddit", RedditIngestor, t, 5), ("X", XIngestor, t, 3), ("RSS", RSSIngestor, t, 5),
        ("MercadoLibre", MercadoLibreIngestor, t, 5), ("GoogleNews", GoogleNewsIngestor, t, 10),
    ]
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch_safe, name, cls, q, lim, pais=pais): name for name, cls, q, lim in tasks}
        for future in as_completed(futures, timeout=20):
            try:
                res = future.result()
                if res: items.extend(res)
            except Exception as e: logger.warning(f"Error en hilo de fuentes: {e}")
    items.extend(_fetch_safe("FAQ", FAQIngestor, q, limit=3, timeout=5, pais=pais))
    items.extend(_fetch_safe("Reviews", ReviewsIngestor, q, limit=3, timeout=5, pais=pais))
    try:
        trends = GoogleTrendsIngestor().get_trend_bundle(t)
        now = datetime.now().isoformat()
        items.append({"id": f"trends_{q}", "title": f"Tendencias: {q}", "content": f"Términos relacionados: {', '.join(trends.get('related_top', [])[:5])}. Términos en ascenso: {', '.join(trends.get('related_rising', [])[:5])}. Autocompletado: {', '.join(trends.get('autocomplete', [])[:5])}.", "url": None, "author": None, "created_utc": None, "created_at": now, "raw_json": None, "item_type": "trends_bundle", "source_name": "Google Trends", "source_type": "trends"})
    except Exception as e: logger.warning(f"⚠️ Google Trends falló: {e}")
    return items

def save_to_db(db, items, questions, topic="", pais="paraguay"):
    id_map = {}
    for item in items:
        sid = db.ensure_source(item.get("source_name", "unknown"), item.get("source_type", "unknown"))
        item["source_id"] = sid; item["topic"] = topic; item["pais"] = pais
        orig_id = item.get("id"); actual_id = db.save_item(item); id_map[orig_id] = actual_id
    for q in questions:
        db.save_question(item_id=id_map.get(q["item_id"], q["item_id"]), question=q["question"], category=q["category"], confidence=q["confidence"], model_used=q["model_used"], topic=f"{topic}_{pais}")

def _calc_category_trend(db, current_cats, total_current, topic=""):
    try:
        conn = db.get_connection(); cursor = conn.cursor()
        cursor.execute("SELECT category, COUNT(*) FROM questions WHERE topic = ? GROUP BY category", (topic,))
        all_time = dict(cursor.fetchall()); conn.close()
    except Exception: return None
    if not all_time or total_current == 0: return None
    all_total = sum(all_time.values())
    if all_total <= total_current: return None
    changes = []
    for cat, cur_count in current_cats.most_common(4):
        diff = (cur_count / total_current * 100) - (all_time.get(cat, 0) / all_total * 100)
        if diff > 8: changes.append(f"'{cat}' subió {diff:.0f}% vs el histórico")
        elif diff < -8: changes.append(f"'{cat}' bajó {abs(diff):.0f}% vs el histórico")
    return ". ".join(changes[:2]) + "." if changes else None

def _find_cross_source(questions):
    by_text = defaultdict(set)
    for q in questions: by_text[q["question"].strip().lower()[:80]].add(q["source_type"])
    result = []
    for text, sources in by_text.items():
        if len(sources) > 1:
            orig = next(x for x in questions if x["question"].strip().lower()[:80] == text)
            result.append({"question": orig["question"], "sources": list(sources), "count": len(sources)})
    return sorted(result, key=lambda x: x["count"], reverse=True)[:5]

def _generate_insight(cat_counter, total, top_cat):
    if total == 0: return None
    pct = int(cat_counter[top_cat] / total * 100)
    others = [(c, int(n / total * 100)) for c, n in cat_counter.most_common()]
    least = others[-1] if len(others) > 1 else None
    lines = []
    if pct > 50: lines.append(f"La categoría '{top_cat}' concentra el {pct}% de las consultas")
    if least and least[1] < 10: lines.append(f"solo el {least[1]}% corresponde a '{least[0]}'")
    if len(others) >= 3 and pct < 40: lines.append(f"'{others[1][0]}' representa el {others[1][1]}%, distribución más equilibrada")
    return " — ".join(lines) + "." if lines else None

def _build_executive_summary(total, top_cat, pct, kw_text, src_counter, cat_counter, trend_text, cross_finding, cross_items):
    if total == 0: return {"que_cambio": "Primera corrida de análisis. No hay datos previos para comparar.", "por_que_importa": "Sin datos suficientes no se puede medir impacto en el negocio.", "que_haria_hoy": "Ejecutar scraping y análisis para establecer línea base."}
    que_cambio = f"La conversación sobre {top_cat} está en aumento. {trend_text}" if trend_text and "subió" in trend_text else f"La conversación sobre {top_cat} está disminuyendo. {trend_text}" if trend_text and "bajó" in trend_text else f"El {pct}% de las preguntas se concentra en {top_cat}, y un tema se repite en {cross_items[0]['count']} fuentes distintas." if cross_finding and cross_items else f"El {pct}% de las señales detectadas corresponde a {top_cat}, con '{kw_text}' como término principal en {len(src_counter)} fuentes."
    por_que_importa = f"Un mismo problema aparece en {cross_items[0]['count']} fuentes distintas. No es ruido aislado — es una señal consistente de que los usuarios no encuentran respuesta y buscan en más de un {'canales' if cross_items[0]['count'] > 2 else 'canal'}." if cross_finding and cross_items else f"La categoría {top_cat} domina con el {pct}% de las consultas. Resolver las dudas allí tiene el mayor impacto en la experiencia del usuario." if pct > 50 else f"Las señales están distribuidas en {len(src_counter)} fuentes y {len(cat_counter)} categorías. La oportunidad está en cruzar estos datos para detectar patrones que una sola fuente no revelaría."
    que_haria_hoy = "Crear contenido específico que responda la pregunta recurrente y monitorear si la frecuencia baja en los próximos 30 días." if cross_finding and cross_items else "Revisar la propuesta de valor en envíos y la comunicación de tiempos de entrega." if top_cat == "logistica_envios" else "Evaluar si los métodos de pago actuales cubren la demanda." if top_cat == "pagos_financiacion" else "Analizar la estructura de precios vs competidores." if top_cat == "marketing_descubrimiento" else f"Priorizar la categoría {top_cat} y asignar recursos para resolver las dudas más repetidas con mayor confianza."
    return {"que_cambio": que_cambio, "por_que_importa": por_que_importa, "que_haria_hoy": que_haria_hoy}

def _recommended_action(category, source_type, confidence):
    cat_actions = RECOMMENDED_ACTIONS.get(category, RECOMMENDED_ACTIONS["otros"])
    texto, tipo = cat_actions.get(source_type) or cat_actions["default"]
    badge = ACCION_TIPO_LABEL.get(tipo, tipo)
    if confidence > 0.85 and source_type == "reddit": texto += " (urgencia alta)"
    return {"texto": texto, "tipo": tipo, "badge": badge}

def _find_rising_questions(db, topic=""):
    recent, older = db.get_question_trends(topic=topic, recent_days=30)
    if not recent: return []
    older_total, recent_total = sum(older.values()) or 1, sum(recent.values()) or 1
    rising = []
    for question, recent_freq in sorted(recent.items(), key=lambda x: x[1], reverse=True)[:10]:
        older_freq = older.get(question, 0)
        cambio = (recent_freq / recent_total * 100) - (older_freq / older_total * 100)
        if cambio > 5: rising.append({"question": question, "frecuencia_reciente": recent_freq, "crecimiento": f"+{cambio:.0f}%"})
    return rising[:5]

def _calc_churn_risk(question, source_type, category, cross_sources_count):
    riesgo = 0
    if category in CHURN_CATEGORIAS_ALTAS: riesgo += 2
    if source_type == "review": riesgo += 2
    elif source_type == "reddit": riesgo += 1
    if cross_sources_count > 1: riesgo += 2
    texto_lower = question.lower()
    for kw in CHURN_KEYWORDS:
        if kw in texto_lower: riesgo += 2; break
    riesgo = min(riesgo, 5)
    nivel = "alto" if riesgo >= 4 else "medio" if riesgo >= 2 else "bajo"
    return {"riesgo": riesgo, "nivel": nivel}

def _rank_opportunities(questions, cat_counter, total, cross_items, trend_text):
    if total == 0: return []
    cross_cats = {q["category"] for ci in (cross_items or []) for q in questions if q["question"].strip().lower()[:80] == ci["question"].strip().lower()[:80]}
    ranking = []
    for cat, count in cat_counter.most_common():
        pct = count / total * 100; volumen = pct / 100.0
        dolor = (2 if cat in cross_cats else 0) + (1 if sum(1 for q in questions if q["category"] == cat and q["source_type"] == "reddit") > 0 else 0)
        dolor = min(dolor, 3); sol = SOLUCIONABILIDAD.get(cat, 0)
        tendencia = 1 if trend_text and cat in trend_text and "subió" in trend_text else -1 if trend_text and cat in trend_text and "bajó" in trend_text else 0
        score = (volumen * OPORTUNIDAD_PONDERACION["volumen"] + (dolor / 3) * OPORTUNIDAD_PONDERACION["dolor"] + (sol / 3) * OPORTUNIDAD_PONDERACION["solucionabilidad"] + (tendencia + 1) / 2 * OPORTUNIDAD_PONDERACION["tendencia"])
        nivel = 3 if score >= 0.7 else 2 if score >= 0.5 else 1 if score >= 0.3 else 0
        ranking.append({"categoria": cat, "señales": count, "porcentaje": f"{pct:.0f}%", "volumen_pct": pct, "dolor": dolor, "solucionabilidad": sol, "tendencia_etq": "al alza" if tendencia > 0 else "a la baja" if tendencia < 0 else "estable", "score": round(score, 2), "nivel": nivel, "etiqueta": ETIQUETA_RANKING[nivel], "impacto_negocio": CAT_BUSINESS_IMPACT.get(cat, "")})
    ranking.sort(key=lambda x: x["score"], reverse=True)
    return ranking

def build_summary(q, items, questions, db, top_keywords, pais="paraguay"):
    total = len(questions)
    cat_counter = Counter(q_item["category"] for q_item in questions)
    src_counter = Counter(q_item["source_type"] for q_item in questions)
    top_cat = cat_counter.most_common(1)[0][0] if cat_counter else "Sin datos"
    top_src = src_counter.most_common(1)[0][0] if src_counter else "Sin datos"
    kw_text = top_keywords[0]["keyword"] if top_keywords else ""
    pct = int(cat_counter[top_cat] / total * 100) if total else 0
    topic_key = f"{q}_{pais}"
    trend_text = _calc_category_trend(db, cat_counter, total, topic=topic_key) or ("Primera corrida de análisis." if total else "Sin datos históricos.")
    cross_items = _find_cross_source(questions)
    cross_finding = f"La pregunta '{cross_items[0]['question'][:80]}' aparece en {cross_items[0]['count']} fuentes distintas." if cross_items else None
    rising_questions = _find_rising_questions(db, topic=topic_key)
    insight_text = _generate_insight(cat_counter, total, top_cat)
    exec_summary = _build_executive_summary(total, top_cat, pct, kw_text, src_counter, cat_counter, trend_text, cross_finding, cross_items)
    cross_map = defaultdict(int)
    for q_item in questions: cross_map[q_item["question"].strip().lower()[:80]] = len({q2["source_type"] for q2 in questions if q2["question"].strip().lower()[:80] == q_item["question"].strip().lower()[:80]})
    item_content_map = {item.get("id"): item.get("content", "") for item in items}
    ans_analyzer = AnswerAnalyzer()
    grouped, churn_questions = {}, []
    for q_item in sorted(questions, key=lambda x: x["confidence"], reverse=True):
        q_item["action"] = {**_recommended_action(q_item["category"], q_item["source_type"], q_item["confidence"]), **(q_item.get("action", {}))}
        q_item["churn"] = _calc_churn_risk(q_item["question"], q_item["source_type"], q_item["category"], cross_map.get(q_item["question"].strip().lower()[:80], 1))
        q_item["respuestas"] = ans_analyzer.analyze(q_item["question"], item_content_map.get(q_item["item_id"], ""))
        if q_item["churn"]["riesgo"] >= 3: churn_questions.append(q_item)
        cat = q_item["category"]
        if cat not in grouped: grouped[cat] = []
        if len(grouped[cat]) < 5: grouped[cat].append(q_item)
    oportunidades = _rank_opportunities(questions, cat_counter, total, cross_items, trend_text)
    anexo_fuentes = []
    c = pais.lower()
    for src, count in src_counter.most_common():
        src_items = [qi for qi in questions if qi["source_type"] == src]
        nombre = f"Reddit r/{c.title()}" if src == "reddit" else f"MercadoLibre ({c.upper()})" if src == "mercadolibre" else f"Google Trends ({c.title()})" if src == "trends" else f"X/Twitter ({c.title()})" if src == "x" else src.title()
        anexo_fuentes.append({"clave": src, "nombre": nombre, "señales": count, "confiabilidad": SOURCE_RELIABILITY.get(src, "Media"), "preguntas": sorted(src_items, key=lambda x: x["confidence"], reverse=True)[:10]})
    return {
        "period": "últimos 90 días", "topic": q, "pais": pais, "total_questions": total, "top_source": top_src, "top_category": top_cat,
        "categories": dict(cat_counter), "sources": dict(src_counter), "top_keywords": top_keywords, "top_items": sorted(questions, key=lambda x: x["confidence"], reverse=True)[:15],
        "top_questions": sorted(questions, key=lambda x: x["confidence"], reverse=True)[:15], "grouped_questions": grouped,
        "churn_questions": sorted(churn_questions, key=lambda x: x["churn"]["riesgo"], reverse=True)[:10], "anexo_fuentes": anexo_fuentes,
        "oportunidades": oportunidades, "rising_questions": rising_questions, "exec": exec_summary, "main_finding": exec_summary["que_cambio"],
        "trend": trend_text, "cross_finding": cross_finding, "cross_items": cross_items, "insight": insight_text,
        "opportunity": f"Oportunidad para resolver dudas recurrentes en '{top_cat}'." if total else "Sin datos.",
        "risks": f"Persisten fricciones en '{top_cat}'." if total else "Sin datos de riesgo.",
        "recommendation": f"Priorizar '{top_cat}' y validar señales." if total else "Ejecutar scraping.",
    }

def _enrich_with_value_layer(db, topic, questions):
    try:
        recent, older = db.get_question_trends(topic, recent_days=30)
        r_total, o_total = sum(recent.values()) or 1, sum(older.values()) or 1
        trends_map = {}
        for q in questions:
            txt = q.get("question", "").strip(); r_f, o_f = recent.get(txt, 0), older.get(txt, 0)
            if o_f == 0 and r_f > 0: trends_map[txt] = "rising"
            elif r_f == 0: trends_map[txt] = "declining"
            else:
                diff = (r_f / r_total * 100) - (o_f / o_total * 100)
                trends_map[txt] = "rising" if diff > 5 else "declining" if diff < -5 else "stable"
    except Exception: trends_map = {}
    team_map = {"logistica_envios": "Producto", "pagos_financiacion": "Finanzas", "experiencia_compra": "CX", "confianza_seguridad": "CX", "plataformas_canales": "Marketing", "marketing_descubrimiento": "Marketing", "marcas_proveedores": "Producto"}
    impact_map = {"logistica_envios": "-15% a -25% abandono carrito", "pagos_financiacion": "+8% a +14% conversión checkout", "experiencia_compra": "-20% a -30% reclamos", "confianza_seguridad": "+12% a +18% confianza", "plataformas_canales": "ROI est.: USD 6k-18k/mes", "marketing_descubrimiento": "-10% a -15% CAC", "marcas_proveedores": "USD 8k-22k/mes demanda"}
    has_critical, complete, rising_cats = False, 0, set()
    for q in questions:
        txt = q.get("question", "").strip(); trend = trends_map.get(txt, "stable"); q["trend"] = trend
        if "action" not in q: q["action"] = {}
        q["action"]["team"] = team_map.get(q.get("category", ""), "Gerencia")
        base = impact_map.get(q.get("category", ""), "Impacto variable")
        mod = " (ventana abierta)" if trend == "rising" else " (monitoreo)" if trend == "declining" else ""
        q["action"]["impact"] = f"{base}{mod}"
        if trend == "rising": rising_cats.add(q.get("category", ""))
        if trend == "rising" and q.get("churn", {}).get("nivel") == "alto": has_critical = True
        if "team" in q["action"] and "impact" in q["action"]: complete += 1
    completeness = int((complete / len(questions)) * 100) if questions else 0
    insight = {"cause_summary": f"Señales en {', '.join(rising_cats)} muestran crecimiento vs histórico." if rising_cats else "Distribución estable."}
    return has_critical, completeness, insight

# ==========================================
# ✅ ALERTAS CONTEXTUALES
# ==========================================
def _generate_alerts(questions, topic_key, db):
    alerts = []
    if not questions: return alerts
    try:
        seen = set()
        for q in questions:
            q_key = q.get("question", "")[:60].strip().lower()
            if q_key in seen: continue
            if q.get("churn", {}).get("nivel") == "alto":
                alerts.append({"level":"Crítica","window":"<72h","deviation":q["churn"]["riesgo"],"question":q.get("question","")[:120],"category":q.get("category","otros"),"source":q.get("source_type","fuente"),"trend":_calc_trend_velocity(q.get("question",""),topic_key,db),"recommendation":_get_churn_action(q.get("category","otros"),q.get("source_type","")),"kpis_affected":_map_kpis(q.get("category","otros"),"churn"),"is_info":False})
                seen.add(q_key)
            elif q.get("trend") == "rising" and q.get("confidence", 0) > 0.75:
                alerts.append({"level":"Alta","window":"<72h","deviation":round(q.get("confidence",0)*2,1),"question":q.get("question","")[:120],"category":q.get("category","otros"),"source":q.get("source_type","fuente"),"trend":_calc_trend_velocity(q.get("question",""),topic_key,db),"recommendation":_get_trend_action(q.get("category","otros"),q.get("source_type","")),"kpis_affected":_map_kpis(q.get("category","otros"),"trend"),"is_info":False})
                seen.add(q_key)
    except Exception: pass
    if not alerts and len(questions) >= 5:
        alerts.append({"level":"Monitoreo activo","window":"<72h","deviation":0,"question":None,"category":None,"source":None,"trend":"estable","recommendation":"Sin señales críticas en las últimas 72h. Los datos se actualizan cada 15 min.","kpis_affected":["Estabilidad","Confianza"],"is_info":True})
    return alerts[:3]

def _calc_trend_velocity(question, topic_key, db):
    try:
        recent, older = db.get_question_trends(topic=topic_key, recent_days=3)
        rt, ot = sum(recent.values()) or 1, sum(older.values()) or 1
        fr, fo = recent.get(question,0), older.get(question,0)
        if ot==0 and fr>0: return "nuevo"
        diff = (fr/rt*100) - (fo/ot*100 if ot>0 else 0)
        return f"+{diff:.0f}% vs histórico" if diff>15 else f"{diff:.0f}% vs histórico" if diff<-15 else "estable"
    except: return "n/d"

def _get_churn_action(cat, src):
    a = {"logistica_envios":{"reddit":"Publicar thread con tiempos reales + código de seguimiento","review":"Contactar en <2h, ofrecer compensación y documentar caso","default":"Badge 'Entrega garantizada' en checkout + SMS confirmación"},"pagos_financiacion":{"reddit":"Hilo aclaratorio de métodos aceptados + screenshot","review":"Ofrecer alternativa inmediata y escalar a finanzas","default":"Íconos de pago en header + FAQ financiación"},"confianza_seguridad":{"reddit":"Responder con certificaciones y política de devolución","review":"Escalar a legal, reembolso preventivo y publicar caso","default":"Sección 'Por qué confiar' con testimonios"},"experiencia_compra":{"default":"Email post-compra con pasos de seguimiento + soporte directo"}}
    return a.get(cat,{}).get(src, a.get(cat,{}).get("default","Revisar manualmente y priorizar en <4h"))

def _get_trend_action(cat, src):
    a = {"logistica_envios":"Landing dedicada a 'Envíos' con calculadora tiempos/costos","pagos_financiacion":"Banner financiación sin intereses + comparar vs competencia","marketing_descubrimiento":"Ajustar meta-ads keywords comparación + badge 'Mejor precio'","plataformas_canales":"Comparativa visual canales (web vs app vs marketplace)","default":f"Contenido específico sobre '{cat}' en {src} + monitorear conversión 48h"}
    return a.get(cat, a["default"])

def _map_kpis(cat, tipo):
    m = {"logistica_envios":{"churn":["Churn","NPS","Retención 90d"],"trend":["Conversión checkout","Tiempo página","Abandono carrito"]},"pagos_financiacion":{"churn":["Abandono checkout","CAC","LTV"],"trend":["Conversión pago","Ticket promedio","Métodos usados"]},"confianza_seguridad":{"churn":["Tasa devolución","Reclamos","Sentimiento neto"],"trend":["CTR orgánico","Share of Voice","Conversión 1ra compra"]},"experiencia_compra":{"churn":["Churn 30d","Soporte tickets","NPS post-compra"],"trend":["Retención 90d","Compras repetidas","Referidos"]},"marketing_descubrimiento":{"churn":["ROAS","CPC","Conversión ads"],"trend":["Impresiones orgánicas","CTR comparación","Conversión oferta"]}}
    return m.get(cat,{}).get(tipo,["KPI genérico","Monitorear"])

# ==========================================
# ✅ PIPELINE PRINCIPAL
# ==========================================
def run_pipeline(q, pais):
    if not pais or pais.lower() not in VALID_COUNTRIES:
        raise ValueError(f"País '{pais}' no soportado.")
    db = Database()
    items = collect_items_parallel(q, pais=pais)
    questions = QuestionAnalyzer(max_items=20, pais=pais).analyze_items(items)
    kw = TrendAnalyzer().analyze_items(items)["top_keywords"]
    save_to_db(db, items, questions, topic=q, pais=pais)
    try:
        topic_key = f"{q}_{pais}"
        has_crit, comp_pct, val_insight = _enrich_with_value_layer(db, topic_key, questions)
    except Exception as e:
        logger.warning(f"⚠️ Capa de valor no inyectada: {e}")
        has_crit, comp_pct, val_insight = False, 0, {"cause_summary": "Enriquecimiento temporalmente no disponible."}
    summary = build_summary(q, items, questions, db, kw, pais=pais)
    summary["top_brands"] = BrandExtractor().extract(items)
    summary["has_critical_signal"] = has_crit; summary["value_completeness"] = comp_pct; summary["value_insight"] = val_insight
    summary["api_enabled"] = False; summary["api_calls_used"] = 0; summary["api_limit"] = 1000
    summary["alerts"] = _generate_alerts(questions, f"{q}_{pais}", db)
    return summary

# ==========================================
# ✅ RUTAS FLASK
# ==========================================
@dashboard_bp.route("/")
def index():
    return render_template("landing.html")

@dashboard_bp.route("/dashboard")
def dashboard():
    start = time.time()
    q = request.args.get("q", "logistica_envios")
    pais = request.args.get("pais", "paraguay").lower()
    if pais not in VALID_COUNTRIES:
        return render_template("dashboard.html", summary={"error": True, "message": f"País '{pais}' no soportado aún."})
    
    cache_key = f"dashboard:{q}:{pais}"
    cached_result = _cache_get(cache_key)
    if cached_result:
        logger.info(f"✅ CACHE HIT | {cache_key} | ⏱️ {(time.time()-start):.3f}s")
        return render_template("dashboard.html", summary=cached_result)
    
    try:
        summary = run_pipeline(q, pais=pais)
        _cache_set(cache_key, summary, ttl=900)
        logger.info(f"✅ PIPELINE + CACHE SET | {cache_key} | ⏱️ {time.time()-start:.2f}s")
        return render_template("dashboard.html", summary=summary)
    except Exception as e:
        logger.error(f"❌ Pipeline falló | {q} | {pais} | {e} | ⏱️ {time.time()-start:.2f}s", exc_info=True)
        fallback = {
            "error": True, "message": "Error temporal al procesar datos.",
            "period": "últimos 90 días", "topic": q, "total_questions": 0, "pais": pais,
            "grouped_questions": {}, "categories": {}, "sources": {},
            "top_keywords": [], "top_items": [], "top_questions": [],
            "churn_questions": [], "anexo_fuentes": [], "oportunidades": [],
            "rising_questions": [], "cross_items": [], "top_brands": [],
            "top_source": "Sin datos", "top_category": "Sin datos",
            "exec": {"que_cambio": "Servicio temporalmente no disponible.", "por_que_importa": "", "que_haria_hoy": ""},
            "has_critical_signal": False, "value_completeness": 0,
            "value_insight": {"cause_summary": ""},
            "api_enabled": False, "api_calls_used": 0, "api_limit": 1000,
            "alerts": []
        }
        return render_template("dashboard.html", summary=fallback), 200

@dashboard_bp.route("/dashboard/pdf")
def download_pdf():
    return redirect(f"https://sikuri.lat/contacto.html?topic={request.args.get('topic', '')}&pais={request.args.get('pais', '')}")

@dashboard_bp.route("/reports/download")
def serve_report():
    report_id = request.args.get("report_id")
    if not report_id or len(report_id.split("_")) < 3:
        abort(400, description="report_id inválido")
    topic, pais = report_id.split("_")[:2]
    pdf_content = f"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>endobj
4 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
5 0 obj<</Length 200>>stream
BT /F1 16 Tf 50 700 Td (TrendQA - Informe: {topic}) Tj 0 -20 Td (País: {pais}) Tj 0 -20 Td (Generado por SIKURI) Tj ET
endstream endobj
xref 0 6 0000000000 65535 f 0000000015 00000 n 0000000060 00000 n 0000000115 00000 n 0000000270 00000 n 0000000340 00000 n trailer<</Size 6/Root 1 0 R>> startxref 590 %%EOF""".encode('latin-1')
    return send_file(io.BytesIO(pdf_content), mimetype='application/pdf', as_attachment=True, download_name=f"TrendQA_{topic}_{pais}.pdf")

@dashboard_bp.route("/health")
def health():
    return {"status": "ok", "service": "trendqa", "timestamp": datetime.utcnow().isoformat()}, 200
