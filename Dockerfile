# Etapa 1: compilar dependencias
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    libxml2-dev \
    libxslt-dev \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Etapa 2: imagen final liviana
FROM python:3.11-slim

WORKDIR /app

# Solo las librerías de runtime necesarias (sin gcc ni dev headers)
RUN apt-get update && apt-get install -y \
    libxml2 \
    libxslt1.1 \
    libffi8 \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

# Copiar paquetes Python instalados desde el builder
COPY --from=builder /install /usr/local

# Copiar el proyecto
COPY . .

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 5000

CMD ["python", "main.py"]
