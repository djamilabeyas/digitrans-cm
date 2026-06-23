from typing import Optional
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import require_permission
from app.core.redis_client import redis_client
from app.models.client import CarteFidelite, TransactionFidelite

router = APIRouter()

NIVEAUX = {"Bronze": 0, "Argent": 5000, "Or": 20000, "Platine": 50000}


class FideliteResponse(BaseModel):
    client_id: uuid.UUID
    points: int
    niveau: str
    total_depenses: float
    derniere_visite: Optional[datetime]

    model_config = {"from_attributes": True}


def _calculer_niveau(total: float) -> str:
    for niveau in reversed(list(NIVEAUX.keys())):
        if total >= NIVEAUX[niveau]:
            return niveau
    return "Bronze"


@router.get("/{client_id}", response_model=FideliteResponse)
async def get_fidelite(
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("read:all")),
):
    cache_key = f"fidelite:{client_id}"
    cached = await redis_client.get(cache_key)
    if cached:
        return cached

    carte = await db.scalar(
        select(CarteFidelite).where(CarteFidelite.client_id == client_id)
    )
    if not carte:
        raise HTTPException(status_code=404, detail="Carte fidélité introuvable")

    result = FideliteResponse.model_validate(carte).model_dump()
    await redis_client.set(cache_key, result, ttl=120)
    return result


@router.get("/{client_id}/historique")
async def get_historique(
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("read:all")),
):
    carte = await db.scalar(
        select(CarteFidelite).where(CarteFidelite.client_id == client_id)
    )
    if not carte:
        raise HTTPException(status_code=404, detail="Carte fidélité introuvable")

    transactions = (await db.execute(
        select(TransactionFidelite)
        .where(TransactionFidelite.carte_id == carte.id)
        .order_by(TransactionFidelite.created_at.desc())
        .limit(50)
    )).scalars().all()

    return [
        {
            "id": str(t.id),
            "points_delta": t.points_delta,
            "motif": t.motif,
            "created_at": t.created_at.isoformat(),
        }
        for t in transactions
    ]
