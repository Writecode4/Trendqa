# Base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies required by some packages (xhtml2pdf, lxml, etc.)
RUN apt-get update && apt-get install -y \
    gcc \
    libxml2-dev \
    libxslt-dev \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project
COPY . .

# Load environment variables from .env (if present at runtime)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Expose Flask default port
EXPOSE 5000

# Run the app
CMD ["python", "main.py"]
