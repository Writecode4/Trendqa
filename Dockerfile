# Fase build: instalar dependencias
FROM python:3.11-alpine AS build

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

COPY . .


# Fase runtime: imagen final
FROM python:3.11-alpine AS runtime

WORKDIR /app

# Crear el usuario antes de usar --chown
RUN adduser --disabled-password --gecos '' app

# Ahora sí puedes usar app:app
COPY --from=build --chown=app:app /root/.local /root/.local
COPY --chown=app:app . .

# PATH y variables de entorno
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/root/.local/bin:$PATH"

USER app

EXPOSE 5000

CMD ["python", "main.py"]
