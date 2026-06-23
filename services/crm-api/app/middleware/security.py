import time
from collections import defaultdict
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Store en mémoire simple (en production : Redis partagé entre pods)
_rate_limit_store: dict = defaultdict(list)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Injecte les headers de sécurité HTTP sur toutes les réponses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        # Masquer la stack technique
        if "server" in response.headers:
            del response.headers["server"]
        if "x-powered-by" in response.headers:
            del response.headers["x-powered-by"]

        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting par IP – protection anti-DDoS basique (complément WAF Azure)."""

    EXEMPT_PATHS = {"/health", "/ready"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        now = time.time()
        window = 60  # 1 minute

        # Nettoyer les requêtes hors fenêtre
        _rate_limit_store[client_ip] = [
            ts for ts in _rate_limit_store[client_ip] if now - ts < window
        ]

        if len(_rate_limit_store[client_ip]) >= settings.RATE_LIMIT_PER_MINUTE:
            logger.warning("Rate limit dépassé", extra={"ip": client_ip})
            return JSONResponse(
                status_code=429,
                content={"detail": "Trop de requêtes. Réessayez dans 60 secondes."},
                headers={"Retry-After": "60"},
            )

        _rate_limit_store[client_ip].append(now)
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(settings.RATE_LIMIT_PER_MINUTE)
        response.headers["X-RateLimit-Remaining"] = str(
            settings.RATE_LIMIT_PER_MINUTE - len(_rate_limit_store[client_ip])
        )
        return response

    def _get_client_ip(self, request: Request) -> str:
        # Derrière l'Application Gateway Azure, l'IP réelle est dans X-Forwarded-For
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"
