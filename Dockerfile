FROM python:3.11-alpine AS build

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt gunicorn

COPY . .

FROM python:3.11-alpine AS runtime

WORKDIR /app

RUN adduser --disabled-password --gecos '' app

COPY --from=build --chown=app:app /root/.local /root/.local
COPY --chown=app:app . .

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/root/.local/bin:$PATH"

USER app

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "main:app"]
