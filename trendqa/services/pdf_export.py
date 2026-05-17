from xhtml2pdf import pisa
from pathlib import Path


class PDFExporter:
    def export(self, html_path, output_path, base_url="."):
        html_path = Path(html_path)
        output_path = Path(output_path)

        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()

        return self.export_string(html, output_path, base_url)

    def export_string(self, html, output_path, base_url="."):
        output_path = Path(output_path)

        with open(output_path, "wb") as f:
            pisa.CreatePDF(html, dest=f, encoding="utf-8", link_callback=self._link_callback(base_url))

        return str(output_path)

    def _link_callback(self, base_url):
        base_url = Path(base_url).resolve()

        def callback(uri, rel):
            p = (base_url / uri).resolve()
            if p.exists():
                return str(p)
            return uri

        return callback