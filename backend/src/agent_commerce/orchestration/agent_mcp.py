"""Agents SDK MCP transport compatibility helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import timedelta

import httpx
from agents.mcp import MCPServerStreamableHttp
from agents.mcp.server import MCPStreamTransport
from mcp.client.streamable_http import streamable_http_client


class CurrentMCPServerStreamableHttp(MCPServerStreamableHttp):
    """Use the current MCP streamable HTTP client with the Agents SDK server.

    The Agents SDK currently delegates to MCP's deprecated ``streamablehttp_client``
    compatibility function. This adapter keeps the SDK's server behavior and tool
    integration while opening the transport through MCP's replacement public API.
    """

    def create_streams(self) -> AbstractAsyncContextManager[MCPStreamTransport]:
        return self._create_current_streams()

    @asynccontextmanager
    async def _create_current_streams(self) -> AsyncIterator[MCPStreamTransport]:
        timeout = self.params.get("timeout", 5)
        read_timeout = self.params.get("sse_read_timeout", 60 * 5)
        timeout_seconds = timeout.total_seconds() if isinstance(timeout, timedelta) else timeout
        read_timeout_seconds = (
            read_timeout.total_seconds() if isinstance(read_timeout, timedelta) else read_timeout
        )
        client_timeout = httpx.Timeout(timeout_seconds, read=read_timeout_seconds)
        client_factory = self.params.get("httpx_client_factory")
        if client_factory is None:
            client = httpx.AsyncClient(
                headers=self.params.get("headers"),
                timeout=client_timeout,
                auth=self.params.get("auth"),
                follow_redirects=False,
            )
        else:
            client = client_factory(
                headers=self.params.get("headers"),
                timeout=client_timeout,
                auth=self.params.get("auth"),
            )

        async with (
            client,
            streamable_http_client(
                self.params["url"],
                http_client=client,
                terminate_on_close=self.params.get("terminate_on_close", True),
            ) as streams,
        ):
            yield streams
