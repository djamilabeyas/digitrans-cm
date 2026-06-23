"""
Initialisation des comptes utilisateurs de démonstration.
Exécuté une seule fois au démarrage si la table utilisateurs est vide.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.security import hash_password
from app.core.logging import get_logger
from app.models.utilisateur import Utilisateur

logger = get_logger(__name__)

DEMO_USERS = [
    {
        "email": "admin@agrocam.cm",
        "nom": "Administrateur",
        "prenom": "Système",
        "password": "Admin@2024!",
        "role": "admin",
        "restaurant_id": None,
    },
    {
        "email": "manager.dla@agrocam.cm",
        "nom": "NGUEMO",
        "prenom": "Paul",
        "password": "Manager@2024!",
        "role": "manager",
        "restaurant_id": "SM-DLA-01",
    },
    {
        "email": "caissier.dla@agrocam.cm",
        "nom": "MBALLA",
        "prenom": "Rose",
        "password": "Caissier@2024!",
        "role": "caissier",
        "restaurant_id": "SM-DLA-01",
    },
]


async def seed_users(db: AsyncSession) -> None:
    logger.info("Vérification des comptes de démonstration...")

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    for u in DEMO_USERS:
        stmt = (
            pg_insert(Utilisateur)
            .values(
                email=u["email"],
                nom=u["nom"],
                prenom=u["prenom"],
                mot_de_passe_hash=hash_password(u["password"]),
                role=u["role"],
                restaurant_id=u.get("restaurant_id"),
            )
            .on_conflict_do_nothing(index_elements=["email"])
        )
        await db.execute(stmt)

    await db.commit()
    logger.info(f"{len(DEMO_USERS)} comptes vérifiés")
