import re
import requests
import json
from datetime import datetime
from bs4 import BeautifulSoup
from pytrends.request import TrendReq


_GEO_MAP = {
    "paraguay": "PY", "argentina": "AR", "mexico": "MX",
    "colombia": "CO", "chile": "CL", "peru": "PE",
    "brasil": "BR", "españa": "ES", "estados unidos": "US",
}

_GEO_TO_COUNTRY = {v: k for k, v in _GEO_MAP.items()}

_OTHER_COUNTRY_KEYWORDS = [
    "argentina", "chile", "colombia", "peru", "mexico", "brasil", "uruguay",
    "bolivia", "ecuador", "venezuela", "españa", "ee.uu.",
    "paraguay", "ande", "edenor", "edesa", "epr", "cfe", "codensa",
    "electricaribe", "enel", "luz del sur",
    "europa", "europe", "europeo", "european", "ue", "union europea",
    "alemania", "germany", "francia", "france", "italia", "italy",
    "reino unido", "united kingdom", "uk", "inglaterra", "england",
    "portugal", "holanda", "netherlands", "belgica", "belgium",
    "suiza", "switzerland", "suecia", "sweden", "noruega", "norway",
    "dinamarca", "denmark", "polonia", "poland", "rusia", "russia",
    "china", "japon", "japan", "india", "asia", "africa",
    "australia", "canada",
]

def _filter_trends_by_country(terms, geo):
    target = _GEO_TO_COUNTRY.get(geo, "").lower()
    if not target:
        return terms
    other_keywords = [kw for kw in _OTHER_COUNTRY_KEYWORDS if kw != target]
    return [
        t for t in terms
        if not any(ok in t.lower() for ok in other_keywords)
    ]

class GoogleTrendsIngestor:
    def __init__(self, hl="es-419", tz=-240, geo=None, pais=None):
        if geo is None and pais:
            geo = _GEO_MAP.get(pais.lower(), "PY")
        self.geo = geo or "PY"
        self.pytrends = None
        try:
            self.pytrends = TrendReq(hl=hl, tz=tz, geo=self.geo)
        except Exception:
            pass
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0",
            "Accept-Language": "es-419,es;q=0.9",
        }

    def get_autocomplete(self, keyword, limit=10):
        # Estrategia 1: API de Google Suggest
        try:
            r = requests.get(
                "https://suggestqueries.google.com/complete/search",
                params={"client": "firefox", "hl": "es", "q": keyword},
                timeout=15,
            )
            if r.status_code == 200:
                data = r.json()
                return data[1][:limit] if len(data) > 1 else []
        except Exception:
            pass

        # Estrategia 2: Scrape Google Suggest HTML
        try:
            r = requests.get(
                "https://www.google.com/complete/search",
                params={"q": keyword, "hl": "es", "client": "gws-wiz", "xssi": "t"},
                headers=self.headers,
                timeout=15,
            )
            if r.status_code == 200:
                raw = r.text
                matches = re.findall(r'\["(.*?)"', raw)
                return [m for m in matches if len(m) > 2][:limit]
        except Exception:
            pass

        return []

    def _scrape_trends_page(self, keyword):
        """Fallback: scrape Google Trends explore page directamente."""
        result = {
            "autocomplete": [],
            "related_top": [],
            "related_rising": [],
            "interest_over_time": [],
        }
        try:
            url = f"https://trends.google.com/trends/explore?geo={self.geo}&q={requests.utils.quote(keyword)}"
            r = requests.get(url, headers=self.headers, timeout=20)
            if r.status_code != 200:
                return result
            soup = BeautifulSoup(r.text, "html.parser")

            # Extraer términos relacionados del HTML
            related_blocks = (
                soup.select("div[class*='related']")
                or soup.select("div[class*='entity']")
                or soup.select("div[class*='item']")
                or []
            )
            seen = set()
            scraped = []
            for block in related_blocks[:15]:
                text = block.get_text(strip=True)
                if text and len(text) > 2 and text not in seen:
                    seen.add(text)
                    scraped.append(text)
            result["related_top"] = _filter_trends_by_country(scraped, self.geo)
        except Exception:
            pass

        result["autocomplete"] = self.get_autocomplete(keyword)
        return result

    def get_trend_bundle(self, keyword):
        result = {
            "keyword": keyword,
            "geo": self.geo,
            "captured_at": datetime.now().isoformat(),
            "autocomplete": [],
            "related_top": [],
            "related_rising": [],
            "interest_over_time": [],
        }

        # Estrategia 1: pytrends library
        if self.pytrends:
            try:
                self.pytrends.build_payload([keyword], timeframe="today 12-m", geo=self.geo)
                related = self.pytrends.related_queries()
                if keyword in related and related[keyword]:
                    top_df = related[keyword].get("top")
                    rising_df = related[keyword].get("rising")
                    if top_df is not None and not top_df.empty:
                        result["related_top"] = _filter_trends_by_country(top_df["query"].head(10).tolist(), self.geo)
                    if rising_df is not None and not rising_df.empty:
                        result["related_rising"] = _filter_trends_by_country(rising_df["query"].head(10).tolist(), self.geo)
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

        # Estrategia 2: Scrape Google Trends como fallback
        if not result["related_top"] and not result["interest_over_time"]:
            scraped = self._scrape_trends_page(keyword)
            result["related_top"] = scraped.get("related_top", [])
            result["related_rising"] = scraped.get("related_rising", [])

        # Estrategia 3: Autocomplete siempre via suggestqueries
        result["autocomplete"] = self.get_autocomplete(keyword)

        return result

    def get_topic_bundle(self, keywords):
        return [self.get_trend_bundle(kw) for kw in keywords]
