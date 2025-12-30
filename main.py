import threading
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from grpc_server import serve as grpc_serve

app = FastAPI(title="Payment Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Start gRPC server in a separate thread
threading.Thread(target=grpc_serve, daemon=True).start()


@app.get("/health/live")
def health_live():
    return {"status": "alive"}


@app.get("/health/ready")
def health_ready():
    return {"status": "ready"}


@app.get("/")
def root():
    return {"message": "Payment Service API"}
