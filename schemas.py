"""
Payment Service Pydantic Schemas

Defines Pydantic models for request/response validation.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PaymentCreate(BaseModel):
    """Schema for creating a new payment."""

    reservation_id: UUID
    user_id: UUID
    tenant_id: UUID
    amount: float = Field(..., gt=0, description="Payment amount (must be positive)")
    currency: str = Field(default="EUR", max_length=3)


class PaymentResponse(BaseModel):
    """Schema for payment response."""

    id: UUID
    reservation_id: UUID
    user_id: UUID
    tenant_id: UUID
    amount: float
    currency: str
    status: str
    transaction_id: UUID
    error_message: str | None = None
    refund_id: UUID | None = None
    refund_amount: float | None = None
    refund_reason: str | None = None
    refunded_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        """Pydantic config."""

        from_attributes = True


class PaymentStatusResponse(BaseModel):
    """Schema for payment status response."""

    status: str
    transaction_id: UUID
    amount: float
    currency: str
    created_at: datetime


class RefundCreate(BaseModel):
    """Schema for creating a refund."""

    transaction_id: UUID
    amount: float = Field(
        default=0, ge=0, description="Refund amount (0 = full refund)"
    )
    reason: str = Field(default="", max_length=500)
    tenant_id: UUID | None = None


class RefundResponse(BaseModel):
    """Schema for refund response."""

    success: bool
    refund_id: UUID | None = None
    message: str
    error_code: str | None = None


class ReservationValidation(BaseModel):
    """Schema for reservation validation data from reservation-service."""

    id: str
    status: str
    total_cost: float = Field(..., alias="totalCost")
    user_id: str = Field(..., alias="userId")

    class Config:
        """Pydantic config."""

        populate_by_name = True
