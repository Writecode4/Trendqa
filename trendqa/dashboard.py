import os
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from flask import Blueprint, render_template, request, send_file
from trendqa.db import Database

BASE = Path(__file__).resolve().parent.parent
load_dotenv(BASE / ".env")
from trendqa.ingest.reddit import RedditIngestor
from trendqa.ingest.rss import RSSIngestor
from trendqa.ingest.trends import GoogleTrendsIngestor
from trendqa.ingest.faq import FAQIngestor
from trendqa.ingest.reviews import ReviewsIngestor
from trendqa.ingest.x import XIngestor
from trendqa.ingest.mercadolibre import MercadoLibreIngestor
from trendqa.ingest.google_news import GoogleNewsIngestor
from trendqa.processing.analyzer import QuestionAnalyzer, TrendAnalyzer, BrandExtractor, AnswerAnalyzer
#from trendqa.services.pdf_export import PDFExporter

dashboard_bp = Blueprint("dashboard", __name__)

SEARCH_TERMS = {
    "experiencia_compra": ["compra", "pedido", "devolución", "garantía", "rastreo", "reclamo", "cancelar", "cambio", "soporte", "seguimiento"],
    "pagos_financiacion": ["pago", "tarjeta", "cuota", "financiación", "bancard", "billetera", "wallet", "paypal", "transferencia", "débito", "crédito", "cripto"],
    "confianza_seguridad": ["estafa", "confiable", "seguro", "reseña falsa", "engaño", "fraude", "verificar", "opiniones", "reputación"],
    "plataformas_canales": ["marketplace", "tienda online", "instagram", "facebook", "shopify", "mercadolibre", "vender", "ecommerce"],
    "logistica_envios": ["envío", "courier", "delivery", "paquete", "entrega", "aduana", "importación", "tracking", "logística"],
    "marketing_descubrimiento": ["oferta", "descuento", "promo", "precio barato", "comparación", "cupón", "liquidación", "rebaja", "económico"],
    "marcas_proveedores": ["marca", "proveedor", "empresa", "fabricante", "distribuidor", "tienda", "producto original", "mayorista"],
}


def expand_terms(q):
    base = SEARCH_TERMS.get(q, [q])
    expanded = [base[0], f"{base[0]} paraguay"]
    return list(set(expanded))


def collect_items(q):
    items = []
    terms = expand_terms(q)

    for t in terms:
        items.extend(RedditIngestor(query=t).fetch(limit=5))
        items.extend(XIngestor(query=t).fetch(max_results=3))
        items.extend(RSSIngestor(query=t).fetch())
        items.extend(MercadoLibreIngestor(query=t).fetch())
        items.extend(GoogleNewsIngestor(query=t).fetch())

    items.extend(FAQIngestor(query=q).fetch())
    items.extend(ReviewsIngestor(query=q).fetch())

    trends = GoogleTrendsIngestor().get_trend_bundle(terms[0])
    now = datetime.now().isoformat()
    items.append({
        "id": f"trends_{q}",
        "title": f"Tendencias: {q}",
        "content": (
            f"Términos relacionados: {', '.join(trends.get('related_top', [])[:5])}. "
            f"Términos en ascenso: {', '.join(trends.get('related_rising', [])[:5])}. "
            f"Autocompletado: {', '.join(trends.get('autocomplete', [])[:5])}."
        ),
        "url": None,
        "author": None,
        "created_utc": None,
        "created_at": now,
        "raw_json": None,
        "item_type": "trends_bundle",
        "source_name": "Google Trends",
        "source_type": "trends",
    })

    return items


def save_to_db(db, items, questions, topic=""):
    id_map = {}
    for item in items:
        sid = db.ensure_source(
            item.get("source_name", "unknown"),
            item.get("source_type", "unknown"),
        )
        item["source_id"] = sid
        orig_id = item.get("id")
        actual_id = db.save_item(item)
        id_map[orig_id] = actual_id

    for q in questions:
        db.save_question(
            item_id=id_map.get(q["item_id"], q["item_id"]),
            question=q["question"],
            category=q["category"],
            confidence=q["confidence"],
            model_used=q["model_used"],
            topic=topic,
        )


