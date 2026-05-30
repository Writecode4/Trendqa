import re
import unicodedata
from functools import lru_cache

# ✅ Regex pre-compilados (evita recompilación en cada llamada)
_HTML_TAG_RE = re.compile(r'<[^>]+>')
_URL_RE = re.compile(r'https?://\S+|www\.\S+')
_NON_WORD_RE = re.compile(r'[^a-z0-9áéíóúüñ\s]')
_WHITESPACE_RE = re.compile(r'\s+')


class TextNormalizer:
    def __init__(self, cache_size=128):
        """
        Inicializa el normalizador con caché opcional.
        :param cache_size: Máx. entradas en caché LRU (0 para desactivar)
        """
        if cache_size > 0:
            # ✅ Envuelve clean_text con caché LRU
            self.clean_text = lru_cache(maxsize=cache_size)(self._clean_text_impl)
        else:
            self.clean_text = self._clean_text_impl

    def _clean_text_impl(self, text):
        """Implementación real de limpieza (llamada directa o vía caché)."""
        if not text:
            return ""
        
        # ✅ 1. Strip HTML ligero (regex es 10-20x más rápido que BeautifulSoup para texto simple)
        text = _HTML_TAG_RE.sub(" ", str(text))
        
        # ✅ 2. Normalizar unicode SIN perder acentos (NFKD + recombina)
        #    Esto preserva "envío" → "envío" en lugar de "envio"
        text = unicodedata.normalize("NFKC", text)
        
        # ✅ 3. Lowercase
        text = text.lower()
        
        # ✅ 4. Remover URLs y caracteres no deseados en un solo paso optimizado
        text = _URL_RE.sub(" ", text)
        text = _NON_WORD_RE.sub(" ", text)
        
        # ✅ 5. Colapsar espacios y strip final
        text = _WHITESPACE_RE.sub(" ", text).strip()
        
        return text

    def normalize_item(self, item):
        """Normaliza título y contenido de un item (mantiene compatibilidad)."""
        # ✅ Copia para no mutar el original si se usa en múltiples lugares
        item = dict(item)
        item["title"] = self.clean_text(item.get("title", ""))
        item["content"] = self.clean_text(item.get("content", ""))
        return item

    def clear_cache(self):
        """Limpia la caché manualmente (útil para tests o liberar memoria)."""
        if hasattr(self.clean_text, "cache_clear"):
            self.clean_text.cache_clear()
