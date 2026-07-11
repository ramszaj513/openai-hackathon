import httpx
import pytest

from frontend.api_client import BackendAPIError, CommerceAPIClient


def test_client_surfaces_stable_backend_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/offers/missing"
        return httpx.Response(404, json={"code": "NOT_FOUND", "message": "offer was not found"})

    api = CommerceAPIClient("http://test", transport=httpx.MockTransport(handler))
    with pytest.raises(BackendAPIError, match="offer was not found") as exc_info:
        api._request("GET", "/api/offers/missing")
    api.close()

    assert exc_info.value.code == "NOT_FOUND"
    assert exc_info.value.status_code == 404


def test_health_handles_unavailable_backend() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    api = CommerceAPIClient("http://test", transport=httpx.MockTransport(handler))
    assert api.health() is False
    api.close()