def _calc_category_trend(db, current_cats, total_current, topic=""):
    """Compara distribución actual de categorías vs histórico en DB."""
    try:
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT category, COUNT(*) FROM questions WHERE topic = ? GROUP BY category", (topic,))
        all_time = dict(cursor.fetchall())
        conn.close()
    except Exception:
        return None
    if not all_time or total_current == 0:
        return None
    all_total = sum(all_time.values())
    if all_total <= total_current:
        return None
    changes = []
    for cat, cur_count in current_cats.most_common(4):
        cur_pct = cur_count / total_current * 100
        all_pct = all_time.get(cat, 0) / all_total * 100
        diff = cur_pct - all_pct
        if diff > 8:
            changes.append(f"'{cat}' subió {diff:.0f}% vs el histórico")
        elif diff < -8:
            changes.append(f"'{cat}' bajó {abs(diff):.0f}% vs el histórico")
    if changes:
        return ". ".join(changes[:2]) + "."
    return None


def _find_cross_source(questions):
    """Detecta preguntas similares que aparecen en múltiples fuentes."""
    by_text = defaultdict(set)
    for q in questions:
        key = q["question"].strip().lower()[:80]
        by_text[key].add(q["source_type"])
    result = []
    for text, sources in by_text.items():
        if len(sources) > 1:
            orig = next(x for x in questions if x["question"].strip().lower()[:80] == text)
            result.append({
                "question": orig["question"],
                "sources": list(sources),
                "count": len(sources),
            })
    return sorted(result, key=lambda x: x["count"], reverse=True)[:5]


def _generate_insight(cat_counter, total, top_cat):
    """Genera un insight basado en la distribución de categorías."""
    if total == 0:
        return None
    pct = int(cat_counter[top_cat] / total * 100)
    others = [(c, int(n / total * 100)) for c, n in cat_counter.most_common()]
    least = others[-1] if len(others) > 1 else None
    lines = []
    if pct > 50:
        lines.append(f"La categoría '{top_cat}' concentra el {pct}% de las consultas")
    if least and least[1] < 10:
        lines.append(f"solo el {least[1]}% corresponde a '{least[0]}'")
    if len(others) >= 3 and pct < 40:
        mid = others[1]
        lines.append(f"'{mid[0]}' representa el {mid[1]}%, distribución más equilibrada")
    if lines:
        return " — ".join(lines) + "."
    return None


SOURCE_RELIABILITY = {
    "reddit": "Alta",
    "rss": "Media",
    "trends": "Media",
    "faq": "Referencial",
    "review": "Referencial",
    "x": "Alta",
    "mercadolibre": "Alta",
    "google_news": "Media",
}

SOURCE_LABELS = {
    "reddit": "Reddit r/Paraguay",
    "rss": "RSS (medios)",
    "trends": "Google Trends",
    "faq": "FAQ Interna",
    "review": "Reviews Internas",
    "x": "X (Twitter)",
    "mercadolibre": "MercadoLibre PY",
    "google_news": "Google News",
}


def _build_executive_summary(total, top_cat, pct, kw_text, src_counter, cat_counter, trend_text, cross_finding, cross_items):
    if total == 0:
        return {
            "que_cambio": "Primera corrida de análisis. No hay datos previos para comparar.",
            "por_que_importa": "Sin datos suficientes no se puede medir impacto en el negocio.",
            "que_haria_hoy": "Ejecutar scraping y análisis para establecer línea base.",
        }

    if trend_text and "subió" in trend_text:
        que_cambio = f"La conversación sobre {top_cat} está en aumento. {trend_text}"
    elif trend_text and "bajó" in trend_text:
        que_cambio = f"La conversación sobre {top_cat} está disminuyendo. {trend_text}"
    elif cross_finding and cross_items:
        que_cambio = (
            f"El {pct}% de las preguntas se concentra en {top_cat}, "
            f"y un tema se repite en {cross_items[0]['count']} fuentes distintas."
        )
    else:
        que_cambio = (
            f"El {pct}% de las señales detectadas corresponde a {top_cat}, "
            f"con '{kw_text}' como término principal en {len(src_counter)} fuentes."
        )

    if cross_finding and cross_items:
        plural = "canales" if cross_items[0]['count'] > 2 else "canal"
        por_que_importa = (
            f"Un mismo problema aparece en {cross_items[0]['count']} fuentes distintas. "
            f"No es ruido aislado — es una señal consistente de que los usuarios "
            f"no encuentran respuesta y buscan en más de un {plural}."
        )
    elif pct > 50:
        por_que_importa = (
            f"La categoría {top_cat} domina con el {pct}% de las consultas. "
            f"Resolver las dudas allí tiene el mayor impacto en la experiencia del usuario."
        )
    else:
        por_que_importa = (
            f"Las señales están distribuidas en {len(src_counter)} fuentes "
            f"y {len(cat_counter)} categorías. La oportunidad está en cruzar estos datos "
            f"para detectar patrones que una sola fuente no revelaría."
        )

    if cross_finding and cross_items:
        que_haria_hoy = (
            "Crear contenido específico que responda la pregunta recurrente "
            "y monitorear si la frecuencia baja en los próximos 30 días."
        )
    elif top_cat == "logistica_envios":
        que_haria_hoy = (
            "Revisar la propuesta de valor en envíos y la comunicación "
            "de tiempos de entrega. Una campaña enfocada en transparencia "
            "logística puede captar a quienes están comparando opciones."
        )
    elif top_cat == "pagos_financiacion":
        que_haria_hoy = (
            "Evaluar si los métodos de pago actuales cubren la demanda. "
            "Si las preguntas son sobre alternativas, hay oportunidad "
            "de agregar opciones y comunicarlo activamente."
        )
    elif top_cat == "marketing_descubrimiento":
        que_haria_hoy = (
            "Analizar la estructura de precios vs competidores. "
            "Si hay comparación recurrente, el problema no es el precio "
            "— es la percepción de valor."
        )
    else:
        que_haria_hoy = (
            f"Priorizar la categoría {top_cat} y asignar recursos "
            f"para resolver las dudas más repetidas con mayor confianza."
        )

    return {
        "que_cambio": que_cambio,
        "por_que_importa": por_que_importa,
        "que_haria_hoy": que_haria_hoy,
    }


