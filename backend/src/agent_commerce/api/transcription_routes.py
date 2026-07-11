"""REST adapter for browser WebRTC transcription sessions."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from agent_commerce.transcription import (
    RealtimeTranscriptionService,
    TranscriptionServiceError,
)

MAX_SDP_BYTES = 64 * 1024


def create_transcription_router(service: RealtimeTranscriptionService) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["transcription"])

    @router.post("/realtime/transcription/session", response_model=None)
    async def create_session(request: Request) -> Response:
        body = await request.body()
        if not body or len(body) > MAX_SDP_BYTES:
            return JSONResponse(
                status_code=422,
                content={
                    "code": "VALIDATION_ERROR",
                    "message": "A non-empty WebRTC SDP offer of at most 64 KiB is required.",
                },
            )
        try:
            sdp_answer = await service.create_session(body.decode("utf-8"))
        except UnicodeDecodeError:
            return JSONResponse(
                status_code=422,
                content={"code": "VALIDATION_ERROR", "message": "The SDP offer must be UTF-8."},
            )
        except TranscriptionServiceError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"code": exc.code, "message": exc.message},
            )
        return PlainTextResponse(sdp_answer, media_type="application/sdp")

    return router
