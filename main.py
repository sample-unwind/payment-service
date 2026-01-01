"""
Payment Service - Main Application

FastAPI application with gRPC server for payment processing.
"""

import logging
import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from db import check_db_connection, init_db
from grpc_server import serve as grpc_serve

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# OpenAPI tags for documentation organization
tags_metadata = [
    {
        "name": "info",
        "description": "Service information and metadata",
    },
    {
        "name": "health",
        "description": "Health check endpoints for Kubernetes liveness and readiness probes",
    },
    {
        "name": "grpc",
        "description": "gRPC service documentation and proto file access",
    },
]

# Create FastAPI app with enhanced OpenAPI metadata
app = FastAPI(
    title="Payment Service",
    description="""
## Payment processing service for Parkora

This service handles payment processing via **gRPC** and provides REST endpoints
for health checks and service information.

### gRPC Service

The payment processing is done via gRPC on port **50051**. Available methods:

| Method | Description |
|--------|-------------|
| `ProcessPayment` | Process a payment for a reservation |
| `GetPaymentStatus` | Get the status of a payment by transaction ID |
| `RefundPayment` | Process a refund for a previous payment |

### Server Reflection

gRPC server reflection is enabled, allowing tools like `grpcurl` and `grpcui`
to discover the API schema automatically.

### Interactive gRPC Documentation

Use grpcui to explore the gRPC API interactively:

```bash
grpcui -plaintext payment-service.parkora.svc.cluster.local:50051
```

Or access the web-based gRPC UI at: `/grpcui/payment/`

### RabbitMQ Events

On successful payment, this service publishes a `payment.processed` event to RabbitMQ
with the following payload:

```json
{
    "event_type": "payment.processed",
    "transaction_id": "uuid",
    "reservation_id": "uuid",
    "user_id": "uuid",
    "amount": 10.00,
    "currency": "EUR",
    "timestamp": "2026-01-01T12:00:00Z"
}
```
    """,
    version="1.0.0",
    contact={
        "name": "Parkora Team",
        "email": "team@parkora.crn.si",
        "url": "https://parkora.crn.si",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    openapi_tags=tags_metadata,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Initialize database and start gRPC server on startup."""
    logger.info("Starting Payment Service...")

    # Initialize database tables
    init_db()

    # Start gRPC server in a separate thread
    grpc_thread = threading.Thread(target=grpc_serve, daemon=True)
    grpc_thread.start()
    logger.info("gRPC server started on port 50051")


@app.get("/", tags=["info"])
def root():
    """
    Root endpoint with service information.

    Returns basic information about the service and available endpoints.
    """
    return {
        "service": "Payment Service",
        "version": "1.0.0",
        "description": "Payment processing service with gRPC support",
        "endpoints": {
            "health": "/health/live, /health/ready",
            "docs": "/docs, /redoc, /openapi.json",
            "proto": "/proto/payment.proto",
            "grpc": "port 50051 - ProcessPayment, GetPaymentStatus, RefundPayment",
        },
        "grpc_reflection": True,
    }


@app.get("/health/live", tags=["health"])
def health_live():
    """
    Liveness probe endpoint.

    Returns 200 if the service is running.
    Used by Kubernetes for liveness checks.
    """
    return {"status": "alive"}


@app.get("/health/ready", tags=["health"])
def health_ready():
    """
    Readiness probe endpoint.

    Returns 200 if the service is ready to accept requests.
    Checks database connectivity.
    Used by Kubernetes for readiness checks.
    """
    db_healthy = check_db_connection()

    if not db_healthy:
        logger.warning("Database connection is not healthy")
        # Return 200 anyway to not crash the pod during startup
        # In production, you might want to return 503
        return {"status": "degraded", "database": "unhealthy"}

    return {"status": "ready", "database": "healthy"}


@app.get("/proto/payment.proto", tags=["grpc"], response_class=PlainTextResponse)
def get_proto():
    """
    Serve the gRPC proto file.

    Returns the payment.proto file content for documentation and client generation.
    """
    proto_path = Path(__file__).parent / "proto" / "payment.proto"
    if proto_path.exists():
        return proto_path.read_text()
    return PlainTextResponse(content="Proto file not found", status_code=404)