RECOMMENDED_ACTIONS = {
    "experiencia_compra": {
        "default": ("Revisar proceso post-venta y fortalecer comunicación de seguimiento.", "servicio"),
        "reddit": ("Responder con datos concretos y crear contenido sobre proceso de compra.", "contenido"),
        "faq": ("Actualizar FAQ con pasos detallados de compra y devolución.", "contenido"),
        "review": ("Contactar al cliente, resolver su caso y mejorar proceso.", "servicio"),
    },
    "pagos_financiacion": {
        "default": ("Evaluar ampliar métodos de pago y comunicar opciones disponibles.", "anuncios"),
        "reddit": ("Publicar thread aclaratorio sobre opciones de pago y seguridad.", "contenido"),
        "faq": ("Actualizar FAQ con métodos de pago y financiación.", "contenido"),
        "review": ("Responder y evaluar si hay fricción en checkout.", "servicio"),
    },
    "confianza_seguridad": {
        "default": ("Reforzar comunicación de confianza y crear contenido sobre seguridad.", "contenido"),
        "reddit": ("Participar con datos objetivos y desmentir mitos.", "contenido"),
        "faq": ("Crear sección de confianza con garantías y certificaciones.", "contenido"),
        "review": ("Responder públicamente y escalar si es queja grave.", "servicio"),
    },
    "plataformas_canales": {
        "default": ("Analizar presencia en canales y crear contenido comparativo.", "contenido"),
        "reddit": ("Participar con análisis de plataformas y recomendar según caso.", "contenido"),
        "faq": ("Crear guía de canales y plataformas disponibles.", "contenido"),
        "review": ("Agradecer y preguntar por su experiencia en cada canal.", "servicio"),
    },
    "logistica_envios": {
        "default": ("Crear propuesta de entrega transparente con tiempos y seguimiento.", "contenido"),
        "reddit": ("Responder en Reddit con datos concretos sobre tiempos y cobertura.", "contenido"),
        "faq": ("Actualizar FAQ con tiempos reales y puntos de entrega.", "contenido"),
        "review": ("Contactar al cliente y mejorar comunicación logística.", "servicio"),
    },
    "marketing_descubrimiento": {
        "default": ("Analizar estructura de precios y crear contenido de ofertas.", "pricing"),
        "reddit": ("Participar con datos de valor y evaluar lanzar promoción.", "oferta"),
        "faq": ("Actualizar precios visibles y promociones activas.", "anuncios"),
        "review": ("Agregar testimonio y considerar ajustar pricing.", "pricing"),
    },
    "marcas_proveedores": {
        "default": ("Monitorear menciones de marca y crear contenido de tracking.", "contenido"),
        "reddit": ("Responder con información de marcas y tendencias.", "contenido"),
        "faq": ("Incluir directorio de marcas y proveedores.", "contenido"),
        "review": ("Derivar a compras si aplica.", "contenido"),
    },
    "otros": {
        "default": ("Revisar y clasificar manualmente.", "contenido"),
        "reddit": ("Monitorear antes de accionar.", "contenido"),
        "faq": ("Archivar como referencia interna.", "contenido"),
        "review": ("Archivar como referencia interna.", "contenido"),
    },
}


