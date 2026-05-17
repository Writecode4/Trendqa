from datetime import datetime


class ReviewsIngestor:
    def __init__(self):
        self.items = [
            {
                "title": "Opinión sobre courier A",
                "content": "Buen precio, pero soporte lento en temporadas altas.",
                "source_name": "Reviews Internas",
                "source_type": "review"
            },
            {
                "title": "Opinión sobre courier B",
                "content": "Entrega rápida y seguimiento claro, aunque cuesta un poco más.",
                "source_name": "Reviews Internas",
                "source_type": "review"
            }
        ]

    def fetch(self):
        now = datetime.now()
        out = []
        for i, item in enumerate(self.items):
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
                "source_name": item["source_name"],
                "source_type": item["source_type"]
            })
        return out