import uuid
import logging

import payment_pb2
import payment_pb2_grpc

log = logging.getLogger(__name__)


class PaymentServicer(payment_pb2_grpc.PaymentServiceServicer):
    def ProcessPayment(self, request, context):
        log.info("Processing payment for reservation %s", request.reservation_id)
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
