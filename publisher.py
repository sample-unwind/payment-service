"""
Payment Event Publisher

Publishes payment events to RabbitMQ for consumption by other services.
"""

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

import pika

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PaymentProcessedEvent:
    """Event published when a payment is processed."""

    event_type: str
    transaction_id: str
    reservation_id: str
    user_id: str
    amount: float
    currency: str
    timestamp: str  # ISO


@dataclass(frozen=True)
class PaymentRefundedEvent:
    """Event published when a payment is refunded."""

    event_type: str
    refund_id: str
    transaction_id: str
    amount: float
    reason: str
    timestamp: str  # ISO


class PaymentEventPublisher:
    """Publisher for payment-related events to RabbitMQ."""

    def __init__(self) -> None:
        """Initialize publisher with RabbitMQ configuration from environment."""
        self.host = os.getenv("RABBITMQ_HOST", "localhost")
        self.port = int(os.getenv("RABBITMQ_PORT", "5672"))
        self.user = os.getenv("RABBITMQ_USER", "guest")
        self.password = os.getenv("RABBITMQ_PASSWORD", "guest")

        self.exchange = os.getenv("PAYMENTS_EXCHANGE", "payments")
        self.exchange_type = os.getenv("PAYMENTS_EXCHANGE_TYPE", "topic")

        self._enabled = self._check_rabbitmq_config()

    def _check_rabbitmq_config(self) -> bool:
        """Check if RabbitMQ is configured."""
        if not os.getenv("RABBITMQ_HOST"):
            logger.warning(
                "RABBITMQ_HOST not set - event publishing disabled. "
                "Events will be logged but not sent to RabbitMQ."
            )
            return False
        return True

    def _get_connection(self) -> pika.BlockingConnection:
        """Create a RabbitMQ connection."""
        credentials = pika.PlainCredentials(self.user, self.password)
        params = pika.ConnectionParameters(
            host=self.host,
            port=self.port,
            credentials=credentials,
            heartbeat=30,
            blocked_connection_timeout=30,
        )
        return pika.BlockingConnection(params)

    def _publish_event(self, routing_key: str, event_data: dict) -> None:
        """Publish an event to RabbitMQ."""
        if not self._enabled:
            logger.info(
                f"Event publishing disabled, would publish: "
                f"routing_key={routing_key}, data={event_data}"
            )
            return

        connection = self._get_connection()
        try:
            channel = connection.channel()
            channel.exchange_declare(
                exchange=self.exchange,
                exchange_type=self.exchange_type,
                durable=True,
            )

            channel.basic_publish(
                exchange=self.exchange,
                routing_key=routing_key,
                body=json.dumps(event_data),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # persistent
                    content_type="application/json",
                ),
            )
            logger.info(f"Published event: routing_key={routing_key}")
        finally:
            connection.close()

    def publish_payment_processed(
        self,
        *,
        transaction_id: str,
        reservation_id: str,
        user_id: str,
        amount: float,
        currency: str,
    ) -> None:
        """
        Publish a payment.processed event.

        Args:
            transaction_id: UUID of the transaction
            reservation_id: UUID of the reservation
            user_id: UUID of the user
            amount: Payment amount
            currency: Currency code (EUR, USD, etc.)
        """
        event = PaymentProcessedEvent(
            event_type="payment.processed",
            transaction_id=transaction_id,
            reservation_id=reservation_id,
            user_id=user_id,
            amount=amount,
            currency=currency,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        self._publish_event("payment.processed", asdict(event))

    def publish_payment_refunded(
        self,
        *,
        refund_id: str,
        transaction_id: str,
        amount: float,
        reason: str,
    ) -> None:
        """
        Publish a payment.refunded event.

        Args:
            refund_id: UUID of the refund
            transaction_id: UUID of the original transaction
            amount: Refund amount
            reason: Reason for the refund
        """
        event = PaymentRefundedEvent(
            event_type="payment.refunded",
            refund_id=refund_id,
            transaction_id=transaction_id,
            amount=amount,
            reason=reason,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        self._publish_event("payment.refunded", asdict(event))
