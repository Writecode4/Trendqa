import os
from pathlib import Path
from flask import Flask
from dotenv import load_dotenv

# ✅ Imports de blueprints
from trendqa.dashboard import dashboard_bp

BASE = Path(__file__).resolve().parent.parent
load_dotenv(BASE / ".env")

def create_app():
    app = Flask(
        __name__,
        static_folder=str(BASE / "static"),  # ✅ Coma correcta, fin de argumento
        template_folder=str(BASE / "templates")
    )
    
    # ✅ Configuración básica
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-fallback-key")
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB max upload
    
    # ✅ Registrar blueprints
    app.register_blueprint(dashboard_bp)
    
    # ✅ Health check mínimo (para monitoreo)
    @app.route("/health")
    def health():
        return {"status": "ok", "service": "trendqa"}, 200
    
    # ✅ Error handlers básicos
    @app.errorhandler(404)
    def not_found(e):
        return {"error": "Not found"}, 404
    
    @app.errorhandler(500)
    def server_error(e):
        return {"error": "Internal server error"}, 500
    
    return app

# ✅ Entry point para Gunicorn / Spaceship
if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=False)
