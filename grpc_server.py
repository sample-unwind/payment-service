from concurrent import futures
import logging

import grpc
from grpc_reflection.v1alpha import reflection

import payment_pb2
import payment_pb2_grpc
from payment_servicer import PaymentServicer

logging.basicConfig(level=logging.INFO)


def serve() -> None:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    payment_pb2_grpc.add_PaymentServiceServicer_to_server(PaymentServicer(), server)

    service_names = (
        payment_pb2.DESCRIPTOR.services_by_name["PaymentService"].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(service_names, server)

    server.add_insecure_port("0.0.0.0:50051")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
