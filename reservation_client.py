"""
Reservation Service Client for Payment Service

HTTP client to communicate with reservation-service GraphQL API.
Used for validating payment amounts against reservation costs.
"""

import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Configuration
RESERVATION_SERVICE_URL = os.getenv(
    "RESERVATION_SERVICE_URL",
    "http://reservation-service.parkora.svc.cluster.local:8000",
)
GRAPHQL_ENDPOINT = f"{RESERVATION_SERVICE_URL}/graphql"

# Timeout settings
REQUEST_TIMEOUT = 10.0  # seconds


@dataclass
class ReservationInfo:
    """Reservation data returned from reservation-service."""

    id: str
    tenant_id: str
    user_id: str
    total_cost: float
    status: str


class ReservationClientError(Exception):
    """Base exception for reservation client errors."""

    pass


class ReservationNotFoundError(ReservationClientError):
    """Raised when reservation is not found."""

    pass


class ReservationValidationError(ReservationClientError):
    """Raised when validation fails (e.g., amount mismatch)."""

    pass


class ReservationServiceUnavailableError(ReservationClientError):
    """Raised when reservation service is unavailable."""

    pass


class ReservationClient:
    """
    HTTP client for reservation-service GraphQL API.

    Handles:
    - Fetching reservation details
    - Validating payment amounts
    - Confirming reservations after payment
    """

    def __init__(self, base_url: str | None = None):
        """
        Initialize the reservation client.

        Args:
            base_url: Optional base URL for reservation service.
                     Defaults to RESERVATION_SERVICE_URL env var.
        """
        self.base_url = base_url or RESERVATION_SERVICE_URL
        self.graphql_url = f"{self.base_url}/graphql"

    async def get_reservation(
        self, reservation_id: str, tenant_id: str
    ) -> ReservationInfo:
        """
        Fetch reservation details from reservation-service.

        Args:
            reservation_id: UUID of the reservation
            tenant_id: UUID of the tenant (passed in X-Tenant-ID header)

        Returns:
            ReservationInfo with reservation details

        Raises:
            ReservationNotFoundError: If reservation doesn't exist
            ReservationServiceUnavailableError: If service is unavailable
        """
        query = """
            query GetReservation($id: String!) {
                reservationById(id: $id) {
                    id
                    tenantId
                    userId
                    totalCost
                    status
                }
            }
        """

        variables = {"id": reservation_id}
        headers = {"X-Tenant-ID": tenant_id, "Content-Type": "application/json"}

        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                response = await client.post(
                    self.graphql_url,
                    json={"query": query, "variables": variables},
                    headers=headers,
                )
                response.raise_for_status()

        except httpx.TimeoutException as e:
            logger.error(f"Timeout fetching reservation {reservation_id}: {e}")
            raise ReservationServiceUnavailableError(
                "Reservation service request timed out"
            ) from e

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching reservation {reservation_id}: {e}")
            raise ReservationServiceUnavailableError(
                f"Reservation service returned error: {e.response.status_code}"
            ) from e

        except httpx.RequestError as e:
            logger.error(f"Request error fetching reservation {reservation_id}: {e}")
            raise ReservationServiceUnavailableError(
                "Failed to connect to reservation service"
            ) from e

        # Parse response
        data: dict[str, Any] = response.json()

        # Check for GraphQL errors
        if "errors" in data:
            error_msg = data["errors"][0].get("message", "Unknown error")
            logger.error(f"GraphQL error: {error_msg}")
            raise ReservationClientError(f"GraphQL error: {error_msg}")

        # Extract reservation data
        reservation_data = data.get("data", {}).get("reservationById")

        if not reservation_data:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")

        return ReservationInfo(
            id=reservation_data["id"],
            tenant_id=reservation_data["tenantId"],
            user_id=reservation_data["userId"],
            total_cost=float(reservation_data["totalCost"]),
            status=reservation_data["status"],
        )

    async def validate_payment_amount(
        self,
        reservation_id: str,
        amount: float,
        tenant_id: str,
        tolerance: float = 0.01,
    ) -> ReservationInfo:
        """
        Validate that payment amount matches reservation cost.

        Args:
            reservation_id: UUID of the reservation
            amount: Payment amount to validate
            tenant_id: UUID of the tenant
            tolerance: Allowed difference (default 0.01 for floating point)

        Returns:
            ReservationInfo if validation passes

        Raises:
            ReservationNotFoundError: If reservation doesn't exist
            ReservationValidationError: If amount doesn't match
        """
        reservation = await self.get_reservation(reservation_id, tenant_id)

        # Check amount matches
        if abs(reservation.total_cost - amount) > tolerance:
            raise ReservationValidationError(
                f"Payment amount {amount} does not match reservation cost "
                f"{reservation.total_cost}"
            )

        # Check reservation status
        if reservation.status not in ["PENDING", "CONFIRMED"]:
            raise ReservationValidationError(
                f"Cannot process payment for reservation with status: "
                f"{reservation.status}"
            )

        logger.info(
            f"Payment amount validated for reservation {reservation_id}: "
            f"expected={reservation.total_cost}, received={amount}"
        )

        return reservation

    async def confirm_reservation(
        self, reservation_id: str, transaction_id: str, tenant_id: str
    ) -> bool:
        """
        Confirm a reservation after successful payment.

        Args:
            reservation_id: UUID of the reservation
            transaction_id: UUID of the payment transaction
            tenant_id: UUID of the tenant

        Returns:
            True if confirmation succeeded

        Raises:
            ReservationClientError: If confirmation fails
        """
        mutation = """
            mutation ConfirmReservation($id: String!, $transactionId: String) {
                confirmReservation(id: $id, transactionId: $transactionId) {
                    id
                    status
                    transactionId
                }
            }
        """

        variables = {"id": reservation_id, "transactionId": transaction_id}
        headers = {"X-Tenant-ID": tenant_id, "Content-Type": "application/json"}

        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                response = await client.post(
                    self.graphql_url,
                    json={"query": mutation, "variables": variables},
                    headers=headers,
                )
                response.raise_for_status()

        except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.RequestError) as e:
            logger.error(f"Error confirming reservation {reservation_id}: {e}")
            raise ReservationServiceUnavailableError(
                "Failed to confirm reservation"
            ) from e

        data: dict[str, Any] = response.json()

        if "errors" in data:
            error_msg = data["errors"][0].get("message", "Unknown error")
            logger.error(f"GraphQL error confirming reservation: {error_msg}")
            raise ReservationClientError(f"Failed to confirm: {error_msg}")

        result = data.get("data", {}).get("confirmReservation")
        if result and result.get("status") == "CONFIRMED":
            logger.info(
                f"Reservation {reservation_id} confirmed with "
                f"transaction {transaction_id}"
            )
            return True

        raise ReservationClientError(f"Unexpected confirmation result: {result}")


# Singleton instance for use across the application
_client: ReservationClient | None = None


def get_reservation_client() -> ReservationClient:
    """Get or create the singleton reservation client instance."""
    global _client
    if _client is None:
        _client = ReservationClient()
    return _client
