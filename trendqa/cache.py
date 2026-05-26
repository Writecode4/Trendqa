import os
import time
import json
import hashlib
from pathlib import Path
from functools import wraps

# Directorio compartido con Flask-Caching
CACHE_DIR = Path("/tmp/flask_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_TTL = 900  # 15 minutos

def _make_key(prefix, *args, **kwargs):
    try:
        from flask import request
        # Si estamos en una petición web, usar ruta + parámetros para clave única
        raw = f"{prefix}:{request.path}:{request.query_string.decode()}"
    except Exception:
        # Fallback para scripts o pruebas fuera de Flask
        raw = f"{prefix}:{args}:{sorted(kwargs.items())}"
    return hashlib.md5(raw.encode()).hexdigest()

def get_cached(key, ttl=DEFAULT_TTL):
    """Lee el caché si existe y no está expirado."""
    cache_file = CACHE_DIR / f"{key}.json"
    if not cache_file.exists():
        return None
    try:
        data = json.loads(cache_file.read_text())
        if time.time() - data["ts"] < ttl:
            return data["result"]
        cache_file.unlink(missing_ok=True)  # Expirado
    except Exception:
        cache_file.unlink(missing_ok=True)  # Corrupto
    return None

def set_cached(key, result, ttl=DEFAULT_TTL):
    """Guarda el resultado en disco."""
    try:
        cache_file = CACHE_DIR / f"{key}.json"
        cache_file.write_text(json.dumps({"ts": time.time(), "result": result}, default=str))
    except Exception:
        pass  # Fallo silencioso: nunca romper la app por caché

def cleanup_cache(max_age=3600):
    """Elimina archivos de caché viejos para no llenar /tmp."""
    now = time.time()
    if not CACHE_DIR.exists():
        return
    for f in CACHE_DIR.iterdir():
        try:
            if f.is_file() and (now - f.stat().st_mtime) > max_age:
                f.unlink()
        except Exception:
            pass

def cached(ttl=DEFAULT_TTL, key_prefix=""):
    """Decorador para envolver funciones y cachear su resultado en disco."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = _make_key(key_prefix, *args, **kwargs)
            result = get_cached(key, ttl)
            if result is not None:
                return result
            result = func(*args, **kwargs)
            set_cached(key, result, ttl)
            return result
        return wrapper
    return decorator
