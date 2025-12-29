import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

import pika


@dataclass(frozen=True)
class PaymentProcessedEvent:
    event_type: str
    transaction_id: str
    reservation_id: str
    user_id: str
    amount: float
    currency: str
    timestamp: str  # ISO


class PaymentEventPublisher:
    def __init__(self) -> None:
        self.host = os.getenv("RABBITMQ_HOST")
        self.port = os.getenv("RABBITMQ_PORT")
        self.user = os.getenv("RABBITMQ_USER")
        self.password = os.getenv("RABBITMQ_PASSWORD")

        self.exchange = os.getenv("PAYMENTS_EXCHANGE") or "payments"
        self.exchange_type = os.getenv("PAYMENTS_EXCHANGE_TYPE") or "topic"

    def publish_payment_processed(
        self,
        *,
        transaction_id: str,
        reservation_id: str,
        user_id: str,
        amount: float,
        currency: str,
    ) -> None:
        event = PaymentProcessedEvent(
            event_type="payment.processed",
            transaction_id=transaction_id,
            reservation_id=reservation_id,
            user_id=user_id,
            amount=amount,
            currency=currency,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        credentials = pika.PlainCredentials(self.user, self.password)
        params = pika.ConnectionParameters(
            host=self.host,
            port=self.port,
            credentials=credentials,
            heartbeat=30,
            blocked_connection_timeout=30,
        )

        connection = pika.BlockingConnection(params)
        try:
            channel = connection.channel()
            channel.exchange_declare(
                exchange=self.exchange,
                exchange_type=self.exchange_type,
                durable=True,
            )

            channel.basic_publish(
                exchange=self.exchange,
                routing_key="payment.processed",
                body=json.dumps(asdict(event)),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # persistent
                    content_type="application/json",
                ),
            )
        finally:
            connection.close()
