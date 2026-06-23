from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, EmailStr, Field

from app.core.database import get_db
from app.core.security import get_current_user, require_permission
from app.core.redis_client import redis_client
from app.models.client import Client, CarteFidelite
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

CACHE_TTL = 300  # 5 min


# ------------------------------------------------------------------
# Schémas
# ------------------------------------------------------------------
class ClientCreate(BaseModel):
    nom: str = Field(..., min_length=2, max_length=100)
    prenom: str = Field(..., min_length=2, max_length=100)
    telephone: Optional[str] = Field(None, pattern=r"^\+?[0-9]{8,15}$")
    email: Optional[EmailStr] = None
    ville: str = Field(default="Douala", max_length=100)
    quartier: Optional[str] = Field(None, max_length=100)
    consentement_marketing: bool = False


class ClientUpdate(BaseModel):
    nom: Optional[str] = Field(None, min_length=2, max_length=100)
    prenom: Optional[str] = Field(None, min_length=2, max_length=100)
    telephone: Optional[str] = Field(None, pattern=r"^\+?[0-9]{8,15}$")
    email: Optional[EmailStr] = None
    ville: Optional[str] = Field(None, max_length=100)
    quartier: Optional[str] = Field(None, max_length=100)
    consentement_marketing: Optional[bool] = None


class ClientResponse(BaseModel):
    id: uuid.UUID
    numero_client: str
    nom: str
    prenom: str
    telephone: Optional[str]
    email: Optional[str]
    ville: str
    quartier: Optional[str]
    is_active: bool
    consentement_marketing: bool

    model_config = {"from_attributes": True}


class ClientListResponse(BaseModel):
    total: int
    page: int
    per_page: int
    items: list[ClientResponse]


# ------------------------------------------------------------------
# Utilitaire – génération numéro client
# ------------------------------------------------------------------
async def generate_numero_client(db: AsyncSession) -> str:
    count = await db.scalar(select(func.count(Client.id)))
    return f"SM-{(count or 0) + 1:06d}"


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------
@router.post("/", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
async def create_client(
    data: ClientCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("write:clients")),
):
    # Vérifier doublon téléphone
    if data.telephone:
        existing = await db.scalar(
            select(Client).where(Client.telephone == data.telephone, Client.is_active == True)
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Numéro de téléphone déjà associé au client {existing.numero_client}",
            )

    numero = await generate_numero_client(db)
    client = Client(numero_client=numero, **data.model_dump())
    db.add(client)
    await db.flush()

    # Création automatique de la carte fidélité
    carte = CarteFidelite(client_id=client.id)
    db.add(carte)

    logger.info("Client créé", extra={
        "client_id": str(client.id),
        "numero": numero,
        "created_by": str(current_user.id),
    })

    return client


@router.get("/", response_model=ClientListResponse)
async def list_clients(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    ville: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("read:all")),
):
    cache_key = f"clients:list:{page}:{per_page}:{ville}:{search}"
    cached = await redis_client.get(cache_key)
    if cached:
        return cached

    query = select(Client).where(Client.is_active == True)
    if ville:
        query = query.where(Client.ville == ville)
    if search:
        query = query.where(
            (Client.nom.ilike(f"%{search}%")) |
            (Client.prenom.ilike(f"%{search}%")) |
            (Client.telephone.ilike(f"%{search}%")) |
            (Client.numero_client.ilike(f"%{search}%"))
        )

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    clients = (await db.execute(
        query.offset((page - 1) * per_page).limit(per_page).order_by(Client.created_at.desc())
    )).scalars().all()

    response = {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": [ClientResponse.model_validate(c).model_dump() for c in clients],
    }
    await redis_client.set(cache_key, response, ttl=CACHE_TTL)
    return response


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission("read:all")),
):
    cache_key = f"client:{client_id}"
    cached = await redis_client.get(cache_key)
    if cached:
        return cached

    client = await db.get(Client, client_id)
    if not client or not client.is_active:
        raise HTTPException(status_code=404, detail="Client introuvable")

    result = ClientResponse.model_validate(client).model_dump()
    await redis_client.set(cache_key, result, ttl=CACHE_TTL)
    return result


@router.patch("/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: uuid.UUID,
    data: ClientUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("write:clients")),
):
    client = await db.get(Client, client_id)
    if not client or not client.is_active:
        raise HTTPException(status_code=404, detail="Client introuvable")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(client, field, value)

    await redis_client.delete(f"client:{client_id}")

    logger.info("Client mis à jour", extra={
        "client_id": str(client_id),
        "fields": list(data.model_dump(exclude_unset=True).keys()),
        "updated_by": str(current_user.id),
    })
    return client


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_client(
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("write:clients")),
):
    """Suppression logique (RGPD / conformité loi camerounaise 2010/012)."""
    client = await db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client introuvable")

    client.is_active = False
    await redis_client.delete(f"client:{client_id}")

    logger.info("Client désactivé", extra={
        "client_id": str(client_id),
        "deactivated_by": str(current_user.id),
    })
