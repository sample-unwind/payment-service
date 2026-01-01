"""
Payment Service Models

Defines SQLAlchemy models for payment transactions.
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from sqlalchemy import DateTime, Float, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class PaymentStatus(str, Enum):
    """Enum for payment status."""

    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class PaymentModel(Base):
    """
    Payment transaction model.

    Stores all payment transactions including refunds.
    """

    __tablename__ = "payments"

    # Primary key
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # References
    reservation_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    # Payment details
    amount: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="EUR",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=PaymentStatus.PENDING.value,
    )
    transaction_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        unique=True,
        default=uuid4,
    )

    # Error handling
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Refund details
    refund_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    refund_amount: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    refund_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    refunded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Composite indexes for common queries
    __table_args__ = (
        Index("idx_payments_reservation_status", "reservation_id", "status"),
        Index("idx_payments_user_status", "user_id", "status"),
        Index("idx_payments_tenant_status", "tenant_id", "status"),
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert payment to dictionary."""
        return {
            "id": str(self.id),
            "reservation_id": str(self.reservation_id),
            "user_id": str(self.user_id),
            "tenant_id": str(self.tenant_id),
            "amount": self.amount,
            "currency": self.currency,
            "status": self.status,
            "transaction_id": str(self.transaction_id),
            "error_message": self.error_message,
            "refund_id": str(self.refund_id) if self.refund_id else None,
            "refund_amount": self.refund_amount,
            "refund_reason": self.refund_reason,
            "refunded_at": (self.refunded_at.isoformat() if self.refunded_at else None),
            "created_at": (self.created_at.isoformat() if self.created_at else None),
            "updated_at": (self.updated_at.isoformat() if self.updated_at else None),
        }
