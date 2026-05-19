from pathlib import Path
from dotenv import load_dotenv
from flask import Flask
from trendqa.dashboard import dashboard_bp

def create_app():
    base = Path(__file__).resolve().parent.parent
    load_dotenv(base / ".env")
    app = Flask(__name__,
                template_folder=str(base / "templates"),
                static_folder=str(base / "static"),
                static_url_path="/static")
    app.register_blueprint(dashboard_bp)
    return app
