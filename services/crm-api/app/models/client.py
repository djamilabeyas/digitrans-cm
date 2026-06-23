from datetime import datetime, timezone
from typing import Optional
import uuid

from sqlalchemy import String, Boolean, DateTime, Integer, Numeric, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    numero_client: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    nom: Mapped[str] = mapped_column(String(100))
    prenom: Mapped[str] = mapped_column(String(100))
    telephone: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    email: Mapped[Optional[str]] = mapped_column(String(200), index=True)

    # Données conformes RGPD / loi camerounaise – chiffrées au niveau applicatif
    date_naissance: Mapped[Optional[str]] = mapped_column(String(50))  # format chiffré

    ville: Mapped[str] = mapped_column(String(100), default="Douala")
    quartier: Mapped[Optional[str]] = mapped_column(String(100))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    consentement_marketing: Mapped[bool] = mapped_column(Boolean, default=False)
    consentement_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relations
    commandes: Mapped[list["Commande"]] = relationship(back_populates="client")
    carte_fidelite: Mapped[Optional["CarteFidelite"]] = relationship(
        back_populates="client", uselist=False
    )

    def __repr__(self) -> str:
        return f"<Client {self.numero_client} – {self.nom} {self.prenom}>"


class CarteFidelite(Base):
    __tablename__ = "cartes_fidelite"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), unique=True)
    points: Mapped[int] = mapped_column(Integer, default=0)
    niveau: Mapped[str] = mapped_column(
        SAEnum("Bronze", "Argent", "Or", "Platine", name="niveau_fidelite"),
        default="Bronze"
    )
    total_depenses: Mapped[float] = mapped_column(Numeric(12, 2), default=0.0)
    derniere_visite: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    client: Mapped["Client"] = relationship(back_populates="carte_fidelite")
    historique: Mapped[list["TransactionFidelite"]] = relationship(back_populates="carte")


class TransactionFidelite(Base):
    __tablename__ = "transactions_fidelite"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    carte_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cartes_fidelite.id"))
    points_delta: Mapped[int] = mapped_column(Integer)           # positif=gain, négatif=dépense
    motif: Mapped[str] = mapped_column(String(200))
    commande_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("commandes.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    carte: Mapped["CarteFidelite"] = relationship(back_populates="historique")