ACCION_TIPO_LABEL = {
    "contenido": "Atacar contenido",
    "oferta": "Lanzar oferta",
    "pricing": "Ajustar pricing",
    "servicio": "Mejorar servicio",
    "anuncios": "Activar anuncios",
    "mvp": "Entrar con MVP",
}


def _recommended_action(category, source_type, confidence):
    cat_actions = RECOMMENDED_ACTIONS.get(category, RECOMMENDED_ACTIONS["otros"])
    texto, tipo = cat_actions.get(source_type) or cat_actions["default"]
    badge = ACCION_TIPO_LABEL.get(tipo, tipo)
    if confidence > 0.85 and source_type == "reddit":
        texto += " (urgencia alta)"
    return {"texto": texto, "tipo": tipo, "badge": badge}


CHURN_CATEGORIAS_ALTAS = {"experiencia_compra", "confianza_seguridad"}
CHURN_KEYWORDS = [
    "devolver", "cancelar", "queja", "mal servicio", "estafa", "robo",
    "no funciona", "pésimo", "horrible", "nunca", "mentira", "no recomiendo",
    "alternativa", "otra empresa", "cambiar", "me voy", "competencia",
]


def _find_rising_questions(db, topic=""):
    """Detecta preguntas en crecimiento comparando frecuencia reciente vs histórica."""
    recent, older = db.get_question_trends(topic=topic, recent_days=30)
    if not recent:
        return []
    older_total = sum(older.values()) or 1
    recent_total = sum(recent.values()) or 1
    rising = []
    for question, recent_freq in sorted(recent.items(), key=lambda x: x[1], reverse=True)[:10]:
        older_freq = older.get(question, 0)
        recent_pct = recent_freq / recent_total * 100
        older_pct = older_freq / older_total * 100
        cambio = recent_pct - older_pct
        if cambio > 5:
            rising.append({
                "question": question,
                "frecuencia_reciente": recent_freq,
                "crecimiento": f"+{cambio:.0f}%",
            })
    return rising[:5]


def _calc_churn_risk(question, source_type, category, cross_sources_count):
    riesgo = 0
    if category in CHURN_CATEGORIAS_ALTAS:
        riesgo += 2
    if source_type == "review":
        riesgo += 2
    elif source_type == "reddit":
        riesgo += 1
    if cross_sources_count > 1:
        riesgo += 2
    texto_lower = question.lower()
    for kw in CHURN_KEYWORDS:
        if kw in texto_lower:
            riesgo += 2
            break
    riesgo = min(riesgo, 5)
    if riesgo >= 4:
        nivel = "alto"
    elif riesgo >= 2:
        nivel = "medio"
    else:
        nivel = "bajo"
    return {"riesgo": riesgo, "nivel": nivel}


OPORTUNIDAD_PONDERACION = {
    "volumen": 0.35,
    "dolor": 0.30,
    "solucionabilidad": 0.20,
    "tendencia": 0.15,
}

SOLUCIONABILIDAD = {
    "logistica_envios": 3, "pagos_financiacion": 3, "experiencia_compra": 3,
    "confianza_seguridad": 2, "plataformas_canales": 2,
    "marketing_descubrimiento": 2, "marcas_proveedores": 1, "otros": 0,
}

CAT_BUSINESS_IMPACT = {
    "experiencia_compra": "Aumenta retención si se reduce fricción post-venta",
    "pagos_financiacion": "Reduce abandono de carrito si se amplían métodos de pago",
    "confianza_seguridad": "Aumenta conversión si se fortalece confianza del consumidor",
    "plataformas_canales": "Guía decisión de dónde vender y en qué canales invertir",
    "logistica_envios": "Aumenta conversión si se reduce incertidumbre logística",
    "marketing_descubrimiento": "Protege margen si se comunica valor y ofertas",
    "marcas_proveedores": "Revela tendencias de marca y oportunidades de distribución",
    "otros": "Requiere clasificación manual para determinar impacto",
}

