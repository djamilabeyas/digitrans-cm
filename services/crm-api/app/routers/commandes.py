from typing import Optional, List
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Header, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.security import get_current_user, require_permission
from app.core.redis_client import redis_client
from app.models.commande import Commande, LigneCommande
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


# ------------------------------------------------------------------
# Schémas
# ------------------------------------------------------------------
class LigneCreate(BaseModel):
    article_id: str
    article_nom: str
    quantite: int = Field(..., ge=1, le=99)
    prix_unitaire: float = Field(..., gt=0)
    options: Optional[dict] = None


class CommandeCreate(BaseModel):
    client_id: Optional[uuid.UUID] = None
    restaurant_id: str
    mode: str = Field(default="sur_place", pattern="^(sur_place|a_emporter|livraison)$")
    lignes: List[LigneCreate] = Field(..., min_length=1)
    mode_paiement: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=500)
    # Champs offline-first
    offline_sync_id: Optional[str] = None
    is_offline_created: bool = False


class CommandeStatusUpdate(BaseModel):
    statut: str = Field(..., pattern="^(en_preparation|pret|en_livraison|livre|annule|rembourse)$")
    notes: Optional[str] = None


class CommandeResponse(BaseModel):
    id: uuid.UUID
    numero_commande: str
    client_id: Optional[uuid.UUID]
    restaurant_id: str
    statut: str
    mode: str
    montant_total: float
    devise: str
    is_offline_created: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------
@router.post("/", response_model=CommandeResponse, status_code=status.HTTP_201_CREATED)
async def create_commande(
    data: CommandeCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("write:commandes")),
    x_offline_mode: Optional[str] = Header(None),
):
    # Vérifier doublon si commande offline (idempotence)
    if data.offline_sync_id:
        existing = await db.scalar(
            select(Commande).where(Commande.offline_sync_id == data.offline_sync_id)
        )
        if existing:
            logger.info("Commande offline déjà synchronisée", extra={"sync_id": data.offline_sync_id})
            return existing

    # Calculer totaux
    montant_total = sum(l.quantite * l.prix_unitaire for l in data.lignes)

    # Numéro séquentiel
    count = await db.scalar(select(func.count(Commande.id)))
    numero = f"CMD-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{(count or 0) + 1:04d}"

    commande = Commande(
        numero_commande=numero,
        client_id=data.client_id,
        restaurant_id=data.restaurant_id,
        mode=data.mode,
        montant_total=montant_total,
        mode_paiement=data.mode_paiement,
        notes=data.notes,
        is_offline_created=data.is_offline_created,
        offline_sync_id=data.offline_sync_id,
        synced_at=datetime.now(timezone.utc) if data.is_offline_created else None,
    )
    db.add(commande)
    await db.flush()

    for ligne_data in data.lignes:
        ligne = LigneCommande(
            commande_id=commande.id,
            total_ligne=ligne_data.quantite * ligne_data.prix_unitaire,
            **ligne_data.model_dump(),
        )
        db.add(ligne)

    # Mettre à jour les points fidélité si client identifié
    if data.client_id:
        from app.services.fidelite_service import crediter_points
        await crediter_points(db, data.client_id, commande.id, montant_total)

    logger.info("Commande créée", extra={
        "commande_id": str(commande.id),
        "numero": numero,
        "montant": montant_total,
        "offline": data.is_offline_created,
        "restaurant": data.restaurant_id,
    })

    return commande


@router.get("/", response_model=list[CommandeResponse])
async def list_commandes(
    restaurant_id: Optional[str] = None,
    statut: Optional[str] = None,
    date_debut: Optional[datetime] = None,
    date_fin: Optional[datetime] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("read:all")),
):
    query = select(Commande)
    if restaurant_id:
        query = query.where(Commande.restaurant_id == restaurant_id)
    if statut:
        query = query.where(Commande.statut == statut)
    if date_debut:
        query = query.where(Commande.created_at >= date_debut)
    if date_fin:
        query = query.where(Commande.created_at <= date_fin)

    result = await db.execute(
        query.order_by(Commande.created_at.desc())
             .offset((page - 1) * per_page)
             .limit(per_page)
    )
    return result.scalars().all()


@router.patch("/{commande_id}/statut", response_model=CommandeResponse)
async def update_statut(
    commande_id: uuid.UUID,
    data: CommandeStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("write:commandes")),
):
    commande = await db.get(Commande, commande_id)
    if not commande:
        raise HTTPException(status_code=404, detail="Commande introuvable")

    old_statut = commande.statut
    commande.statut = data.statut
    if data.notes:
        commande.notes = data.notes

    logger.info("Statut commande mis à jour", extra={
        "commande_id": str(commande_id),
        "ancien": old_statut,
        "nouveau": data.statut,
        "updated_by": str(current_user.id),
    })
    return commande
