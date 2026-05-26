from pathlib import Path
from dotenv import load_dotenv
from flask import Flask
from trendqa.dashboard import dashboard_bp

def create_app():
    base = Path(__file__).resolve().parent.parent
    load_dotenv(base / ".env")
    app = Flask(__name__,
                template_folder=str(base / "templates"),
                static_folder=str(base / "static"),import os
import time
import sqlite3
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

    # Optimización SQLite (se ejecuta al crear la app)
    try:
        db_path = os.getenv('DATABASE_PATH', str(base / 'trendqa.db'))
        conn = sqlite3.connect(db_path, timeout=5)
        conn.execute('PRAGMA journal_mode=WAL;')
        conn.execute('PRAGMA synchronous=NORMAL;')
        conn.execute('PRAGMA cache_size=-8000;')   # ~8MB cache en RAM
        conn.execute('PRAGMA temp_store=MEMORY;')
        conn.execute('PRAGMA busy_timeout=3000;')  # Espera 3s si está bloqueada
        conn.close()
        app.logger.info("✅ SQLite optimizado (WAL + cache low-memory)")
    except Exception as e:
        app.logger.warning(f"⚠️ Error optimizando SQLite: {e}")

    # Crear directorio de caché si no existe
    os.makedirs('/tmp/flask_cache', exist_ok=True)

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
                static_url_path="/static")
    app.register_blueprint(dashboard_bp)
    return app
