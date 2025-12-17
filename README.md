# Payment Service

## Description
Python/FastAPI microservice for handling payments via gRPC.

## Setup
- Install Python 3.11
- Run `pip install -r requirements.txt`
- Run `python main.py`

## API Endpoints
- gRPC ProcessPayment

## CI/CD
This service uses GitHub Actions for CI/CD.

- **Triggers**: Push to main, PRs, releases.
- **Linting**: black, mypy, isort, flake8.
- **Testing**: pytest (placeholder).
- **Build**: Docker image.
- **Deploy**: Placeholders for ACR push and Helm upgrade on AKS.

See `.github/workflows/ci-cd.yml` for details.