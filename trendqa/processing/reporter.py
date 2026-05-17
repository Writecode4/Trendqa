import json
from collections import Counter


class ReportGenerator:
    def __init__(self, db):
        self.db = db

    def build_summary(self, topic="E-commerce Paraguay", period_label="últimos 90 días"):
        rows = self.db.get_all_questions_with_items()
        trends = self.db.get_trend_terms(limit=20)

        categories = Counter()
        sources = Counter()
        source_types = Counter()
        questions = []

        for row in rows:
            question, category, confidence, model_used, title, url, item_type, scraped_at, source_name, source_type = row
            category = category or "Otros"
            source_name = source_name or "Sin fuente"
            source_type = source_type or "unknown"

            categories[category] += 1
            sources[source_name] += 1
            source_types[source_type] += 1

            questions.append({
                "question": question,
                "category": category,
                "confidence": float(confidence) if confidence is not None else 0.0,
                "title": title,
                "url": url,
                "item_type": item_type,
                "source_name": source_name,
                "source_type": source_type,
                "scraped_at": scraped_at
            })

        questions_sorted = sorted(questions, key=lambda x: x["confidence"], reverse=True)
        top_questions = questions_sorted[:15]

        trend_keywords = []
        for row in trends[:10]:
            keyword, related_top, related_rising, autocomplete, interest_over_time, geo, captured_at = row
            trend_keywords.append({
                "keyword": keyword,
                "geo": geo,
                "captured_at": captured_at,
                "autocomplete": autocomplete,
                "related_top": related_top,
                "related_rising": related_rising,
                "interest_over_time": interest_over_time
            })

        top_category = categories.most_common(1)[0][0] if categories else "Sin datos"
        top_source = source_types.most_common(1)[0][0] if source_types else "Sin datos"

        summary = {
            "topic": topic,
            "period": period_label,
            "total_questions": len(questions),
            "top_category": top_category,
            "top_source": top_source,
            "categories": dict(categories),
            "sources": dict(sources),
            "source_types": dict(source_types),
            "top_questions": top_questions,
            "trend_keywords": trend_keywords,
            "main_finding": self._main_finding(top_category, top_source, len(questions)),
            "opportunity": self._opportunity(top_category),
            "risks": self._risks(top_category),
            "recommendation": self._recommendation(top_category, top_source)
        }
        return summary

    def _main_finding(self, top_category, top_source, total_questions):
        if total_questions == 0:
            return "No hay suficientes datos todavía para generar hallazgos sólidos."
        return f"La mayor concentración de señales está en {top_category.lower()}, con predominio de datos desde {top_source}."

    def _opportunity(self, top_category):
        mapping = {
            "E-commerce": "Hay oportunidad para contenido, servicio o producto enfocado en compras, pagos y logística.",
            "Fintech": "Hay oportunidad para soluciones de pago, tarjetas, billeteras y fricción financiera.",
            "Logística": "Hay oportunidad para mejorar entrega, seguimiento, couriers y experiencia postcompra.",
            "Trámites": "Hay oportunidad para simplificar procesos, importación y gestión operativa."
        }
        return mapping.get(top_category, "Hay oportunidad para atacar el dolor recurrente detectado en la conversación.")

    def _risks(self, top_category):
        mapping = {
            "E-commerce": "Persisten dudas sobre confianza, devoluciones, costos y tiempos de entrega.",
            "Fintech": "La fricción se concentra en medios de pago, validación y compatibilidad bancaria.",
            "Logística": "Los principales riesgos están en demoras, aduanas y seguimiento del envío.",
            "Trámites": "El riesgo está en complejidad operativa, requisitos y procesos poco claros."
        }
        return mapping.get(top_category, "Existen fricciones repetidas que pueden frenar conversión o adopción.")

    def _recommendation(self, top_category, top_source):
        return f"Priorizar el tema {top_category.lower()} y validar la señal con {top_source}, luego convertirla en acciones concretas."