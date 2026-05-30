import os
import io
import time
import atexit
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

    # Túnel SSH para base de datos remota
    from sshtunnel import SSHTunnelForwarder
    import paramiko

    ENV = os.getenv('FLASK_ENV', 'development')
    tunnel = None

    if ENV == 'production':
        private_key_str = os.getenv('SSH_PRIVATE_KEY').replace('\\n', '\n')
        key_file = io.StringIO(private_key_str)
        for KeyClass in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
            try:
                key_file.seek(0)
                private_key = KeyClass.from_private_key(key_file)
                break
            except paramiko.SSHException:
                continue
        else:
            raise paramiko.SSHException("No se pudo cargar la clave SSH privada")
        tunnel = SSHTunnelForwarder(
            (os.getenv('SSH_HOST'), int(os.getenv('SSH_PORT'))),
            ssh_username=os.getenv('SSH_USER'),
            ssh_pkey=private_key,
            remote_bind_address=('127.0.0.1', 3306)
        )
        tunnel.start()
    else:
        tunnel = SSHTunnelForwarder(
            (os.getenv('SSH_HOST'), int(os.getenv('SSH_PORT'))),
            ssh_username=os.getenv('SSH_USER'),
            ssh_pkey=paramiko.RSAKey.from_private_key_file(os.getenv('SSH_KEY_PATH')),
            remote_bind_address=('127.0.0.1', 3306)
        )
        tunnel.start()

    os.environ['DB_PORT'] = str(tunnel.local_bind_port)
    app.tunnel = tunnel

    def close_tunnel():
        if tunnel:
            tunnel.stop()

    atexit.register(close_tunnel)

    # Inicializar extensiones
    cache = Cache(app)
    Compress(app)

    # Registrar blueprint existente
    from trendqa.dashboard import dashboard_bp
    app.register_blueprint(dashboard_bp)

    from trendqa.contact import contact_bp
    app.register_blueprint(contact_bp)

    from flask_cors import CORS
    CORS(app, resources={r"/api/*": {"origins": "*"}})


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
    
