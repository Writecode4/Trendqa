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
    import threading

    ENV = os.getenv('FLASK_ENV', 'development')
    _tunnel = None
    _tunnel_lock = threading.Lock()
    _tunnel_stop_event = threading.Event()

    ssh_pkey = os.getenv('SSH_PRIVATE_KEY')
    if ssh_pkey:
        ssh_pkey = ssh_pkey.replace('\\n', '\n')
        key_file = io.StringIO(ssh_pkey)
        for KeyClass in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
            try:
                key_file.seek(0)
                ssh_pkey = KeyClass.from_private_key(key_file)
                break
            except paramiko.SSHException:
                continue
        else:
            raise paramiko.SSHException("No se pudo cargar la clave SSH privada")
    else:
        ssh_pkey = paramiko.RSAKey.from_private_key_file(os.getenv('SSH_KEY_PATH'))

    def _start_tunnel():
        global _tunnel
        t = SSHTunnelForwarder(
            (os.getenv('SSH_HOST'), int(os.getenv('SSH_PORT'))),
            ssh_username=os.getenv('SSH_USER'),
            ssh_pkey=ssh_pkey,
            remote_bind_address=('127.0.0.1', 3306),
        )
        t.start()
        if t.transport is not None:
            t.transport.set_keepalive(30)
        _tunnel = t
        os.environ['DB_PORT'] = str(_tunnel.local_bind_port)
        app.logger.info("Túnel SSH iniciado correctamente")
        return t

    def _ensure_tunnel():
        with _tunnel_lock:
            if _tunnel is None or not _tunnel.is_active:
                app.logger.warning("Túnel SSH caído — reconectando...")
                try:
                    if _tunnel:
                        _tunnel.stop()
                except Exception:
                    pass
                _start_tunnel()

    def _tunnel_watchdog():
        while not _tunnel_stop_event.is_set():
            _tunnel_stop_event.wait(60)
            try:
                _ensure_tunnel()
            except Exception as e:
                app.logger.error(f"Watchdog túnel falló: {e}")

    _start_tunnel()
    watchdog = threading.Thread(target=_tunnel_watchdog, daemon=True)
    watchdog.start()

    app.tunnel_provider = _ensure_tunnel

    def close_tunnel():
        _tunnel_stop_event.set()
        with _tunnel_lock:
            if _tunnel:
                try:
                    _tunnel.stop()
                except Exception:
                    pass
                _tunnel = None

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
    
