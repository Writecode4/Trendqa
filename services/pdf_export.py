from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
)
from reportlab.lib.enums import TA_CENTER


BLUE = HexColor("#0496FF")
DARK = HexColor("#111827")
GRAY = HexColor("#6B7280")
LIGHT_GRAY = HexColor("#F3F4F6")
WHITE = HexColor("#FFFFFF")
RED = HexColor("#EF4444")
GREEN = HexColor("#34D399")
AMBER = HexColor("#FBBF24")
PURPLE = HexColor("#A78BFA")
BLUE_HEX = "#0496FF"
DARK_HEX = "#111827"
GRAY_HEX = "#6B7280"
RED_HEX = "#EF4444"
GREEN_HEX = "#34D399"
AMBER_HEX = "#FBBF24"
PURPLE_HEX = "#A78BFA"
LOGO_HEIGHT = 28


def _p(text, style):
    return Paragraph(text, style)


class PDFExporter:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()

    def _logo_path(self):
        p = self.base_dir / "static" / "images" / "logo-sikuri.png"
        return str(p) if p.exists() else None

    def _make_styles(self, styles):
        styles.add(ParagraphStyle("Title2", parent=styles["Heading1"], fontSize=20, spaceAfter=6, textColor=DARK, fontName="Helvetica-Bold"))
        styles.add(ParagraphStyle("SubTitle", parent=styles["Normal"], fontSize=10, textColor=GRAY, spaceAfter=2))
        styles.add(ParagraphStyle("SectionTitle", parent=styles["Heading2"], fontSize=13, spaceBefore=14, spaceAfter=6, textColor=DARK, fontName="Helvetica-Bold"))
        styles.add(ParagraphStyle("Body2", parent=styles["Normal"], fontSize=9.5, leading=14, textColor=DARK, spaceAfter=6))
        styles.add(ParagraphStyle("CardTitle", parent=styles["Normal"], fontSize=10, textColor=BLUE, fontName="Helvetica-Bold", spaceAfter=2))
        styles.add(ParagraphStyle("TableHeader", parent=styles["Normal"], fontSize=8.5, textColor=WHITE, fontName="Helvetica-Bold"))
        styles.add(ParagraphStyle("TableCell", parent=styles["Normal"], fontSize=8.5, textColor=DARK, leading=12))
        styles.add(ParagraphStyle("TableCellSmall", parent=styles["Normal"], fontSize=7.5, textColor=DARK, leading=11))
        styles.add(ParagraphStyle("Footer", parent=styles["Normal"], fontSize=8, textColor=GRAY, alignment=TA_CENTER))
        styles.add(ParagraphStyle("BrandName", parent=styles["Normal"], fontSize=16, textColor=DARK, fontName="Helvetica-Bold"))
        styles.add(ParagraphStyle("BadgeRisk", parent=styles["Normal"], fontSize=7.5, textColor=RED, fontName="Helvetica-Bold"))
        styles.add(ParagraphStyle("BadgeInfo", parent=styles["Normal"], fontSize=7.5, textColor=BLUE, fontName="Helvetica-Bold"))
        styles.add(ParagraphStyle("BadgeSuccess", parent=styles["Normal"], fontSize=7.5, textColor=GREEN, fontName="Helvetica-Bold"))
        styles.add(ParagraphStyle("BodySmall", parent=styles["Normal"], fontSize=8, leading=11, textColor=GRAY))
        return styles

    def _header_block(self, elements, styles):
        logo_path = self._logo_path()
        header_data = []
        if logo_path:
            img = Image(logo_path, width=LOGO_HEIGHT, height=LOGO_HEIGHT)
            header_data.append(img)
        header_data.append(_p("<b>SIKURI</b>", styles["BrandName"]))
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

    def _meta_section(self, elements, styles, summary):
        elements.append(_p("TrendQA &mdash; Resumen ejecutivo de tendencias", styles["Title2"]))
        elements.append(Spacer(1, 8))
        meta_parts = [
            f"<b>Período:</b> {summary.get('period', 'N/A')}",
            f"<b>Tema:</b> {summary.get('topic', 'N/A')}",
            f"<b>País:</b> {summary.get('pais', 'N/A')}",
            f"<b>Total de señales:</b> {summary.get('total_questions', 0)}",
            f"<b>Fuente top:</b> {summary.get('top_source', 'N/A')}",
            f"<b>Categoría top:</b> {summary.get('top_category', 'N/A')}",
        ]
        if summary.get("value_completeness"):
            meta_parts.append(f"<b>Calidad del análisis:</b> {summary['value_completeness']}% con datos accionables")
        if summary.get("top_brands"):
            brands = " &middot; ".join(summary["top_brands"])
            meta_parts.append(f"<b>Marcas mencionadas:</b> {brands}")
        if summary.get("has_critical_signal"):
            meta_parts.append('<font color="#EF4444"><b>⚠ Señal crítica detectada</b></font>')
        elements.append(_p("<br/>".join(meta_parts), styles["SubTitle"]))
        elements.append(Spacer(1, 12))

    def _critical_banner(self, elements, styles, summary):
        if summary.get("has_critical_signal"):
            data = [
                [_p('<b><font color="#EF4444">⚠ Señal crítica detectada</font></b>', styles["Body2"])],
                [_p("La combinación de tendencia creciente y riesgo de fuga requiere priorización inmediata.", styles["BodySmall"])],
            ]
            t = Table(data, colWidths=[460])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), HexColor("#FEF2F2")),
                ("BOX", (0, 0), (-1, -1), 1, RED),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ]))
            elements.append(t)
            elements.append(Spacer(1, 8))

    def _causal_context(self, elements, styles, summary):
        insight = summary.get("value_insight", {})
        cause = insight.get("cause_summary", "")
        if cause:
            data = [
                [_p('<font color="#64748B">CONTEXTO CAUSAL</font>', styles["BodySmall"])],
                [_p(cause, styles["Body2"])],
            ]
            t = Table(data, colWidths=[460])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), HexColor("#F5F3FF")),
                ("LINEBEFORE", (0, 0), (-1, -1), 3, PURPLE),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ]))
            elements.append(t)
            elements.append(Spacer(1, 8))

    def _executive_cards(self, elements, styles, summary):
        cards = [
            ("Hallazgo principal", summary.get("main_finding", "")),
            ("Oportunidad", summary.get("opportunity", "")),
            ("Riesgos o fricciones", summary.get("risks", "")),
            ("Recomendación", summary.get("recommendation", "")),
        ]
        for label, text in cards:
            data = [
                [_p(label, styles["CardTitle"])],
                [_p(text, styles["Body2"])],
            ]
            t = Table(data, colWidths=[460])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GRAY),
                ("BOX", (0, 0), (-1, -1), 0.5, HexColor("#E5E7EB")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("LINEBELOW", (0, 0), (-1, 0), 1, BLUE),
            ]))
            elements.append(t)
            elements.append(Spacer(1, 8))

    def _exec_summary_detail(self, elements, styles, summary):
        exec_data = summary.get("exec", {})
        if any(exec_data.get(k) for k in ["que_cambio", "por_que_importa", "que_haria_hoy"]):
            elements.append(_p("Resumen ejecutivo detallado", styles["SectionTitle"]))
            items = [
                ("QUÉ CAMBIÓ", exec_data.get("que_cambio", ""), BLUE),
                ("POR QUÉ IMPORTA", exec_data.get("por_que_importa", ""), PURPLE),
                ("QUÉ HARÍA HOY", exec_data.get("que_haria_hoy", ""), GREEN),
            ]
            for label, text, color in items:
                if text:
                    data = [
                        [_p(f'<font color="{GRAY_HEX}">{label}</font>', styles["BodySmall"])],
                        [_p(text, styles["Body2"])],
                    ]
                    t = Table(data, colWidths=[460])
                    t.setStyle(TableStyle([
                        ("LINEBEFORE", (0, 0), (-1, -1), 3, color),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ("LEFTPADDING", (0, 0), (-1, -1), 10),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ]))
                    elements.append(t)
                    elements.append(Spacer(1, 6))

    def _categories_sources_tables(self, elements, styles, summary):
        categories = summary.get("categories", {})
        sources = summary.get("sources", {})
        if categories:
            elements.append(_p("Distribución de señales", styles["SectionTitle"]))
            data = [[_p("<b>Categoría</b>", styles["TableHeader"]), _p("<b>Señales</b>", styles["TableHeader"])]]
            for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
                data.append([_p(cat, styles["TableCellSmall"]), _p(str(count), styles["TableCellSmall"])])
            t = Table(data, colWidths=[360, 100])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), DARK),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#E5E7EB")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]))
            elements.append(t)
            elements.append(Spacer(1, 6))
        if sources:
            data = [[_p("<b>Fuente</b>", styles["TableHeader"]), _p("<b>Señales</b>", styles["TableHeader"])]]
            for src, count in sorted(sources.items(), key=lambda x: x[1], reverse=True):
                data.append([_p(src, styles["TableCellSmall"]), _p(str(count), styles["TableCellSmall"])])
            t = Table(data, colWidths=[360, 100])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), DARK),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#E5E7EB")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]))
            elements.append(t)
            elements.append(Spacer(1, 8))

    def _rising_questions(self, elements, styles, summary):
        rising = summary.get("rising_questions", [])
        if rising:
            elements.append(_p("Preguntas en tendencia <font size=9> (creciendo en frecuencia)</font>", styles["SectionTitle"]))
            elements.append(_p("<b>Crecimiento %</b> &mdash; aumento en frecuencia vs el histórico de 30 días atrás.", styles["BodySmall"]))
            elements.append(Spacer(1, 4))
            for rq in rising:
                growth = rq.get("crecimiento", "")
                question = rq.get("question", "")[:120]
                data = [
                    [_p(question, styles["Body2"])],
                    [_p(f'<font color="{GREEN_HEX}">{growth}</font>', styles["BodySmall"])],
                ]
                t = Table(data, colWidths=[460])
                t.setStyle(TableStyle([
                    ("BOX", (0, 0), (-1, -1), 0.5, HexColor("#E5E7EB")),
                    ("LINEBEFORE", (0, 0), (-1, -1), 3, GREEN),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ]))
                elements.append(t)
                elements.append(Spacer(1, 4))

    def _cross_source(self, elements, styles, summary):
        cross = summary.get("cross_items", [])
        if cross:
            elements.append(_p("Preguntas que aparecen en múltiples fuentes", styles["SectionTitle"]))
            for item in cross:
                q_text = item.get("question", "")[:100]
                srcs = " &middot; ".join(item.get("sources", []))
                data = [
                    [_p(q_text, styles["Body2"])],
                    [_p(f'<font color="{GRAY_HEX}">Fuentes: {srcs}</font>', styles["BodySmall"])],
                ]
                t = Table(data, colWidths=[460])
                t.setStyle(TableStyle([
                    ("BOX", (0, 0), (-1, -1), 0.5, HexColor("#E5E7EB")),
                    ("LINEBEFORE", (0, 0), (-1, -1), 3, PURPLE),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ]))
                elements.append(t)
                elements.append(Spacer(1, 4))

    def _grouped_questions(self, elements, styles, summary):
        grouped = summary.get("grouped_questions", {})
        if grouped:
            elements.append(_p("Preguntas destacadas por categoría", styles["SectionTitle"]))
            for cat, items in grouped.items():
                cat_data = [[_p(f"<b>{cat}</b>  ({len(items)})", styles["CardTitle"])]]
                for item in items:
                    q_text = item.get("question", "")
                    conf = f'{item.get("confidence", 0) * 100:.0f}%'
                    src = item.get("source_type", "")
                    trend = item.get("trend", "stable")
                    churn_risk = item.get("churn", {}).get("nivel", "")
                    action_text = item.get("action", {}).get("texto", "")
                    impact = item.get("action", {}).get("impact", "")
                    team = item.get("action", {}).get("team", "")
                    responses = item.get("respuestas", {})
                    resumen = responses.get("resumen", "") if responses.get("hay_respuestas") else ""

                    line_parts = [f'<font color="{GRAY_HEX}">{src}</font> &middot; Conf: {conf}']
                    if churn_risk == "alto":
                        line_parts.append(f'<font color="{RED_HEX}">[fuga alto]</font>')
                    meta_line = " &middot; ".join(line_parts)

                    detail_parts = []
                    if action_text:
                        detail_parts.append(f'→ {action_text}')
                    if impact:
                        detail_parts.append(f'<font color="{GRAY_HEX}">Impacto: {impact}</font>')
                    if team:
                        detail_parts.append(f'<font color="{GRAY_HEX}">Equipo: {team}</font>')
                    detail_line = " | ".join(detail_parts)

                    entry = f"<b>{q_text}</b><br/>{meta_line}"
                    if detail_line:
                        entry += f"<br/>{detail_line}"
                    if resumen:
                        entry += f"<br/><font color='{GRAY_HEX}'>↳ {resumen}</font>"

                    trend_colors = {"rising": GREEN, "declining": RED, "stable": GRAY}
                    border_c = trend_colors.get(trend, GRAY)

                    cat_data.append([_p(entry, styles["TableCellSmall"])])
                    inner = Table(cat_data[-1:], colWidths=[440])
                    inner.setStyle(TableStyle([
                        ("LINEBEFORE", (0, 0), (-1, -1), 3, border_c),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ]))
                    cat_data[-1] = [inner]

                t = Table(cat_data, colWidths=[460])
                t.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GRAY),
                    ("BOX", (0, 0), (-1, -1), 0.5, HexColor("#E5E7EB")),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("LINEBELOW", (0, 0), (-1, 0), 1, BLUE),
                ]))
                elements.append(t)
                elements.append(Spacer(1, 6))

    def _churn_questions(self, elements, styles, summary):
        churn = summary.get("churn_questions", [])
        if churn:
            elements.append(_p("Riesgo de fuga", styles["SectionTitle"]))
            elements.append(_p("Señales que pueden indicar pérdida de clientes. Priorizar atención.", styles["BodySmall"]))
            elements.append(Spacer(1, 4))
            for item in churn:
                q_text = item.get("question", "")
                riesgo = item.get("churn", {}).get("riesgo", 0)
                nivel = item.get("churn", {}).get("nivel", "")
                src = item.get("source_type", "")
                conf = f'{item.get("confidence", 0) * 100:.0f}%'
                action_text = item.get("action", {}).get("texto", "")
                impact = item.get("action", {}).get("impact", "")
                detail = f"<b>{q_text}</b><br/>"
                detail += f'<font color="{RED_HEX}">Riesgo: {nivel} ({riesgo}/5)</font> &middot; {src} &middot; Conf: {conf}'
                if action_text:
                    detail += f"<br/>→ {action_text}"
                if impact:
                    detail += f' <font color="{GRAY_HEX}">({impact})</font>'
                data = [[_p(detail, styles["TableCellSmall"])]]
                t = Table(data, colWidths=[460])
                t.setStyle(TableStyle([
                    ("BOX", (0, 0), (-1, -1), 0.5, HexColor("#E5E7EB")),
                    ("LINEBEFORE", (0, 0), (-1, -1), 4, RED),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ]))
                elements.append(t)
                elements.append(Spacer(1, 4))

    def _opportunities_table(self, elements, styles, summary):
        oportunidades = summary.get("oportunidades", [])
        if oportunidades:
            elements.append(_p("Oportunidades priorizadas", styles["SectionTitle"]))
            header_row = [
                _p("Categoría", styles["TableHeader"]),
                _p("Señales", styles["TableHeader"]),
                _p("Score", styles["TableHeader"]),
                _p("Impacto en negocio", styles["TableHeader"]),
            ]
            opp_data = [header_row]
            for o in oportunidades[:8]:
                nivel = o.get("nivel", 0)
                score_str = str(o.get("score", ""))
                if nivel >= 3:
                    score_str = f'<font color="{RED_HEX}">{score_str}</font>'
                elif nivel == 2:
                    score_str = f'<font color="{AMBER_HEX}">{score_str}</font>'
                opp_data.append([
                    _p(o.get("categoria", ""), styles["TableCell"]),
                    _p(f"{o.get('señales', 0)} ({o.get('porcentaje', '')})", styles["TableCell"]),
                    _p(score_str, styles["TableCell"]),
                    _p(o.get("impacto_negocio", ""), styles["TableCellSmall"]),
                ])
            opp_table = Table(opp_data, colWidths=[90, 65, 45, 260])
            opp_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), DARK),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#E5E7EB")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]))
            elements.append(opp_table)
            elements.append(Spacer(1, 8))

    def _alerts_section(self, elements, styles, summary):
        alerts = summary.get("alerts", [])
        if alerts:
            elements.append(_p("Alertas accionables", styles["SectionTitle"]))
            for a in alerts:
                level = a.get("level", "")
                window = a.get("window", "")
                trend = a.get("trend", "")
                question = a.get("question", "")
                recommendation = a.get("recommendation", "")
                kpis = a.get("kpis_affected", [])
                source = a.get("source", "")
                kpi_text = ", ".join(kpis)

                level_colors = {"Crítica": RED, "Alta": AMBER, "Monitoreo activo": BLUE}
                lc = level_colors.get(level, GRAY)
                level_hex = {"Crítica": RED_HEX, "Alta": AMBER_HEX, "Monitoreo activo": BLUE_HEX}.get(level, GRAY_HEX)

                lines = [f'<font color="{level_hex}"><b>{level}</b></font> &middot; {window} &middot; {trend}']
                if question:
                    lines.append(f'<i>"{question[:120]}"</i>')
                lines.append(f"→ {recommendation}")
                meta_parts = []
                if source:
                    meta_parts.append(f"Fuente: {source}")
                meta_parts.append(f"KPIs: {kpi_text}")
                lines.append(f'<font color="{GRAY_HEX}">{" | ".join(meta_parts)}</font>')

                content = "<br/>".join(lines)
                data = [[_p(content, styles["TableCellSmall"])]]
                t = Table(data, colWidths=[460])
                t.setStyle(TableStyle([
                    ("BOX", (0, 0), (-1, -1), 0.5, HexColor("#E5E7EB")),
                    ("LINEBEFORE", (0, 0), (-1, -1), 3, lc),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ]))
                elements.append(t)
                elements.append(Spacer(1, 4))

    def _top_questions_table(self, elements, styles, summary):
        top_items = summary.get("top_items", [])
        if top_items:
            elements.append(_p("Preguntas destacadas", styles["SectionTitle"]))
            header_row = [
                _p("Pregunta", styles["TableHeader"]),
                _p("Categoría", styles["TableHeader"]),
                _p("Fuente", styles["TableHeader"]),
                _p("Conf.", styles["TableHeader"]),
            ]
            q_data = [header_row]
            for item in top_items[:15]:
                q_data.append([
                    _p(item.get("question", "")[:80], styles["TableCell"]),
                    _p(item.get("category", ""), styles["TableCell"]),
                    _p(item.get("source_type", ""), styles["TableCell"]),
                    _p(f"{item.get('confidence', 0):.2f}", styles["TableCell"]),
                ])
            q_table = Table(q_data, colWidths=[200, 85, 85, 90])
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
            elements.append(Spacer(1, 8))

    def _source_annex(self, elements, styles, summary):
        anexo = summary.get("anexo_fuentes", [])
        if anexo:
            elements.append(_p("Anexo de fuentes", styles["SectionTitle"]))
            for f in anexo:
                nombre = f.get("nombre", "")
                confiabilidad = f.get("confiabilidad", "Media")
                senales = f.get("señales", 0)

                conf_hex_map = {"Alta": GREEN_HEX, "Media": AMBER_HEX, "Baja": RED_HEX}
                cc_hex = conf_hex_map.get(confiabilidad, GRAY_HEX)

                header = f"<b>{nombre}</b> &nbsp; <font color='{cc_hex}'>{confiabilidad}</font> &nbsp; <font color='{GRAY_HEX}'>{senales} señal{'es' if senales != 1 else ''}</font>"
                data_rows = [[_p(header, styles["Body2"])]]
                for pq in f.get("preguntas", [])[:8]:
                    data_rows.append([_p(pq.get("question", ""), styles["TableCellSmall"])])

                t = Table(data_rows, colWidths=[460])
                t.setStyle(TableStyle([
                    ("BOX", (0, 0), (-1, -1), 0.5, HexColor("#E5E7EB")),
                    ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GRAY),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("LINEBELOW", (0, 0), (-1, 0), 1, HexColor("#E5E7EB")),
                ]))
                elements.append(t)
                elements.append(Spacer(1, 6))

            legend = "<b>Alta:</b> conversación orgánica no moderada &middot; <b>Media:</b> contenido editado o algoritmo &middot; <b>Referencial:</b> curada por el negocio"
            elements.append(_p(legend, styles["BodySmall"]))

    def _footer(self, elements, styles):
        elements.append(Spacer(1, 20))
        elements.append(Table([[" "]], colWidths=[460], style=TableStyle([
            ("LINEABOVE", (0, 0), (-1, -1), 0.5, HexColor("#E5E7EB")),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ])))
        elements.append(Spacer(1, 8))
        elements.append(_p("&copy; 2026 SIKURI &mdash; Generado por TrendQA", styles["Footer"]))

    def export_summary(self, summary, output_path):
        if isinstance(output_path, (str, Path)):
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            dest = str(output_path)
        else:
            dest = output_path

        doc = SimpleDocTemplate(
            dest, pagesize=A4,
            topMargin=2*cm, bottomMargin=2*cm,
            leftMargin=2*cm, rightMargin=2*cm,
        )

        styles = getSampleStyleSheet()
        styles = self._make_styles(styles)

        elements = []
        self._header_block(elements, styles)
        self._meta_section(elements, styles, summary)
        self._critical_banner(elements, styles, summary)
        self._causal_context(elements, styles, summary)
        self._executive_cards(elements, styles, summary)
        self._exec_summary_detail(elements, styles, summary)
        self._categories_sources_tables(elements, styles, summary)
        self._rising_questions(elements, styles, summary)
        self._cross_source(elements, styles, summary)
        self._grouped_questions(elements, styles, summary)
        self._churn_questions(elements, styles, summary)
        self._opportunities_table(elements, styles, summary)
        self._alerts_section(elements, styles, summary)
        self._top_questions_table(elements, styles, summary)
        self._source_annex(elements, styles, summary)
        self._footer(elements, styles)

        doc.build(elements)
        return str(output_path) if isinstance(output_path, (str, Path)) else output_path