ETIQUETA_RANKING = {
    0: "Baja prioridad — señal decorativa, sin impacto económico claro",
    1: "Prioridad media — oportunidad condicional, validar antes de actuar",
    2: "Alta prioridad — señal con impacto directo en ingresos o costos",
    3: "Crítica — demanda alta + dolor alto + poca solución visible",
}


def _rank_opportunities(questions, cat_counter, total, cross_items, trend_text):
    if total == 0:
        return []

    cross_cats = set()
    if cross_items:
        for ci in cross_items:
            for q in questions:
                if q["question"].strip().lower()[:80] == ci["question"].strip().lower()[:80]:
                    cross_cats.add(q["category"])

    ranking = []
    for cat, count in cat_counter.most_common():
        pct = count / total * 100
        volumen = pct / 100.0

        dolor = 0
        if cat in cross_cats:
            dolor += 2
        reddit_count = sum(1 for q in questions if q["category"] == cat and q["source_type"] == "reddit")
        if reddit_count > 0:
            dolor += 1
        dolor = min(dolor, 3)

        sol = SOLUCIONABILIDAD.get(cat, 0)

        if trend_text and cat in trend_text:
            if "subió" in trend_text:
                tendencia = 1
            elif "bajó" in trend_text:
                tendencia = -1
            else:
                tendencia = 0
        else:
            tendencia = 0

        score = (
            volumen * OPORTUNIDAD_PONDERACION["volumen"]
            + (dolor / 3) * OPORTUNIDAD_PONDERACION["dolor"]
            + (sol / 3) * OPORTUNIDAD_PONDERACION["solucionabilidad"]
            + (tendencia + 1) / 2 * OPORTUNIDAD_PONDERACION["tendencia"]
        )

        if score >= 0.7:
            nivel = 3
        elif score >= 0.5:
            nivel = 2
        elif score >= 0.3:
            nivel = 1
        else:
            nivel = 0

        ranking.append({
            "categoria": cat,
            "señales": count,
            "porcentaje": f"{pct:.0f}%",
            "volumen_pct": pct,
            "dolor": dolor,
            "solucionabilidad": sol,
            "tendencia_etq": "al alza" if tendencia > 0 else "a la baja" if tendencia < 0 else "estable",
            "score": round(score, 2),
            "nivel": nivel,
            "etiqueta": ETIQUETA_RANKING[nivel],
            "impacto_negocio": CAT_BUSINESS_IMPACT.get(cat, ""),
        })

    ranking.sort(key=lambda x: x["score"], reverse=True)
    return ranking


