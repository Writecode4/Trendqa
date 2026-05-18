from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


BLUE = HexColor("#0496FF")
DARK = HexColor("#111827")
GRAY = HexColor("#6B7280")
LIGHT_GRAY = HexColor("#F3F4F6")
WHITE = HexColor("#FFFFFF")

LOGO_HEIGHT = 28


class PDFExporter:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()

    def _logo_path(self):
        p = self.base_dir / "static" / "images" / "logo-sikuri.png"
        return str(p) if p.exists() else None

    def export_summary(self, summary, output_path):
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            topMargin=2*cm,
            bottomMargin=2*cm,
            leftMargin=2*cm,
            rightMargin=2*cm,
        )

        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(
            "Title2", parent=styles["Heading1"], fontSize=20,
            spaceAfter=6, textColor=DARK, fontName="Helvetica-Bold",
        ))
        styles.add(ParagraphStyle(
            "SubTitle", parent=styles["Normal"], fontSize=10,
            textColor=GRAY, spaceAfter=2,
        ))
        styles.add(ParagraphStyle(
            "SectionTitle", parent=styles["Heading2"], fontSize=13,
            spaceBefore=14, spaceAfter=6, textColor=DARK,
            fontName="Helvetica-Bold",
        ))
        styles.add(ParagraphStyle(
            "Body2", parent=styles["Normal"], fontSize=9.5,
            leading=14, textColor=DARK, spaceAfter=6,
        ))
        styles.add(ParagraphStyle(
            "CardTitle", parent=styles["Normal"], fontSize=10,
            textColor=BLUE, fontName="Helvetica-Bold", spaceAfter=2,
        ))
        styles.add(ParagraphStyle(
            "TableHeader", parent=styles["Normal"], fontSize=8.5,
            textColor=WHITE, fontName="Helvetica-Bold",
        ))
        styles.add(ParagraphStyle(
            "TableCell", parent=styles["Normal"], fontSize=8.5,
            textColor=DARK, leading=12,
        ))
        styles.add(ParagraphStyle(
            "Footer", parent=styles["Normal"], fontSize=8,
            textColor=GRAY, alignment=TA_CENTER,
        ))
        styles.add(ParagraphStyle(
            "BrandName", parent=styles["Normal"], fontSize=16,
            textColor=DARK, fontName="Helvetica-Bold",
        ))

        elements = []

        # --- Header ---
        logo_path = self._logo_path()
        header_data = []
        if logo_path:
            img = Image(logo_path, width=LOGO_HEIGHT, height=LOGO_HEIGHT)
            header_data.append(img)
        header_data.append(Paragraph("<b>SIKURI</b>", styles["BrandName"]))
        header_table = Table([header_data], colWidths=[LOGO_HEIGHT + 4, None])
        header_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (0, 0), 0),
            ("RIGHTPADDING", (1, 1), (1, 1), 0),
        ]))
        elements.append(header_table)
        elements.append(Spacer(1, 4))
        elements.append(Table([[" "]], colWidths=[460], style=TableStyle([
            ("LINEBELOW", (0, 0), (-1, -1), 2, BLUE),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ])))
        elements.append(Spacer(1, 12))

        # --- Title ---
        elements.append(Paragraph("TrendQA &mdash; Resumen ejecutivo de tendencias", styles["Title2"]))
        elements.append(Spacer(1, 8))

        # --- Meta ---
        meta_text = (
            f"<b>Período:</b> {summary.get('period', 'N/A')}<br/>"
            f"<b>Tema:</b> {summary.get('topic', 'N/A')}<br/>"
            f"<b>Total de señales:</b> {summary.get('total_questions', 0)}"
        )
        elements.append(Paragraph(meta_text, styles["SubTitle"]))
        elements.append(Spacer(1, 12))

        # --- Cards: Hallazgo, Oportunidad, Riesgos, Recomendación ---
        cards = [
            ("Hallazgo principal", summary.get("main_finding", "")),
            ("Oportunidad", summary.get("opportunity", "")),
            ("Riesgos o fricciones", summary.get("risks", "")),
            ("Recomendación", summary.get("recommendation", "")),
        ]
        for label, text in cards:
            card_data = [
                [Paragraph(label, styles["CardTitle"])],
                [Paragraph(text, styles["Body2"])],
            ]
            card_table = Table(card_data, colWidths=[460])
            card_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GRAY),
                ("BOX", (0, 0), (-1, -1), 0.5, HexColor("#E5E7EB")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("LINEBELOW", (0, 0), (-1, 0), 1, BLUE),
            ]))
            elements.append(card_table)
            elements.append(Spacer(1, 8))

        # --- Oportunidades priorizadas ---
        oportunidades = summary.get("oportunidades", [])
        if oportunidades:
            elements.append(Paragraph("Oportunidades priorizadas", styles["SectionTitle"]))
            opp_data = [[
                Paragraph("Categoría", styles["TableHeader"]),
                Paragraph("Señales", styles["TableHeader"]),
                Paragraph("Score", styles["TableHeader"]),
                Paragraph("Impacto en negocio", styles["TableHeader"]),
            ]]
            for o in oportunidades[:6]:
                opp_data.append([
                    Paragraph(o["categoria"], styles["TableCell"]),
                    Paragraph(f"{o['señales']} ({o['porcentaje']})", styles["TableCell"]),
                    Paragraph(str(o["score"]), styles["TableCell"]),
                    Paragraph(o.get("impacto_negocio", ""), styles["TableCell"]),
                ])
            opp_table = Table(opp_data, colWidths=[100, 70, 50, 240])
            opp_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), DARK),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#E5E7EB")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]))
            elements.append(opp_table)
            elements.append(Spacer(1, 12))

        # --- Preguntas destacadas ---
        top_items = summary.get("top_items", [])
        if top_items:
            elements.append(Paragraph("Preguntas destacadas", styles["SectionTitle"]))
            q_data = [[
                Paragraph("Pregunta", styles["TableHeader"]),
                Paragraph("Categoría", styles["TableHeader"]),
                Paragraph("Fuente", styles["TableHeader"]),
                Paragraph("Conf.", styles["TableHeader"]),
            ]]
            for item in top_items[:12]:
                q_data.append([
                    Paragraph(item.get("question", "")[:80], styles["TableCell"]),
                    Paragraph(item.get("category", ""), styles["TableCell"]),
                    Paragraph(item.get("source_type", ""), styles["TableCell"]),
                    Paragraph(f"{item.get('confidence', 0):.2f}", styles["TableCell"]),
                ])
            q_table = Table(q_data, colWidths=[220, 90, 80, 70])
            q_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), DARK),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#E5E7EB")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]))
            elements.append(q_table)
            elements.append(Spacer(1, 12))

        # --- Footer ---
        elements.append(Spacer(1, 20))
        elements.append(Table([[" "]], colWidths=[460], style=TableStyle([
            ("LINEABOVE", (0, 0), (-1, -1), 0.5, HexColor("#E5E7EB")),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ])))
        elements.append(Spacer(1, 8))
        elements.append(Paragraph(
            "&copy; 2026 SIKURI &mdash; Generado por TrendQA",
            styles["Footer"],
        ))

        doc.build(elements)
        return str(output_path)
