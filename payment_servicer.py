"""
Payment Service gRPC Servicer

Implements the PaymentService gRPC interface with:
- ProcessPayment: Validate amount, create payment, confirm reservation
- GetPaymentStatus: Retrieve payment details by transaction ID
- RefundPayment: Process refund for a previous payment
"""

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

import grpc

import payment_pb2
import payment_pb2_grpc
from db import DEFAULT_TENANT_ID, get_db_context_with_tenant, set_tenant_id
from models import PaymentModel, PaymentStatus
from publisher import PaymentEventPublisher
from reservation_client import (
    ReservationClient,
    ReservationClientError,
    ReservationNotFoundError,
    ReservationServiceUnavailableError,
    ReservationValidationError,
)

logger = logging.getLogger(__name__)

# Error codes for client categorization
ERROR_CODES = {
    "INVALID_REQUEST": "INVALID_REQUEST",
    "RESERVATION_NOT_FOUND": "RESERVATION_NOT_FOUND",
    "AMOUNT_MISMATCH": "AMOUNT_MISMATCH",
    "RESERVATION_SERVICE_UNAVAILABLE": "RESERVATION_SERVICE_UNAVAILABLE",
    "PAYMENT_NOT_FOUND": "PAYMENT_NOT_FOUND",
    "PAYMENT_ALREADY_REFUNDED": "PAYMENT_ALREADY_REFUNDED",
    "REFUND_NOT_ALLOWED": "REFUND_NOT_ALLOWED",
    "INTERNAL_ERROR": "INTERNAL_ERROR",
}


