# ============================================================
# DIGITRANS-CM – CRM API Dockerfile
# Build multi-stage pour image minimale en production
# ============================================================

# --- Stage 1: Builder ---
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt


# --- Stage 2: Runtime ---
FROM python:3.12-slim AS runtime

# Utilisateur non-root (sécurité)
RUN groupadd --gid 1001 appgroup \
    && useradd --uid 1001 --gid appgroup --no-create-home appuser

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

# Copier les dépendances depuis le builder
COPY --from=builder /install /usr/local

# Copier le code applicatif
COPY --chown=appuser:appgroup app/ ./app/

# Ne pas exposer les fichiers de config locaux
USER appuser

EXPOSE 8000

# Health check intégré Docker (complément probe AKS)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Gunicorn + Uvicorn workers pour la production
CMD ["python", "-m", "uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--loop", "uvloop", \
     "--http", "h11", \
     "--no-access-log"]