def build_summary(q, items, questions, db, top_keywords):
    total = len(questions)
    cat_counter = Counter(q["category"] for q in questions)
    src_counter = Counter(q["source_type"] for q in questions)
    top_cat = cat_counter.most_common(1)[0][0] if cat_counter else "Sin datos"
    top_src = src_counter.most_common(1)[0][0] if src_counter else "Sin datos"
    kw_text = top_keywords[0]["keyword"] if top_keywords else ""

    pct = int(cat_counter[top_cat] / total * 100) if total else 0

    # Tendencia temporal
    trend_text = _calc_category_trend(db, cat_counter, total, topic=q)
    if trend_text is None:
        trend_text = (
            "Primera corrida de análisis. Estos datos establecen la línea base "
            "para futuras comparaciones."
            if total else "Sin datos históricos."
        )

    # Cruce de fuentes
    cross_items = _find_cross_source(questions)
    cross_finding = None
    if cross_items:
        top_cross = cross_items[0]
        cross_finding = (
            f"La pregunta '{top_cross['question'][:80]}' aparece "
            f"en {top_cross['count']} fuentes distintas: "
            f"{', '.join(top_cross['sources'])}."
        )

    # Preguntas en tendencia
    rising_questions = _find_rising_questions(db, topic=q)

    # Insight
    insight_text = _generate_insight(cat_counter, total, top_cat)

    # Resumen ejecutivo (reemplaza las 4 tarjetas individuales)
    exec_summary = _build_executive_summary(
        total, top_cat, pct, kw_text,
        src_counter, cat_counter,
        trend_text, cross_finding, cross_items
    )

    # Mapa de cruce de fuentes por texto de pregunta
    cross_map = defaultdict(int)
    for q_item_x in questions:
        key = q_item_x["question"].strip().lower()[:80]
        cross_map[key] = len({q2["source_type"] for q2 in questions if q2["question"].strip().lower()[:80] == key})

    # Mapa de contenido por item_id para análisis de respuestas
    item_content_map = {item.get("id"): item.get("content", "") for item in items}
    ans_analyzer = AnswerAnalyzer()

    # Agrupar preguntas por categoría con acción, riesgo de fuga y análisis de respuestas
    grouped = {}
    churn_questions = []
    for q_item in sorted(questions, key=lambda x: x["confidence"], reverse=True):
        q_item["action"] = _recommended_action(
            q_item["category"], q_item["source_type"], q_item["confidence"]
        )
        cross_count = cross_map.get(q_item["question"].strip().lower()[:80], 1)
        q_item["churn"] = _calc_churn_risk(
            q_item["question"], q_item["source_type"], q_item["category"], cross_count
        )
        # Análisis de respuestas
        content = item_content_map.get(q_item["item_id"], "")
        q_item["respuestas"] = ans_analyzer.analyze(q_item["question"], content)
        if q_item["churn"]["riesgo"] >= 3:
            churn_questions.append(q_item)
        cat = q_item["category"]
        if cat not in grouped:
            grouped[cat] = []
        if len(grouped[cat]) < 5:
            grouped[cat].append(q_item)

    # Oportunidad priorizada — ranking por rentabilidad probable
    oportunidades = _rank_opportunities(
        questions, cat_counter, total, cross_items, trend_text
    )

    # Anexo de fuentes — señales organizadas por fuente
    anexo_fuentes = []
    for src, count in src_counter.most_common():
        src_items = [qi for qi in questions if qi["source_type"] == src]
        anexo_fuentes.append({
            "clave": src,
            "nombre": SOURCE_LABELS.get(src, src),
            "señales": count,
            "confiabilidad": SOURCE_RELIABILITY.get(src, "Media"),
            "preguntas": sorted(src_items, key=lambda x: x["confidence"], reverse=True)[:10],
        })

    return {
        "period": "últimos 90 días",
        "topic": q,
        "total_questions": total,
        "top_source": top_src,
        "top_category": top_cat,
        "categories": dict(cat_counter),
        "sources": dict(src_counter),
        "top_keywords": top_keywords,
        "top_items": sorted(questions, key=lambda x: x["confidence"], reverse=True)[:15],
        "top_questions": sorted(questions, key=lambda x: x["confidence"], reverse=True)[:15],
        "grouped_questions": grouped,
        "churn_questions": sorted(churn_questions, key=lambda x: x["churn"]["riesgo"], reverse=True)[:10],
        "anexo_fuentes": anexo_fuentes,
        "oportunidades": oportunidades,
        "rising_questions": rising_questions,
        # Resumen ejecutivo
        "exec": exec_summary,
        # Claves legacy para compatibilidad con report_pdf.html
        "main_finding": exec_summary["que_cambio"],
        "trend": trend_text,
        "cross_finding": cross_finding,
        "cross_items": cross_items,
        "insight": insight_text,
        "opportunity": (
            f"Oportunidad para resolver dudas recurrentes en '{top_cat}', "
            f"especialmente las que se repiten en múltiples fuentes."
            if total else "Sin datos."
        ),
        "risks": (
            f"Persisten fricciones en '{top_cat}' que pueden frenar conversión."
            if total else "Sin datos de riesgo."
        ),
        "recommendation": (
            f"Priorizar '{top_cat}' y validar las señales con mayor confianza en terreno."
            if total else "Ejecutar scraping para obtener datos."
        ),
    }


def run_pipeline(q):
    db = Database()

    items = collect_items(q)

    questions = QuestionAnalyzer(max_items=20).analyze_items(items)

    kw = TrendAnalyzer().analyze_items(items)["top_keywords"]

    save_to_db(db, items, questions, topic=q)
    summary = build_summary(q, items, questions, db, kw)

    brands = BrandExtractor().extract(items)
    summary["top_brands"] = brands

    return summary


@dashboard_bp.route("/")
def index():
    return render_template("landing.html")


@dashboard_bp.route("/dashboard")
def dashboard():
    q = request.args.get("q", "logistica_envios")
    pais = request.args.get("pais", "paraguay")
    if pais != "paraguay":
        return render_template("dashboard.html", summary={"proximamente": True, "pais": pais})
    import traceback, sys
    try:
        summary = run_pipeline(q)
    except Exception:
        tb = traceback.format_exc()
        print(f"ERROR en dashboard: {tb}", flush=True)
        return f"Error: {tb}", 500
    return render_template("dashboard.html", summary=summary)






