import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime


class MercadoLibreIngestor:
    def __init__(self, query=None, days=90):
        self.limit_date = datetime.now().timestamp() - days * 86400
        self.query_words = [w for w in (query.lower().split() if query else []) if len(w) > 2 and w != "paraguay"]
        self.search_url = query or ""
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "es-419,es;q=0.9",
        }

    def fetch(self, max_results=20):
        items = []
        if not self.search_url:
            return items
        try:
            url = f"https://listado.mercadolibre.com.py/{requests.utils.quote(self.search_url)}"
            r = requests.get(url, headers=self.headers, timeout=20)
            if r.status_code != 200:
                return items
            soup = BeautifulSoup(r.text, "html.parser")

            result_blocks = (
                soup.select("li.ui-search-layout__item")
                or soup.select("ol.ui-search-layout li")
                or soup.select("div.ui-search-result__content")
                or soup.select("div[class*='item']")
                or soup.find_all("li", class_=re.compile(r"item|result"))
                or [soup]
            )

            for res in result_blocks[:max_results]:
                title = ""
                for sel in (
                    "h2.ui-search-item__title",
                    "h2",
                    "h3",
                    "a[class*='title']",
                    "a[class*='item']",
                    "img[alt]",
                ):
                    el = res.select_one(sel)
                    if el:
                        title = el.get("alt", "") if el.name == "img" else el.get_text(strip=True)
                        if title:
                            break
                if not title:
                    title = res.get_text(strip=True)[:150]

                price = ""
                for sel in (
                    ".andes-money-amount__fraction",
                    ".ui-search-price__part",
                    "span[class*='price']",
                    "span[class*='amount']",
                    "div[class*='price']",
                ):
                    el = res.select_one(sel)
                    if el:
                        price = el.get_text(strip=True)
                        break

                link = ""
                for sel in (
                    "a.ui-search-link",
                    "a[href*='/py/']",
                    "a[class*='item']",
                    "a[class*='title']",
                    "a[href]",
                ):
                    el = res.select_one(sel)
                    if el:
                        href = el.get("href", "")
                        if href and "/py/" in href:
                            link = href
                            break

                content = f"{title} — {price}" if price else title
                items.append({
                    "id": f"ml_{hash(title + str(datetime.now().timestamp()))}",
                    "title": title[:200],
                    "content": content,
                    "url": link,
                    "author": None,
                    "created_utc": datetime.now().timestamp(),
                    "created_at": datetime.now().isoformat(),
                    "raw_json": None,
                    "item_type": "ml_product",
                    "source_name": "MercadoLibre Paraguay",
                    "source_type": "mercadolibre",
                })
        except Exception:
            pass
        return items
