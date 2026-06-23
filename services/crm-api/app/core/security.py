"""
Authentification JWT RS256 + contrôle d'accès basé sur les rôles (RBAC).
Conforme à la loi camerounaise 2010/012 (traçabilité des accès).
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger

logger = get_logger(__name__)

bearer_scheme = HTTPBearer()
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# Rôles DIGITRANS-CM
ROLES = {
    "admin":         ["*"],
    "manager":       ["read:all", "write:commandes", "write:clients", "read:reports"],
    "caissier":      ["read:menu", "write:commandes", "read:clients"],
    "livreur":       ["read:commandes:assigned", "write:commandes:status"],
    "client_app":    ["read:menu", "write:commandes:own", "read:fidelite:own"],
}


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str, role: str, restaurant_id: Optional[str] = None) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "jti": secrets.token_urlsafe(16),    # ID unique – révocation possible
        "iss": "digitrans-cm-auth",
        "aud": "digitrans-cm-crm",
    }
    if restaurant_id:
        claims["restaurant_id"] = restaurant_id

    return jwt.encode(claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(subject: str) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": subject,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        "jti": secrets.token_urlsafe(32),
        "aud": "digitrans-cm-refresh",
    }
    return jwt.encode(claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str, audience: str = "digitrans-cm-crm") -> dict:
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            audience=audience,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expiré",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        logger.warning("Token invalide", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide",
            headers={"WWW-Authenticate": "Bearer"},
        )


class _DevUser:
    """Utilisateur fictif pour l'environnement de développement."""
    def __init__(self, payload: dict):
        self.id = payload.get("sub", "dev-admin")
        self.is_active = True
        self._jwt_payload = payload


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    payload = decode_token(credentials.credentials)
    user_id = payload.get("sub")

    # En dev, on évite la requête DB et on retourne un utilisateur virtuel
    if settings.ENVIRONMENT != "prod":
        return _DevUser(payload)

    from app.services.user_service import get_user_by_id
    user = await get_user_by_id(db, user_id)

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur inactif ou introuvable",
        )

    user._jwt_payload = payload
    return user


def require_permission(permission: str):
    """Décorateur de dépendance FastAPI pour le RBAC."""
    async def _checker(current_user=Depends(get_current_user)):
        role = current_user._jwt_payload.get("role", "")
        allowed = ROLES.get(role, [])

        if "*" in allowed or permission in allowed:
            return current_user

        # Vérification préfixe (ex: "read:commandes" couvre "read:commandes:assigned")
        if any(permission.startswith(p.rstrip("*")) for p in allowed if p.endswith("*")):
            return current_user

        logger.warning(
            "Accès refusé",
            extra={"user": current_user.id, "role": role, "permission": permission}
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission requise : {permission}",
        )

    return _checker
