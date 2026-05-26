import os
import sys
from pathlib import Path

# Asegura que la carpeta raíz del proyecto esté en el PYTHONPATH
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from trendqa.app import create_app

# Crear la aplicación Flask
app = create_app()

# Variable estándar requerida por servidores WSGI (Gunicorn, uWSGI, etc.)
application = app

# Solo se ejecuta si llamas directamente: python wsgi.py
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
