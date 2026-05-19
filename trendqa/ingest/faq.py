from datetime import datetime


class FAQIngestor:
    def __init__(self, query=None):
        self.query_words = [w for w in (query.lower().split() if query else []) if len(w) > 2 and w != "paraguay"]
        self.items = [
            {
                "question": "¿Cuál es el mejor courier para Paraguay?",
                "answer": "Depende del costo, tiempo y soporte. Conviene comparar reseñas y tiempos de entrega.",
                "source_name": "FAQ Interna",
                "source_type": "faq"
            },
            {
                "question": "¿Cuánto tarda un envío internacional?",
                "answer": "Varía según origen, courier y aduana. Puede ir de pocos días a varias semanas.",
                "source_name": "FAQ Interna",
                "source_type": "faq"
            },
            {
                "question": "¿Qué es vía Miami?",
                "answer": "Es una modalidad logística para consolidar compras en EE. UU. antes de enviarlas a Paraguay.",
                "source_name": "FAQ Interna",
                "source_type": "faq"
            }
        ]

    def fetch(self):
        now = datetime.now()
        out = []
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
                "source_name": item["source_name"],
                "source_type": item["source_type"]
            })
        return out
