"""
Endpoint de synchronisation offline-first.
Permet aux caisses/tablettes SavoirManger de synchroniser les
opérations effectuées hors connexion (coupures Douala, zones rurales).
"""

from typing import List
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_permission
from app.core.redis_client import redis_client
from app.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


class OfflineOperation(BaseModel):
    type: str              # "create_commande", "update_client", "update_statut"
    payload: dict
    local_id: str          # ID généré côté client pour idempotence
    created_at_local: datetime
    device_id: str
    restaurant_id: str


class SyncBatch(BaseModel):
    operations: List[OfflineOperation]
    device_id: str
    last_sync_at: datetime


class SyncResult(BaseModel):
    accepted: int
    rejected: int
    errors: List[dict]
    server_time: datetime


@router.post("/batch", response_model=SyncResult)
async def sync_offline_batch(
    batch: SyncBatch,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_permission("write:commandes")),
):
    """
    Reçoit un lot d'opérations offline et les traite séquentiellement.
    Garantit l'idempotence via les local_id (offline_sync_id).
    """
    accepted = 0
    rejected = 0
    errors = []

    for op in batch.operations:
        try:
            if op.type == "create_commande":
                from app.routers.commandes import create_commande, CommandeCreate
                data = CommandeCreate(
                    **op.payload,
                    offline_sync_id=op.local_id,
                    is_offline_created=True,
                )
                await create_commande(data, db, current_user)
                accepted += 1

            elif op.type == "update_statut":
                from app.routers.commandes import update_statut, CommandeStatusUpdate
                import uuid
                await update_statut(
                    uuid.UUID(op.payload["commande_id"]),
                    CommandeStatusUpdate(**op.payload),
                    db,
                    current_user,
                )
                accepted += 1

            else:
                rejected += 1
                errors.append({"local_id": op.local_id, "error": f"Type inconnu: {op.type}"})

        except Exception as e:
            rejected += 1
            errors.append({"local_id": op.local_id, "error": str(e)})
            logger.warning("Opération offline rejetée", extra={
                "local_id": op.local_id,
                "type": op.type,
                "error": str(e),
                "device": batch.device_id,
            })

    logger.info("Sync batch terminé", extra={
        "device": batch.device_id,
        "total": len(batch.operations),
        "accepted": accepted,
        "rejected": rejected,
    })

    return SyncResult(
        accepted=accepted,
        rejected=rejected,
        errors=errors,
        server_time=datetime.now(timezone.utc),
    )


@router.get("/queue/size")
async def get_queue_size(_=Depends(require_permission("read:all"))):
    """Taille de la file offline côté serveur (monitoring)."""
    size = await redis_client.get_offline_queue_size()
    return {"queue_size": size, "timestamp": datetime.now(timezone.utc)}
