import uuid
import logging

import payment_pb2
import payment_pb2_grpc
from publisher import PaymentEventPublisher

publisher = PaymentEventPublisher()

log = logging.getLogger(__name__)


class PaymentServicer(payment_pb2_grpc.PaymentServiceServicer):
    def ProcessPayment(self, request, context):
        log.info("Processing payment for reservation %s", request.reservation_id)

        transaction_id = str(uuid.uuid4())

        # Publish event to RabbitMQ
        publisher.publish_payment_processed(
            transaction_id=transaction_id,
            reservation_id=request.reservation_id,
            user_id=request.user_id,
            amount=request.amount,
            currency=request.currency or "EUR",
        )

        return payment_pb2.PaymentResponse(
            success=True,
            transaction_id=str(uuid.uuid4()),
            message="Payment processed successfully",
        )

    def GetPaymentStatus(self, request, context):
        # dummy implementation
        return payment_pb2.PaymentStatusResponse(
            status="COMPLETED",
            transaction_id=request.transaction_id,
        )
