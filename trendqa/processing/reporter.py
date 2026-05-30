import json
import heapq
import logging
from collections import Counter
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# ✅ Mappings externalizados (fáciles de testear y actualizar)
OPPORTUNITY_MAP = {
    "E-commerce": "Hay oportunidad para contenido, servicio o producto enfocado en compras, pagos y logística.",
    "Fintech": "Hay oportunidad para soluciones de pago, tarjetas, billeteras y fricción financiera.",
    "Logística": "Hay oportunidad para mejorar entrega, seguimiento, couriers y experiencia postcompra.",
    "Trámites": "Hay oportunidad para simplificar procesos, importación y gestión operativa.",
    "Otros": "Hay oportunidad para atacar el dolor recurrente detectado en la conversación.",
}

RISKS_MAP = {
    "E-commerce": "Persisten dudas sobre confianza, devoluciones, costos y tiempos de entrega.",
    "Fintech": "La fricción se concentra en medios de pago, validación y compatibilidad bancaria.",
    "Logística": "Los principales riesgos están en demoras, aduanas y seguimiento del envío.",
    "Trámites": "El riesgo está en complejidad operativa, requisitos y procesos poco claros.",
    "Otros": "Existen fricciones repetidas que pueden frenar conversión o adopción."
}

DEFAULT_OPPORTUNITY = "Hay oportunidad para atacar el dolor recurrente detectado en la conversación."
DEFAULT_RISK = "Existen fricciones repetidas que pueden frenar conversión o adopción."

# ✅ Límites configurables para control de memoria/CPU
MAX_QUESTIONS_LOAD = 500  # Máx. preguntas a cargar en memoria para resumen
TOP_QUESTIONS_COUNT = 15
TOP_TRENDS_COUNT = 10


class ReportGenerator:
    def __init__(self, db):
        self.db = db

    def _safe_db_call(self, method, *args, default=None, **kwargs):
        """Wrapper seguro para llamadas a DB con fallback."""
        try:
            return method(*args, **kwargs)
        except Exception as e:
            logger.warning(f"⚠️ DB error en {method.__name__}: {e}")
            return default if default is not None else []

    def _main_finding(self, top_category: str, top_source: str, total: int) -> str:
        if total == 0:
            return "No hay suficientes datos todavía para generar hallazgos sólidos."
        return f"La mayor concentración de señales está en {top_category.lower()}, con predominio de datos desde {top_source}."

    def _opportunity(self, category: str) -> str:
        return OPPORTUNITY_MAP.get(category, DEFAULT_OPPORTUNITY)

    def _risks(self, category: str) -> str:
        return RISKS_MAP.get(category, DEFAULT_RISK)

    def _recommendation(self, category: str, source: str) -> str:
        return f"Priorizar el tema {category.lower()} y validar la señal con {source}, luego convertirla en acciones concretas."

    def build_summary(self, topic: str = "E-commerce Paraguay", period_label: str = "últimos 90 días") -> Dict[str, Any]:
        """Genera resumen con caché opcional, límites estrictos y fallback seguro."""
        
        # ✅ 1. Obtener datos de DB con protección
        rows = self._safe_db_call(self.db.get_all_questions_with_items, default=[])
        trends = self._safe_db_call(self.db.get_trend_terms, limit=TOP_TRENDS_COUNT, default=[])
        
        # ✅ 2. Límite de memoria: procesar máx. MAX_QUESTIONS_LOAD
        if len(rows) > MAX_QUESTIONS_LOAD:
            logger.info(f"⚠️ Limitando a {MAX_QUESTIONS_LOAD} preguntas de {len(rows)} totales para resumen")
            rows = rows[:MAX_QUESTIONS_LOAD]
        
        # ✅ 3. Contadores y colección segura
        categories = Counter()
        sources = Counter()
        source_types = Counter()
        questions = []

        for row in rows:
            try:
                # ✅ Desempaquetado seguro con fallbacks
                question = row[0] or ""
                category = (row[1] or "Otros").strip()
                confidence = float(row[2]) if row[2] is not None else 0.0
                title = row[4] or ""
                url = row[5] or ""
                item_type = row[6] or ""
                scraped_at = row[7]
                source_name = (row[8] or "Sin fuente").strip()
                source_type = (row[9] or "unknown").strip()

                categories[category] += 1
                sources[source_name] += 1
                source_types[source_type] += 1

                questions.append({
                    "question": question[:300],  # ✅ Truncar para ahorrar memoria
                    "category": category,
                    "confidence": confidence,
                    "title": title[:200],
                    "url": url,
                    "item_type": item_type,
                    "source_name": source_name,
                    "source_type": source_type,
                    "scraped_at": scraped_at
                })
            except (IndexError, TypeError, ValueError) as e:
                logger.warning(f"⚠️ Fila malformada en resumen: {e}")
                continue

        # ✅ 4. Top questions con heapq (O(n log k) vs O(n log n))
        if questions:
            top_questions = heapq.nlargest(
                TOP_QUESTIONS_COUNT, 
                questions, 
                key=lambda x: x["confidence"]
            )
        else:
            top_questions = []

        # ✅ 5. Trends con validación
        trend_keywords = []
        for row in trends[:TOP_TRENDS_COUNT]:
            try:
                trend_keywords.append({
                    "keyword": row[0] or "",
                    "geo": row[5] or "",
                    "captured_at": row[6],
                    "autocomplete": row[3] or [],
                    "related_top": row[1] or [],
                    "related_rising": row[2] or [],
                    "interest_over_time": row[4] or []
                })
            except (IndexError, TypeError):
                continue

        # ✅ 6. Métricas principales con fallback
        top_category = categories.most_common(1)[0][0] if categories else "Sin datos"
        top_source = source_types.most_common(1)[0][0] if source_types else "Sin datos"
        total_questions = len(questions)

        return {
            "topic": topic,
            "period": period_label,
            "total_questions": total_questions,
            "top_category": top_category,
            "top_source": top_source,
            "categories": dict(categories),
            "sources": dict(sources),
            "source_types": dict(source_types),
            "top_questions": top_questions,
            "trend_keywords": trend_keywords,
            "main_finding": self._main_finding(top_category, top_source, total_questions),
            "opportunity": self._opportunity(top_category),
            "risks": self._risks(top_category),
            "recommendation": self._recommendation(top_category, top_source)
        }

    def build_summary_cached(self, topic: str = "E-commerce Paraguay", period_label: str = "últimos 90 días", ttl: int = 900):
        """
        Versión con caché automático (usa trendqa.cache si está disponible).
        Útil para endpoints que se llaman frecuentemente con mismos parámetros.
        """
        try:
            from trendqa.cache import cached
            # ✅ Decorador dinámico con clave por parámetros
            return cached(ttl=ttl, key_prefix="report")(self.build_summary)(topic, period_label)
        except ImportError:
            # Fallback si cache.py no está disponible
            logger.warning("⚠️ Cache no disponible, ejecutando build_summary directo")
            return self.build_summary(topic, period_label)
