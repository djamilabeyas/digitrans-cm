from datetime import datetime, timezone
from typing import Optional, List
import uuid

from sqlalchemy import String, Numeric, Integer, ForeignKey, Enum as SAEnum, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Commande(Base):
    __tablename__ = "commandes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    numero_commande: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    client_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("clients.id"), nullable=True)
    restaurant_id: Mapped[str] = mapped_column(String(50), index=True)

    statut: Mapped[str] = mapped_column(
        SAEnum(
            "en_attente", "en_preparation", "pret", "en_livraison",
            "livre", "annule", "rembourse",
            name="statut_commande"
        ),
        default="en_attente",
        index=True,
    )

    mode: Mapped[str] = mapped_column(
        SAEnum("sur_place", "a_emporter", "livraison", name="mode_commande"),
        default="sur_place"
    )

    montant_total: Mapped[float] = mapped_column(Numeric(10, 2))
    montant_paye: Mapped[float] = mapped_column(Numeric(10, 2), default=0.0)
    devise: Mapped[str] = mapped_column(String(5), default="XAF")   # FCFA

    mode_paiement: Mapped[Optional[str]] = mapped_column(
        SAEnum("especes", "mobile_money", "carte", "coupons", name="mode_paiement"),
        nullable=True
    )

    # Données offline – métadonnées de synchronisation
    is_offline_created: Mapped[bool] = mapped_column(default=False)
    offline_sync_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relations
    client: Mapped[Optional["Client"]] = relationship(back_populates="commandes")
    lignes: Mapped[List["LigneCommande"]] = relationship(back_populates="commande", cascade="all, delete-orphan")


class LigneCommande(Base):
    __tablename__ = "lignes_commande"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    commande_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("commandes.id"))
    article_id: Mapped[str] = mapped_column(String(50))
    article_nom: Mapped[str] = mapped_column(String(200))
    quantite: Mapped[int] = mapped_column(Integer)
    prix_unitaire: Mapped[float] = mapped_column(Numeric(10, 2))
    total_ligne: Mapped[float] = mapped_column(Numeric(10, 2))
    options: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # ex: {"sauce": "piment"}

    commande: Mapped["Commande"] = relationship(back_populates="lignes")
