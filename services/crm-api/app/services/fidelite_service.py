import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.client import CarteFidelite, TransactionFidelite


POINTS_PAR_1000_XAF = 1   # 1 point par 1000 FCFA dépensé


async def crediter_points(
    db: AsyncSession,
    client_id: uuid.UUID,
    commande_id: uuid.UUID,
    montant: float,
) -> int:
    carte = await db.scalar(
        select(CarteFidelite).where(CarteFidelite.client_id == client_id)
    )
    if not carte:
        return 0

    points_gagnes = int(montant / 1000) * POINTS_PAR_1000_XAF
    if points_gagnes <= 0:
        return 0

    carte.points += points_gagnes
    carte.total_depenses = float(carte.total_depenses or 0) + montant
    carte.derniere_visite = datetime.now(timezone.utc)

    # Recalculer le niveau
    total = float(carte.total_depenses)
    if total >= 50000:
        carte.niveau = "Platine"
    elif total >= 20000:
        carte.niveau = "Or"
    elif total >= 5000:
        carte.niveau = "Argent"
    else:
        carte.niveau = "Bronze"

    transaction = TransactionFidelite(
        carte_id=carte.id,
        points_delta=points_gagnes,
        motif=f"Achat commande {commande_id}",
        commande_id=commande_id,
    )
    db.add(transaction)

    return points_gagnes
