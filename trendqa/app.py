import os
import time
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, g, request
from flask_caching import Cache
from flask_compress import Compress

def create_app():
    base = Path(__file__).resolve().parent.parent
    load_dotenv(base / ".env")

    app = Flask(__name__,
                template_folder=str(base / "templates"),
                static_folder=str(base / "static"),
                static_url_path="/static")

    # Configuración de caché y compresión
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-change-me')
    app.config['CACHE_TYPE'] = 'FileSystemCache'
    app.config['CACHE_DIR'] = '/tmp/flask_cache'
    app.config['CACHE_DEFAULT_TIMEOUT'] = 900  # 15 minutos
    app.config['COMPRESS_REGISTER'] = True

    # Inicializar extensiones
    cache = Cache(app)
    Compress(app)

    # Registrar blueprint existente
    from trendqa.dashboard import dashboard_bp
    app.register_blueprint(dashboard_bp)


    # Middleware para medir tiempo de respuesta
    @app.before_request
    def _start_timer():
        g._start_time = time.time()

    @app.after_request
    def _log_duration(response):
        duration = time.time() - g.get('_start_time', time.time())
        if duration > 5:
            app.logger.warning(f"⚠️ SLOW: {request.method} {request.path} → {duration:.2f}s")
        response.headers['X-Response-Time'] = f"{duration:.3f}s"
        return response

    # Hacer cache accesible globalmente
    app.cache = cache

    return app
    
