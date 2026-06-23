"""
DIGITRANS-CM – CRM API (SavoirManger)
Module de gestion de la relation client pour les restaurants AGROCAM.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import settings
from app.core.database import engine, Base
from app.core.logging import configure_logging, get_logger
from app.core.redis_client import redis_client
from app.routers import clients, commandes, fidelite, sync
from app.middleware.security import SecurityHeadersMiddleware, RateLimitMiddleware
from app.middleware.audit import AuditMiddleware

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info("DIGITRANS-CM CRM API démarrage", extra={"env": settings.ENVIRONMENT})

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await redis_client.connect()
    logger.info("Redis connecté – cache offline-first activé")

    yield

    await redis_client.close()
    logger.info("CRM API arrêt propre")


app = FastAPI(
    title="DIGITRANS-CM CRM API",
    description="API REST du module CRM – Restaurants SavoirManger (AGROCAM S.A.)",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if settings.ENVIRONMENT != "prod" else None,
    lifespan=lifespan,
)


@app.get("/api/docs", include_in_schema=False)
async def custom_swagger():
    from fastapi.responses import HTMLResponse
    from fastapi.openapi.docs import get_swagger_ui_html
    return get_swagger_ui_html(
        openapi_url="/api/openapi.json",
        title="DIGITRANS-CM CRM API",
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
    )

# ------------------------------------------------------------------
# Middleware (ordre important : dernier ajouté = premier exécuté)
# ------------------------------------------------------------------
app.add_middleware(AuditMiddleware)          # journalisation conformité loi 2010/012
app.add_middleware(RateLimitMiddleware)      # anti-DDoS
app.add_middleware(SecurityHeadersMiddleware)  # headers sécurité HTTP

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Offline-Mode"],
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.ALLOWED_HOSTS,
)

# ------------------------------------------------------------------
# Routeurs
# ------------------------------------------------------------------
app.include_router(clients.router,   prefix="/api/v1/clients",   tags=["Clients"])
app.include_router(commandes.router, prefix="/api/v1/commandes", tags=["Commandes"])
app.include_router(fidelite.router,  prefix="/api/v1/fidelite",  tags=["Fidélité"])
app.include_router(sync.router,      prefix="/api/v1/sync",       tags=["Sync Offline"])


@app.get("/health", tags=["System"])
async def health():
    """Endpoint de santé – utilisé par le probe AKS et l'Application Gateway."""
    redis_ok = await redis_client.ping()
    return {
        "status": "healthy",
        "service": "crm-api",
        "version": "1.0.0",
        "redis": "ok" if redis_ok else "degraded",
    }


@app.get("/ready", tags=["System"])
async def readiness():
    """Readiness probe – AKS ne route pas le trafic si KO."""
    from app.core.database import check_db_connection
    db_ok = await check_db_connection()
    if not db_ok:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Base de données indisponible")
    return {"status": "ready"}
