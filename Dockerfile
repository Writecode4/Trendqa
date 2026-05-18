# Fase build: instala dependencias y copia el código
FROM python:3.11-alpine AS build

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY . .


# Fase runtime: imagen final minimalista
FROM python:3.11-alpine AS runtime

WORKDIR /app

# Copia solo /root/.local desde el user install de pip
COPY --from=build --chown=app:app /root/.local /root/.local

# Copia solo código fuente necesario (evita .git, __pycache__, etc.)
COPY --chown=app:app . .

# Variables de entorno
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/root/.local/bin:$PATH

# Crear usuario no root
RUN adduser --disabled-password --gecos '' app
USER app

EXPOSE 5000

CMD ["python", "main.py"]
