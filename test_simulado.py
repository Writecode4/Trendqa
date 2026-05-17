import sys
sys.path.insert(0, ".")

from trendqa.db import Database
from trendqa.ingest.faq import FAQIngestor
from trendqa.ingest.reviews import ReviewsIngestor
from trendqa.processing.analyzer import TrendAnalyzer
from trendqa.processing.reporter import ReportGenerator

items = FAQIngestor().fetch()
items += ReviewsIngestor().fetch()
print(f"Items locales: {len(items)}")

ta = TrendAnalyzer()
r = ta.analyze_items(items)
print(f"Keywords: {r['top_keywords'][:3]}")

db = Database()
print(f"DB lista en: {db.db_path}")

rg = ReportGenerator(db)
s = rg.build_summary(topic="test", period_label="simulado")
print(f"Reporte generado: {s['total_questions']} preguntas")
print("TODO OK")
