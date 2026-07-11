"""HTTP-only client for the Streamlit application."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

JsonObject = dict[str, Any]


class BackendAPIError(RuntimeError):
    """A safe backend error suitable for presentation in the UI."""

    def __init__(self, code: str, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class CommerceAPIClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 8.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def health(self) -> bool:
        try:
            response = self._client.get("/health")
            return response.status_code == 200 and response.json().get("status") == "ok"
        except (httpx.HTTPError, ValueError):
            return False

    def search_offers(self, request: Mapping[str, Any]) -> list[JsonObject]:
        result = self._request("POST", "/api/offers/search", json=dict(request))
        if not isinstance(result, list):
            raise BackendAPIError("INVALID_RESPONSE", "Backend returned an invalid offer list")
        return result

    def start_transaction(self, request: Mapping[str, Any]) -> JsonObject:
        return self._object_request("POST", "/api/agent/transactions", json=dict(request))

    def get_transaction(self, transaction_id: str) -> JsonObject:
        return self._object_request("GET", f"/api/agent/transactions/{transaction_id}")

    def approve_transaction(
        self, transaction_id: str, request: Mapping[str, Any]
    ) -> JsonObject:
        return self._object_request(
            "POST",
            f"/api/agent/transactions/{transaction_id}/approve",
            json=dict(request),
        )

    def resume_transaction(self, transaction_id: str) -> JsonObject:
        return self._object_request(
            "POST", f"/api/agent/transactions/{transaction_id}/resume"
        )

    def cancel_transaction(
        self, transaction_id: str, request: Mapping[str, Any]
    ) -> JsonObject:
        return self._object_request(
            "POST",
            f"/api/agent/transactions/{transaction_id}/cancel",
            json=dict(request),
        )

    def return_transaction(
        self, transaction_id: str, request: Mapping[str, Any]
    ) -> JsonObject:
        return self._object_request(
            "POST",
            f"/api/agent/transactions/{transaction_id}/return",
            json=dict(request),
        )

    def create_checkout(self, request: Mapping[str, Any]) -> JsonObject:
        return self._object_request("POST", "/api/checkouts", json=dict(request))

    def get_checkout(self, checkout_id: str) -> JsonObject:
        return self._object_request("GET", f"/api/checkouts/{checkout_id}")

    def complete_checkout(self, checkout_id: str, request: Mapping[str, Any]) -> JsonObject:
        return self._object_request(
            "POST", f"/api/checkouts/{checkout_id}/complete", json=dict(request)
        )

    def get_order(self, order_id: str) -> JsonObject:
        return self._object_request("GET", f"/api/orders/{order_id}")

    def get_payment(self, payment_id: str) -> JsonObject:
        return self._object_request("GET", f"/api/payments/{payment_id}")

    def cancel_order(self, order_id: str, idempotency_key: str) -> JsonObject:
        return self._object_request(
            "POST",
            f"/api/orders/{order_id}/cancel",
            json={"order_id": order_id, "idempotency_key": idempotency_key},
        )

    def set_order_state(
        self, order_id: str, state: str, idempotency_key: str
    ) -> JsonObject:
        return self._object_request(
            "POST",
            f"/api/demo/orders/{order_id}/state",
            json={
                "order_id": order_id,
                "state": state,
                "idempotency_key": idempotency_key,
            },
        )

    def create_return(
        self,
        order_id: str,
        items: Mapping[str, int],
        reason: str,
        idempotency_key: str,
    ) -> JsonObject:
        return self._object_request(
            "POST",
            f"/api/orders/{order_id}/returns",
            json={
                "order_id": order_id,
                "items": dict(items),
                "reason": reason,
                "idempotency_key": idempotency_key,
            },
        )

    def list_events(self, transaction_id: str) -> list[JsonObject]:
        result = self._request("GET", f"/api/transactions/{transaction_id}/events")
        if not isinstance(result, list):
            raise BackendAPIError("INVALID_RESPONSE", "Backend returned an invalid event list")
        return result

    def _object_request(self, method: str, path: str, **kwargs: Any) -> JsonObject:
        result = self._request(method, path, **kwargs)
        if not isinstance(result, dict):
            raise BackendAPIError("INVALID_RESPONSE", "Backend returned an invalid object")
        return result

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise BackendAPIError(
                "BACKEND_UNAVAILABLE", "Cannot reach the commerce backend"
            ) from exc

        if response.is_success:
            try:
                return response.json()
            except ValueError as exc:
                raise BackendAPIError(
                    "INVALID_RESPONSE", "Backend returned unreadable data", response.status_code
                ) from exc

        try:
            error = response.json()
        except ValueError:
            error = {}
        raise BackendAPIError(
            str(error.get("code", "HTTP_ERROR")),
            str(error.get("message", "The backend rejected the request")),
            response.status_code,
        )
