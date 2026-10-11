# Multi-stage Dockerfile for the FastAPI Emergency Coordination backend
FROM python:3.11-slim AS builder

WORKDIR /app

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt


# Final runtime image (non-root, no tests or build tools)
FROM python:3.11-slim AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite:////app/data/blood_donation.db

RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app

COPY --from=builder /install /usr/local

COPY app /app/app
COPY .env.example /app/.env.example

# SQLite lives here (mounted as a volume in docker-compose.yml)
RUN mkdir -p /app/data && chown -R app:app /app/data

USER app

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
