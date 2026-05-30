import io
import tempfile
from pathlib import Path
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, send_file
from trendqa.db import Database
from trendqa.dashboard import get_cached_summary
from trendqa.services.pdf_export import PDFExporter


contact_bp = Blueprint("contact", __name__)


@contact_bp.route("/contacto", methods=["GET", "POST"])
def contacto():
    if request.method == "POST":
        db = Database()
        db.save_contact(
            nombre_completo=request.form.get("nombre_completo"),
            email_corporativo=request.form.get("email_corporativo"),
            telefono=request.form.get("telefono"),
            industria=request.form.get("industria"),
            mensaje=request.form.get("mensaje"),
        )

        topic = request.form.get("topic") or request.args.get("topic", "")
        pais = request.form.get("pais") or request.args.get("pais", "paraguay")
        summary = get_cached_summary(topic, pais)

        if not summary:
            return render_template("contacto.html", ok="1", no_pdf=True)

        base = Path(__file__).resolve().parent.parent
        exporter = PDFExporter(base_dir=str(base))
        buf = io.BytesIO()
        exporter.export_summary(summary, buf)
        buf.seek(0)
        return send_file(
            buf,
            mimetype="application/pdf",
            as_attachment=False,
            download_name=f"trendqa_{topic}.pdf",
        )

    ok = request.args.get("ok")
    topic = request.args.get("topic", "")
    pais = request.args.get("pais", "paraguay")
    return render_template("contacto.html", ok=ok, topic=topic, pais=pais)


@contact_bp.route("/api/contact", methods=["POST", "OPTIONS"])
def api_contact():
    if request.method == "OPTIONS":
        return jsonify({"ok": True})

    data = request.get_json() or request.form
    db = Database()
    db.save_contact(
        nombre_completo=data.get("nombre_completo"),
        email_corporativo=data.get("email_corporativo"),
        telefono=data.get("telefono"),
        industria=data.get("industria"),
        mensaje=data.get("mensaje"),
    )
    return jsonify({"ok": True, "message": "Contacto registrado"})


@contact_bp.route("/api/contacts", methods=["GET"])
def api_contacts():
    db = Database()
    contacts = db.get_contacts()
    return jsonify(contacts)
