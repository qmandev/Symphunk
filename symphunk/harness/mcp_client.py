from __future__ import annotations

import logging
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

logger = logging.getLogger(__name__)


class MCPClient:
    """Streamable-HTTP client for the Splunk MCP Server.

    Uses the HTTP proxy endpoint (port 8000) for local dev to avoid self-signed cert issues.
    Two endpoints available:
      - http://localhost:8000/en-US/splunkd/__raw/services/mcp  (HTTP, no SSL — use for dev)
      - https://localhost:8089/services/mcp                     (HTTPS, self-signed cert)
    """

    def __init__(self, url: str, token: str) -> None:
        self._url = url
        self._token = token
        self._session: ClientSession | None = None
        self._transport = None
        self._tools: dict[str, Any] = {}

    async def __aenter__(self) -> MCPClient:
        await self.connect()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def connect(self) -> None:
        headers = {"Authorization": f"Bearer {self._token}"}
        self._transport = streamablehttp_client(self._url, headers=headers)
        read, write, _ = await self._transport.__aenter__()
        self._session = ClientSession(read, write)
        await self._session.__aenter__()
        await self._session.initialize()
        tools_result = await self._session.list_tools()
        self._tools = {t.name: t for t in tools_result.tools}
        logger.info("MCP connected url=%s tools=%d", self._url, len(self._tools))

    async def close(self) -> None:
        if self._session:
            await self._session.__aexit__(None, None, None)
        if self._transport:
            await self._transport.__aexit__(None, None, None)

    async def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def tool_schemas(self) -> list[Any]:
        return list(self._tools.values())

    async def call_tool(self, name: str, arguments: dict) -> Any:
        if not self._session:
            raise RuntimeError("MCPClient not connected — use as async context manager")
        logger.debug("MCP call tool=%s", name)
        result = await self._session.call_tool(name, arguments)
        return result.content
