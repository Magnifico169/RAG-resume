FROM python:3.11-slim

# Prevents Python from writing .pyc files and enables unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps (optional): install curl for healthchecks/debug
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    gcc \
    libffi-dev \
    libssl-dev \
    python3-dev \
  && rm -rf /var/lib/apt/lists/*

# Copy requirements separately for better cache
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r /app/requirements.txt

# Copy app code
COPY . /app

# Create data directory and ensure it exists in container
RUN mkdir -p /app/data

# Default environment
ENV HOST=0.0.0.0 \
    PORT=8080 \
    DEBUG=True

EXPOSE 8080

CMD ["python3", "main.py"]

