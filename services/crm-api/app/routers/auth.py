"""
Authentification DIGITRANS-CM
- POST /auth/login   : connexion email + mot de passe → JWT + refresh cookie
- POST /auth/refresh : renouvelle le JWT via le refresh token cookie
- POST /auth/logout  : révoque la session
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.core.database import get_db
from app.core.security import (
    verify_password, hash_password,
    create_access_token, create_refresh_token, decode_token,
    ROLES,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.models.utilisateur import Utilisateur

logger = get_logger(__name__)
router = APIRouter()

COOKIE_NAME = "digitrans_refresh"
COOKIE_MAX_AGE = settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400


# ------------------------------------------------------------------
# Schémas
# ------------------------------------------------------------------
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    nom: str
    prenom: str
    restaurant_id: str | None


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------
@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    # 1. Chercher l'utilisateur
    result = await db.execute(select(Utilisateur).where(Utilisateur.email == body.email))
    user: Utilisateur | None = result.scalar_one_or_none()

    # 2. Vérifier mot de passe (même délai si user inexistant → anti-timing attack)
    if not user or not verify_password(body.password, user.mot_de_passe_hash):
        logger.warning("Tentative de connexion échouée", extra={"email": body.email})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect",
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Compte désactivé")

    # 3. Mettre à jour last_login
    await db.execute(
        update(Utilisateur)
        .where(Utilisateur.id == user.id)
        .values(last_login=datetime.now(timezone.utc))
    )
    await db.commit()

    # 4. Générer les tokens
    access_token = create_access_token(
        subject=str(user.id),
        role=user.role,
        restaurant_id=user.restaurant_id,
    )
    refresh_token = create_refresh_token(subject=str(user.id))

    # 5. Refresh token dans cookie HttpOnly (JS ne peut pas le lire → protection XSS)
    response.set_cookie(
        key=COOKIE_NAME,
        value=refresh_token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="strict",
        secure=(settings.ENVIRONMENT == "prod"),  # HTTPS uniquement en prod
    )

    logger.info("Connexion réussie", extra={"user_id": str(user.id), "role": user.role})

    return TokenResponse(
        access_token=access_token,
        role=user.role,
        nom=user.nom,
        prenom=user.prenom,
        restaurant_id=user.restaurant_id,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    refresh_token = request.cookies.get(COOKIE_NAME)
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expirée")

    try:
        payload = decode_token(refresh_token, audience="digitrans-cm-refresh")
    except HTTPException:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expirée")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalide")

    user_id = payload.get("sub")
    result = await db.execute(select(Utilisateur).where(Utilisateur.id == user_id))
    user: Utilisateur | None = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Utilisateur inactif")

    new_access = create_access_token(str(user.id), user.role, user.restaurant_id)
    new_refresh = create_refresh_token(str(user.id))

    response.set_cookie(
        key=COOKIE_NAME,
        value=new_refresh,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="strict",
        secure=(settings.ENVIRONMENT == "prod"),
    )

    return TokenResponse(
        access_token=new_access,
        role=user.role,
        nom=user.nom,
        prenom=user.prenom,
        restaurant_id=user.restaurant_id,
    )


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"message": "Déconnecté"}
