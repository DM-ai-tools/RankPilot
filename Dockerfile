# RankPilot API — build context must be the repository root (monorepo).
# Stops Railpack/Metal from failing on an empty repo root with no pyproject/package.json.
FROM python:3.12-slim-bookworm

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# postgresql-client provides `psql` so `python scripts/apply_migrations.py` works in Railway Shell.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml /app/pyproject.toml
COPY backend/app /app/app
COPY backend/scripts /app/scripts
COPY infra/sql /app/infra/sql

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
