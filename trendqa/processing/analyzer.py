import json
import os
import re
import time
from collections import Counter
from groq import Groq, RateLimitError

from .normalize import TextNormalizer


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


class QuestionAnalyzer:
    CATEGORIES = (
        "envios", "pagos", "precios", "productos",
        "garantia_devolucion", "proveedores", "experiencia", "otros"
    )

    def __init__(self, max_items=5):
        self.max_items = max_items
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY no configurada en las variables de entorno")
        self.client = Groq(api_key=api_key)
        self.model = "llama-3.3-70b-versatile"

    def _parse_retry_after(self, error_msg):
        match = re.search(r"try again in ([0-9.]+)s", str(error_msg))
        return float(match.group(1)) if match else 10

    def analyze_post(self, title, content, retries=3):
        prompt = f"""Analizá el siguiente post sobre e-commerce en Paraguay y extraé las preguntas que el usuario está haciendo.

Título: {title[:300]}
Contenido: {content[:1000]}

Respondé SOLO con un JSON array. Cada elemento debe tener:
- "pregunta": la pregunta textual
- "categoria": una de {', '.join(self.CATEGORIES)}
- "confianza": número entre 0 y 1

Ejemplo:
[{{"pregunta": "Alguien sabe si hace envíos al interior?", "categoria": "envios", "confianza": 0.9}}]

Si no hay preguntas claras, devolvé [].
"""
        for attempt in range(retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                )
                raw = response.choices[0].message.content.strip()
                raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```")
                data = json.loads(raw)
                if isinstance(data, dict):
                    return data.get("preguntas", data.get("questions", []))
                return data if isinstance(data, list) else []
            except RateLimitError as e:
                wait = self._parse_retry_after(str(e))
                print(f"  Límite excedido, esperando {wait:.0f}s (intento {attempt + 1}/{retries})")
                time.sleep(wait)
            except Exception as e:
                print(f"Error QuestionAnalyzer: {e}")
                return []
        return []

    def analyze_items(self, items):
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
                    "model_used": self.model,
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "source_type": item.get("source_type", "unknown"),
                    "source_name": item.get("source_name", ""),
                })
            time.sleep(1)
        return results