def run_async(coro):
    """Helper to run async code in sync gRPC handlers.

    Creates a new event loop for each call to avoid conflicts with
    the main uvicorn event loop running in a different thread.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class PaymentServicer(payment_pb2_grpc.PaymentServiceServicer):
    """
    gRPC servicer for payment operations.

    Handles payment processing, status queries, and refunds.
    Integrates with reservation-service for amount validation.
    """

    def __init__(self):
        """Initialize the servicer with dependencies."""
        self.publisher = PaymentEventPublisher()
        self.reservation_client = ReservationClient()
        logger.info("PaymentServicer initialized")

    def ProcessPayment(
        self, request: payment_pb2.PaymentRequest, context: grpc.ServicerContext
    ) -> payment_pb2.PaymentResponse:
        """
        Process a payment for a reservation.

        Steps:
        1. Validate request fields
        2. Call reservation-service to validate amount matches totalCost
        3. Create payment record in database
        4. Confirm reservation in reservation-service
        5. Publish payment event to RabbitMQ
        6. Return success with transaction_id

        Args:
            request: PaymentRequest with reservation_id, user_id, amount, currency, tenant_id
            context: gRPC context

        Returns:
            PaymentResponse with success status and transaction_id
        """
        logger.info(
            f"ProcessPayment request: reservation_id={request.reservation_id}, "
            f"user_id={request.user_id}, amount={request.amount}, "
            f"currency={request.currency}, tenant_id={request.tenant_id}"
        )

        # Validate required fields
        if not request.reservation_id:
            return payment_pb2.PaymentResponse(
                success=False,
                transaction_id="",
                message="reservation_id is required",
                error_code=ERROR_CODES["INVALID_REQUEST"],
            )

        if not request.user_id:
            return payment_pb2.PaymentResponse(
                success=False,
                transaction_id="",
                message="user_id is required",
                error_code=ERROR_CODES["INVALID_REQUEST"],
            )

        if not request.tenant_id:
            return payment_pb2.PaymentResponse(
                success=False,
                transaction_id="",
                message="tenant_id is required",
                error_code=ERROR_CODES["INVALID_REQUEST"],
            )

        if request.amount <= 0:
            return payment_pb2.PaymentResponse(
                success=False,
                transaction_id="",
                message="amount must be positive",
                error_code=ERROR_CODES["INVALID_REQUEST"],
            )

        currency = request.currency or "EUR"

        # Validate amount against reservation
        try:
            reservation_info = run_async(
                self.reservation_client.validate_payment_amount(
                    reservation_id=request.reservation_id,
                    amount=request.amount,
                    tenant_id=request.tenant_id,
                )
            )
        except ReservationNotFoundError as e:
            logger.warning(f"Reservation not found: {e}")
            return payment_pb2.PaymentResponse(
                success=False,
                transaction_id="",
                message=str(e),
                error_code=ERROR_CODES["RESERVATION_NOT_FOUND"],
            )
        except ReservationValidationError as e:
            logger.warning(f"Amount validation failed: {e}")
            return payment_pb2.PaymentResponse(
                success=False,
                transaction_id="",
                message=str(e),
                error_code=ERROR_CODES["AMOUNT_MISMATCH"],
            )
        except ReservationServiceUnavailableError as e:
            logger.error(f"Reservation service unavailable: {e}")
            return payment_pb2.PaymentResponse(
                success=False,
                transaction_id="",
                message="Reservation service is temporarily unavailable",
                error_code=ERROR_CODES["RESERVATION_SERVICE_UNAVAILABLE"],
            )
        except ReservationClientError as e:
            logger.error(f"Reservation client error: {e}")
            return payment_pb2.PaymentResponse(
                success=False,
                transaction_id="",
                message=f"Failed to validate reservation: {e}",
                error_code=ERROR_CODES["INTERNAL_ERROR"],
            )

        # Create payment record
        transaction_id = uuid4()
        payment = PaymentModel(
            reservation_id=UUID(request.reservation_id),
            user_id=UUID(request.user_id),
            tenant_id=UUID(request.tenant_id),
            amount=request.amount,
            currency=currency,
            status=PaymentStatus.PENDING.value,
            transaction_id=transaction_id,
        )

        try:
            with get_db_context_with_tenant(request.tenant_id) as db:
                db.add(payment)
                db.flush()  # Get the ID before commit

                # Try to confirm reservation
                try:
                    run_async(
                        self.reservation_client.confirm_reservation(
                            reservation_id=request.reservation_id,
                            transaction_id=str(transaction_id),
                            tenant_id=request.tenant_id,
                        )
                    )
                    # Mark payment as completed
                    payment.status = PaymentStatus.COMPLETED.value
                    logger.info(
                        f"Payment completed: transaction_id={transaction_id}, "
                        f"reservation_id={request.reservation_id}"
                    )
                except ReservationClientError as e:
                    # Mark payment as failed if confirmation fails
                    payment.status = PaymentStatus.FAILED.value
                    payment.error_message = f"Failed to confirm reservation: {e}"
                    logger.error(
                        f"Failed to confirm reservation, payment marked as failed: {e}"
                    )
                    db.commit()
                    return payment_pb2.PaymentResponse(
                        success=False,
                        transaction_id=str(transaction_id),
                        message=f"Payment recorded but reservation confirmation failed: {e}",
                        error_code=ERROR_CODES["INTERNAL_ERROR"],
                    )

                # Commit the completed payment
                db.commit()

        except Exception as e:
            logger.error(f"Database error during payment processing: {e}")
            return payment_pb2.PaymentResponse(
                success=False,
                transaction_id="",
                message="Internal error during payment processing",
                error_code=ERROR_CODES["INTERNAL_ERROR"],
            )

        # Publish event to RabbitMQ (best effort, don't fail if queue is down)
        try:
            self.publisher.publish_payment_processed(
                transaction_id=str(transaction_id),
                reservation_id=request.reservation_id,
                user_id=request.user_id,
                amount=request.amount,
                currency=currency,
            )
        except Exception as e:
            logger.warning(f"Failed to publish payment event: {e}")
            # Don't fail the payment, just log the error

        return payment_pb2.PaymentResponse(
            success=True,
            transaction_id=str(transaction_id),
            message="Payment processed successfully",
            error_code="",
        )

    def GetPaymentStatus(
        self,
        request: payment_pb2.PaymentStatusRequest,
        context: grpc.ServicerContext,
    ) -> payment_pb2.PaymentStatusResponse:
        """
        Get the status of a payment by transaction ID.

        Args:
            request: PaymentStatusRequest with transaction_id
            context: gRPC context

        Returns:
            PaymentStatusResponse with status, amount, currency, created_at
        """
        logger.info(
            f"GetPaymentStatus request: transaction_id={request.transaction_id}"
        )

        if not request.transaction_id:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("transaction_id is required")
            return payment_pb2.PaymentStatusResponse(
                status="",
                transaction_id="",
                amount=0,
                currency="",
                created_at="",
            )

        try:
            # Note: GetPaymentStatus doesn't have tenant_id in request,
            # so we use default. The transaction_id query is unique anyway.
            with get_db_context_with_tenant(DEFAULT_TENANT_ID) as db:
                payment = (
                    db.query(PaymentModel)
                    .filter(PaymentModel.transaction_id == UUID(request.transaction_id))
                    .first()
                )

                if not payment:
                    context.set_code(grpc.StatusCode.NOT_FOUND)
                    context.set_details("Payment not found")
                    return payment_pb2.PaymentStatusResponse(
                        status="",
                        transaction_id=request.transaction_id,
                        amount=0,
                        currency="",
                        created_at="",
                    )

                created_at = payment.created_at
                created_at_str = (
                    created_at.isoformat()
                    if isinstance(created_at, datetime)
                    else str(created_at)
                )

                return payment_pb2.PaymentStatusResponse(
                    status=payment.status,
                    transaction_id=str(payment.transaction_id),
                    amount=payment.amount,
                    currency=payment.currency,
                    created_at=created_at_str,
                )

        except ValueError as e:
            logger.warning(f"Invalid transaction_id format: {e}")
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("Invalid transaction_id format")
            return payment_pb2.PaymentStatusResponse(
                status="",
                transaction_id=request.transaction_id,
                amount=0,
                currency="",
                created_at="",
            )
        except Exception as e:
            logger.error(f"Database error in GetPaymentStatus: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Internal error")
            return payment_pb2.PaymentStatusResponse(
                status="",
                transaction_id=request.transaction_id,
                amount=0,
                currency="",
                created_at="",
            )

    def RefundPayment(
        self,
        request: payment_pb2.RefundRequest,
        context: grpc.ServicerContext,
    ) -> payment_pb2.RefundResponse:
        """
        Process a refund for a previous payment.

        Steps:
        1. Validate request fields
        2. Find original payment by transaction_id
        3. Check payment is refundable (COMPLETED status, not already refunded)
        4. Calculate refund amount (full refund if amount=0)
        5. Update payment record with refund details
        6. Publish refund event

        Args:
            request: RefundRequest with transaction_id, amount, reason, tenant_id
            context: gRPC context

        Returns:
            RefundResponse with success status and refund_id
        """
        logger.info(
            f"RefundPayment request: transaction_id={request.transaction_id}, "
            f"amount={request.amount}, reason={request.reason}"
        )

        # Validate required fields
        if not request.transaction_id:
            return payment_pb2.RefundResponse(
                success=False,
                refund_id="",
                message="transaction_id is required",
                error_code=ERROR_CODES["INVALID_REQUEST"],
            )

        if not request.tenant_id:
            return payment_pb2.RefundResponse(
                success=False,
                refund_id="",
                message="tenant_id is required",
                error_code=ERROR_CODES["INVALID_REQUEST"],
            )

        try:
            with get_db_context_with_tenant(request.tenant_id) as db:
                # Find the original payment
                payment = (
                    db.query(PaymentModel)
                    .filter(PaymentModel.transaction_id == UUID(request.transaction_id))
                    .first()
                )

                if not payment:
                    return payment_pb2.RefundResponse(
                        success=False,
                        refund_id="",
                        message="Payment not found",
                        error_code=ERROR_CODES["PAYMENT_NOT_FOUND"],
                    )

                # Check tenant matches
                if str(payment.tenant_id) != request.tenant_id:
                    return payment_pb2.RefundResponse(
                        success=False,
                        refund_id="",
                        message="Payment not found",
                        error_code=ERROR_CODES["PAYMENT_NOT_FOUND"],
                    )

                # Check if already refunded
                if payment.status == PaymentStatus.REFUNDED.value:
                    return payment_pb2.RefundResponse(
                        success=False,
                        refund_id=str(payment.refund_id) if payment.refund_id else "",
                        message="Payment has already been refunded",
                        error_code=ERROR_CODES["PAYMENT_ALREADY_REFUNDED"],
                    )

                # Check if refundable
                if payment.status != PaymentStatus.COMPLETED.value:
                    return payment_pb2.RefundResponse(
                        success=False,
                        refund_id="",
                        message=f"Cannot refund payment with status: {payment.status}",
                        error_code=ERROR_CODES["REFUND_NOT_ALLOWED"],
                    )

                # Calculate refund amount (0 means full refund)
                refund_amount = request.amount if request.amount > 0 else payment.amount

                # Validate refund amount
                if refund_amount > payment.amount:
                    return payment_pb2.RefundResponse(
                        success=False,
                        refund_id="",
                        message=(
                            f"Refund amount {refund_amount} exceeds "
                            f"original payment amount {payment.amount}"
                        ),
                        error_code=ERROR_CODES["INVALID_REQUEST"],
                    )

                # Process refund
                refund_id = uuid4()
                payment.status = PaymentStatus.REFUNDED.value
                payment.refund_id = refund_id
                payment.refund_amount = refund_amount
                payment.refund_reason = request.reason or "Cancellation refund"
                payment.refunded_at = datetime.now(timezone.utc)

                db.commit()

                logger.info(
                    f"Refund processed: refund_id={refund_id}, "
                    f"transaction_id={request.transaction_id}, "
                    f"amount={refund_amount}"
                )

                # Publish refund event (best effort)
                try:
                    self.publisher.publish_payment_refunded(
                        refund_id=str(refund_id),
                        transaction_id=request.transaction_id,
                        amount=refund_amount,
                        reason=request.reason or "Cancellation refund",
                    )
                except Exception as e:
                    logger.warning(f"Failed to publish refund event: {e}")

                return payment_pb2.RefundResponse(
                    success=True,
                    refund_id=str(refund_id),
                    message="Refund processed successfully",
                    error_code="",
                )

        except ValueError as e:
            logger.warning(f"Invalid UUID format: {e}")
            return payment_pb2.RefundResponse(
                success=False,
                refund_id="",
                message="Invalid transaction_id format",
                error_code=ERROR_CODES["INVALID_REQUEST"],
            )
        except Exception as e:
            logger.error(f"Database error during refund processing: {e}")
            return payment_pb2.RefundResponse(
                success=False,
                refund_id="",
                message="Internal error during refund processing",
                error_code=ERROR_CODES["INTERNAL_ERROR"],
            )
