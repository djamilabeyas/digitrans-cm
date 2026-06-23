"""
Middleware d'audit – conformité loi camerounaise 2010/012
Enregistre toutes les requêtes entrantes avec métadonnées de traçabilité.
"""

import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import get_logger

logger = get_logger("audit")

# Routes exclues de l'audit (santé, métriques)
AUDIT_EXEMPT = {"/health", "/ready", "/metrics"}

# Verbes qui modifient des données – toujours audités
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class AuditMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in AUDIT_EXEMPT:
            return await call_next(request)

        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        start = time.perf_counter()

        # Injecter le request_id pour corrélation
        request.state.request_id = request_id

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        # Toujours logger les écritures ; pour les lectures, logger seulement les erreurs
        should_log = (
            request.method in WRITE_METHODS
            or response.status_code >= 400
        )

        if should_log:
            # Extraire l'utilisateur depuis le token si déjà validé
            user_id = getattr(request.state, "user_id", "anonymous")

            logger.info(
                "audit_event",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "query": str(request.url.query),
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "user_id": user_id,
                    "ip": request.headers.get("X-Forwarded-For", ""),
                    "user_agent": request.headers.get("User-Agent", ""),
                },
            )

        response.headers["X-Request-ID"] = request_id
        return response
