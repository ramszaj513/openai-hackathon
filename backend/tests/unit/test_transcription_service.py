from __future__ import annotations

import httpx
import pytest
from agent_commerce.api.transcription_routes import create_transcription_router
from agent_commerce.transcription import (
    RealtimeTranscriptionService,
    TranscriptionServiceError,
)
from fastapi import FastAPI


async def test_creates_transcription_only_realtime_call() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = (await request.aread()).decode()
        assert request.url.path == "/v1/realtime/calls"
        assert request.headers["Authorization"] == "Bearer test-key"
        assert "offer-sdp" in body
        assert '"type": "transcription"' in body
        assert '"model": "gpt-realtime-whisper"' in body
        assert '"language": "pl"' in body
        assert '"delay": "low"' in body
        return httpx.Response(201, text="answer-sdp")

    service = RealtimeTranscriptionService(
        "test-key",
        transport=httpx.MockTransport(handler),
    )

    assert await service.create_session("offer-sdp") == "answer-sdp"


async def test_requires_backend_api_key() -> None:
    service = RealtimeTranscriptionService(None)

    with pytest.raises(TranscriptionServiceError) as error:
        await service.create_session("offer-sdp")

    assert error.value.code == "TRANSCRIPTION_NOT_CONFIGURED"
    assert error.value.status_code == 503


async def test_transcription_route_returns_safe_json_error() -> None:
    app = FastAPI()
    app.include_router(create_transcription_router(RealtimeTranscriptionService(None)))
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/realtime/transcription/session",
            content="offer-sdp",
            headers={"Content-Type": "application/sdp"},
        )

    assert response.status_code == 503
    assert response.json() == {
        "code": "TRANSCRIPTION_NOT_CONFIGURED",
        "message": "Voice input requires OPENAI_API_KEY in the backend environment.",
    }


async def test_upstream_error_is_mapped_without_credentials() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": {"message": "Unsupported transcription session."}},
        )

    service = RealtimeTranscriptionService(
        "test-key",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(TranscriptionServiceError) as error:
        await service.create_session("offer-sdp")

    assert error.value.message == "Unsupported transcription session."
    assert "test-key" not in error.value.message
