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
COPY backend/pyproject.toml backend/poetry.lock* ./
COPY backend/requirements.txt ./

RUN set -eux; \
    if [ -f requirements.txt ]; then \
      pip install -r requirements.txt; \
    elif [ -f pyproject.toml ]; then \
      pip install poetry && poetry install --no-root --only main; \
    fi

# Copy source
COPY backend/ ./

# Environment
ENV PORT=8000 \
    HOST=0.0.0.0 \
    PYTHONPATH=/app

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "${PORT}"]

FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend

ENV PYTHONPATH=/app/backend

EXPOSE 8000

CMD ["python", "backend/run.py"]


