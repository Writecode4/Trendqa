import requests
import json
from datetime import datetime
from pytrends.request import TrendReq


class GoogleTrendsIngestor:
    def __init__(self, hl="es-419", tz=-240, geo="PY"):
        self.pytrends = TrendReq(hl=hl, tz=tz)
        self.geo = geo
        self.autocomplete_url = "https://suggestqueries.google.com/complete/search"

    def get_autocomplete(self, keyword, limit=10):
        try:
            r = requests.get(
                self.autocomplete_url,
                params={"client": "firefox", "hl": "es", "q": keyword},
                timeout=15
            )
            if r.status_code != 200:
                return []
            data = r.json()
            return data[1][:limit] if len(data) > 1 else []
        except Exception:
            return []

    def get_trend_bundle(self, keyword):
        result = {
            "keyword": keyword,
            "geo": self.geo,
            "captured_at": datetime.now().isoformat(),
            "autocomplete": [],
            "related_top": [],
            "related_rising": [],
            "interest_over_time": []
        }

        try:
            self.pytrends.build_payload([keyword], timeframe="today 12-m", geo=self.geo)
            related = self.pytrends.related_queries()

            if keyword in related and related[keyword]:
                top_df = related[keyword].get("top")
                rising_df = related[keyword].get("rising")

                if top_df is not None and not top_df.empty:
                    result["related_top"] = top_df["query"].head(10).tolist()

                if rising_df is not None and not rising_df.empty:
                    result["related_rising"] = rising_df["query"].head(10).tolist()

            iot = self.pytrends.interest_over_time()
            if iot is not None and not iot.empty:
                cols = [c for c in iot.columns if c != "isPartial"]
                if cols:
                    key = cols[0]
                    result["interest_over_time"] = [
                        {"date": idx.strftime("%Y-%m-%d"), "value": int(row[key])}
                        for idx, row in iot.iterrows()
                    ]

        except Exception:
            pass

        result["autocomplete"] = self.get_autocomplete(keyword)
        return result

    def get_topic_bundle(self, keywords):
        return [self.get_trend_bundle(kw) for kw in keywords]