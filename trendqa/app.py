from pathlib import Path
from dotenv import load_dotenv
from flask import Flask
from trendqa.dashboard import dashboard_bp

def create_app():
    load_dotenv()
    base = Path(__file__).resolve().parent.parent
    app = Flask(__name__,
                template_folder=str(base / "templates"),
                static_folder=str(base / "static"),
                static_url_path="/static")
    app.register_blueprint(dashboard_bp)
    return app