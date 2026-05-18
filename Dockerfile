# ---------- Etapa 1: Builder ----------
FROM python:3.11-alpine AS builder

WORKDIR /app

# Copiar solo requirements.txt primero (para aprovechar caché)
COPY requirements.txt .

# Instalar dependencias en un directorio temporal (--prefix o --target)
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------- Etapa 2: Final ----------
FROM python:3.11-alpine

WORKDIR /app

# Copiar las dependencias instaladas desde la etapa builder
COPY --from=builder /install /usr/local

# Copiar el resto del código de la aplicación
COPY . .

# Variables de entorno (igual que en el original)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 5000

CMD ["python", "main.py"]
