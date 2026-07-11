"""Server-side OpenAI Realtime transcription session creation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

import httpx

TranscriptionDelay = Literal["minimal", "low", "medium", "high", "xhigh"]


@dataclass(frozen=True)
class TranscriptionServiceError(Exception):
    """A safe, stable error returned by the transcription boundary."""

    code: str
    message: str
    status_code: int

    def __str__(self) -> str:
        return self.message


class RealtimeTranscriptionService:
    """Exchanges browser WebRTC SDP without exposing the OpenAI API key."""

    def __init__(
        self,
        api_key: str | None,
        *,
        model: str = "gpt-realtime-whisper",
        language: str | None = "pl",
        delay: TranscriptionDelay = "low",
        base_url: str = "https://api.openai.com/v1",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._language = language
        self._delay = delay
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    async def create_session(self, sdp: str) -> str:
        """Create a transcription-only Realtime call and return its SDP answer."""
        if not self._api_key:
            raise TranscriptionServiceError(
                "TRANSCRIPTION_NOT_CONFIGURED",
                "Voice input requires OPENAI_API_KEY in the backend environment.",
                503,
            )

        transcription: dict[str, str] = {
            "model": self._model,
            "delay": self._delay,
        }
        if self._language:
            transcription["language"] = self._language
        session = {
            "type": "transcription",
            "audio": {"input": {"transcription": transcription}},
        }

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(20.0),
                transport=self._transport,
            ) as client:
                response = await client.post(
                    f"{self._base_url}/realtime/calls",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    files={
                        "sdp": (None, sdp, "application/sdp"),
                        "session": (None, json.dumps(session), "application/json"),
                    },
                )
        except httpx.HTTPError as exc:
            raise TranscriptionServiceError(
                "TRANSCRIPTION_UPSTREAM_UNAVAILABLE",
                "Could not connect to OpenAI Realtime transcription.",
                503,
            ) from exc

        if response.is_error:
            message = "OpenAI could not start the Realtime transcription session."
            try:
                payload = response.json()
                upstream_message = payload.get("error", {}).get("message")
                if isinstance(upstream_message, str) and upstream_message:
                    message = upstream_message
            except (ValueError, AttributeError):
                pass
            raise TranscriptionServiceError(
                "TRANSCRIPTION_SESSION_REJECTED",
                message,
                502,
            )

        return response.text
