"""
Payment Service - Main Application

FastAPI application with gRPC server for payment processing.
"""

import logging
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db import check_db_connection, init_db
from grpc_server import serve as grpc_serve

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Payment Service",
    description="Payment processing service with gRPC support",
    version="1.0.0",
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


@app.get("/")
def root():
    """Root endpoint with service information."""
    return {
        "service": "Payment Service",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health/live, /health/ready",
            "grpc": "port 50051 - ProcessPayment, GetPaymentStatus, RefundPayment",
        },
    }


@app.get("/health/live")
def health_live():
    """
    Liveness probe endpoint.

    Returns 200 if the service is running.
    """
    return {"status": "alive"}


@app.get("/health/ready")
def health_ready():
    """
    Readiness probe endpoint.

    Returns 200 if the service is ready to accept requests.
    Checks database connectivity.
    """
    db_healthy = check_db_connection()

    if not db_healthy:
        logger.warning("Database connection is not healthy")
        # Return 200 anyway to not crash the pod during startup
        # In production, you might want to return 503
        return {"status": "degraded", "database": "unhealthy"}

    return {"status": "ready", "database": "healthy"}
