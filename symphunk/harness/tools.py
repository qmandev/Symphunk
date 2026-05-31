from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, dict] = {}

    def from_mcp(self, mcp_tools: list) -> None:
        for tool in mcp_tools:
            self._tools[tool.name] = {
                "description": getattr(tool, "description", ""),
                "schema": tool.inputSchema,
                "source": "mcp",
            }
        logger.info("Registered %d MCP tools", len(mcp_tools))

    def register_local(self, name: str, description: str, schema: dict) -> None:
        self._tools[name] = {"description": description, "schema": schema, "source": "local"}

    def claude_tool_defs(self, *, cache_last: bool = True) -> list[dict]:
        """Return tool definitions in Anthropic format, optionally caching the last entry."""
        defs = [
            {
                "name": name,
                "description": meta["description"],
                "input_schema": meta.get("schema", {"type": "object", "properties": {}}),
            }
            for name, meta in self._tools.items()
        ]
        if cache_last and defs:
            defs[-1]["cache_control"] = {"type": "ephemeral"}
        return defs

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)
