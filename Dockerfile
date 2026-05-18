# Fase build: instalar dependencias como root (normal en Docker)
FROM python:3.11-alpine AS build

WORKDIR /app

COPY requirements.txt .
# --user evita llenar /usr/local y manda scripts a /root/.local/bin
RUN pip install --no-cache-dir --user -r requirements.txt

COPY . .


# Fase runtime: imagen final y usuario no root
FROM python:3.11-alpine AS runtime

WORKDIR /app

# Copia solo deps desde --user
COPY --from=build --chown=app:app /root/.local /root/.local

# Copia solo el código que necesitas
COPY --chown=app:app . .

# Agrega /root/.local/bin al PATH
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/root/.local/bin:$PATH"

# Crear usuario no root y usarlo
RUN adduser --disabled-password --gecos '' app
USER app

EXPOSE 5000

CMD ["python", "main.py"]
