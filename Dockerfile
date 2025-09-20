# syntax=docker/dockerfile:1

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements (support both poetry and requirements.txt)
COPY pyproject.toml poetry.lock* ./ 
COPY requirements.txt ./ 

RUN set -eux; \
    if [ -f requirements.txt ]; then \
      pip install -r requirements.txt; \
    elif [ -f pyproject.toml ]; then \
      pip install poetry && poetry install --no-root --only main; \
    fi

# Copy source code
COPY . .

# Environment
ENV HOST=0.0.0.0 \
    PYTHONPATH=/app

# Expose the runtime port (Cloud Run provides $PORT)
EXPOSE 8080

# Use Cloud Run's $PORT dynamically
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port $PORT"]
