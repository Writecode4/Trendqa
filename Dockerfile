FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    libxml2-dev \
    libxslt-dev \
    libffi-dev \
    libssl-dev \
    && pip install --no-cache-dir lxml xhtml2pdf \
    && apt-get remove -y gcc libxml2-dev libxslt-dev libffi-dev libssl-dev \
    && apt-get autoremove -y \
    && apt-get install -y libxml2 libxslt1.1 libffi8 libssl3 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 5000

CMD ["python", "main.py"]