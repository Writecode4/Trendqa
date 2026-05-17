import re
import unicodedata
from bs4 import BeautifulSoup


class TextNormalizer:
    def clean_text(self, text):
        if not text:
            return ""
        text = BeautifulSoup(str(text), "html.parser").get_text(" ")
        text = unicodedata.normalize("NFKD", text)
        text = text.encode("ascii", "ignore").decode("utf-8")
        text = text.lower()
        text = re.sub(r"https?://\S+|www\.\S+", " ", text)
        text = re.sub(r"[^a-z0-9áéíóúüñ\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def normalize_item(self, item):
        item["title"] = self.clean_text(item.get("title", ""))
        item["content"] = self.clean_text(item.get("content", ""))
        return item