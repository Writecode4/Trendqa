import re, os, json, hashlib, time
from datetime import datetime, timedelta
from pathlib import Path
import requests
from bs4 import BeautifulSoup

CACHE_DIR = Path("/tmp/news_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_TTL = 1800
MAX_RESPONSE_SIZE = 150_000

_PATTERNS = {
    "google_news_url": re.compile(r"https://news\.google\.com/articles/[^\"'\s]+"),
    "source_from_url": re.compile(r"/([^/]+?)(?:\?|$)"),
    "date_iso": re.compile(r"(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2})"),
    "date_relative": re.compile(r"(\d+)\s*(hora|horas|minuto|minutos|día|días)"),
}

_SELECTORS = {
    "title": ["article h3 a", "article h4 a", "a[jsname]", "[role='heading'] a"],
    "link": ["article h3 a[href]", "a[jsname][href]", "a[href*='/articles/']"],
    "snippet": ["[role='text']", "article p", "[class*='snippet']"],
    "source": ["article [aria-label]", "time", "[class*='source']"],
    "time": ["article time", "[datetime]"],
}

def _cached_get_news(url, headers, timeout=15):
    cache_key = hashlib.md5(f"gn:{url}".encode()).hexdigest()
    cache_file = CACHE_DIR / f"{cache_key}.json"
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            if time.time() - data["ts"] < CACHE_TTL:
                return data["html"], True
        except:
            cache_file.unlink(missing_ok=True)
    try:
        r = requests.get(url, headers=headers, timeout=timeout, stream=True)
        if r.status_code != 200: return None, False
        content = b""
        for chunk in r.iter_content(chunk_size=8192):
            content += chunk
            if len(content) >= MAX_RESPONSE_SIZE: break
        html = content.decode("utf-8", errors="ignore")[:MAX_RESPONSE_SIZE]
        if "<article" in html or "heading" in html:
            cache_file.write_text(json.dumps({"ts": time.time(), "html": html}))
        return html, False
    except: return None, False

# ✅ Mapeo multi-país para Google News
_COUNTRY_NEWS_MAP = {
    "paraguay": ("PY", "PY:es-419"),
    "argentina": ("AR", "AR:es-419"),
    "mexico": ("MX", "MX:es-419"),
}

class GoogleNewsIngestor:
    def __init__(self, query=None, days=90, pais="paraguay"):
        self.query = query or ""
        self.limit_date = datetime.now() - timedelta(days=days)
        self.pais = pais.lower()
        self.query_words = [w for w in (query.lower().split() if query else []) if len(w) > 3 and w not in {"paraguay","argentina","mexico","para","que","como","cuanto","cual","sobre"}]
        self.query_pattern = re.compile(r'|'.join(re.escape(w) for w in self.query_words), re.I) if self.query_words else None
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0",
            "Accept-Language": "es-419,es;q=0.9",
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        }

    def _matches_query(self, text):
        if not self.query_pattern: return True
        return bool(self.query_pattern.search(text))

    def _extract_text(self, element, max_len=200):
        if not element: return ""
        return (element.get_text(strip=True) or element.get("title") or element.get("alt", ""))[:max_len].strip()

    def _parse_date(self, time_str):
        if not time_str: return None
        match = _PATTERNS["date_iso"].search(time_str)
        if match:
            try: return datetime.fromisoformat(match.group(1).replace(" ", "T").replace("Z", "+00:00"))
            except: pass
        match = _PATTERNS["date_relative"].search(time_str.lower())
        if match:
            try:
                v = int(match.group(1))
                u = match.group(2)
                if "hora" in u: return datetime.now() - timedelta(hours=v)
                if "minuto" in u: return datetime.now() - timedelta(minutes=v)
                if "día" in u: return datetime.now() - timedelta(days=v)
            except: pass
        return None

    def _parse_article(self, art, base_url="https://news.google.com"):
        title = ""
        for sel in _SELECTORS["title"]:
            el = art.select_one(sel)
            if el:
                title = self._extract_text(el, 200)
                if title and len(title) > 10: break
        if not title or len(title) > 300 or not self._matches_query(title): return None
        link = ""
        for sel in _SELECTORS["link"]:
            el = art.select_one(sel)
            if el:
                href = el.get("href", "")
                if href.startswith("./"): href = base_url + href[1:]
                elif href.startswith("/articles/"): href = base_url + href
                if href and "http" in href: link = href; break
        snippet = ""
        for sel in _SELECTORS["snippet"]:
            el = art.select_one(sel)
            if el:
                snippet = self._extract_text(el, 300)
                if snippet: break
        source = ""
        for sel in _SELECTORS["source"]:
            el = art.select_one(sel)
            if el:
                txt = self._extract_text(el, 50)
                if txt and len(txt) < 60 and ":" not in txt: source = txt; break
        if not source and link:
            m = _PATTERNS["source_from_url"].search(link)
            if m: source = m.group(1).replace("-", " ").title()
        created_dt = None
        time_el = art.select_one(_SELECTORS["time"][0])
        if time_el:
            created_dt = self._parse_date(time_el.get("datetime") or self._extract_text(time_el, 30))
        if created_dt and created_dt < self.limit_date: return None
        return {
            "id": f"gn_{hashlib.md5(title.encode()).hexdigest()[:12]}",
            "title": title, "content": (title + (f". {snippet}" if snippet else ""))[:400],
            "url": link, "author": source or "Google News",
            "created_utc": created_dt.timestamp() if created_dt else datetime.now().timestamp(),
            "created_at": created_dt.isoformat() if created_dt else datetime.now().isoformat(),
            "raw_json": None, "item_type": "news_article",
            "source_name": f"Google News - {source}" if source else "Google News", "source_type": "google_news",
        }

    def fetch(self, max_results=10, **kwargs):
        if not self.query: return []
        items, seen = [], set()
        gl, ceid = _COUNTRY_NEWS_MAP.get(self.pais, ("PY", "PY:es-419"))
        url = f"https://news.google.com/search?q={requests.utils.quote(self.query)}&hl=es-419&gl={gl}&ceid={ceid}"
        html, _ = _cached_get_news(url, self.headers, timeout=15)
        if not html: return []
        soup = BeautifulSoup(html, "html.parser")
        for art in soup.select("article")[:max_results + 5]:
            if len(items) >= max_results: break
            item = self._parse_article(art)
            if item and item["title"] not in seen:
                seen.add(item["title"]); items.append(item)
        return items
