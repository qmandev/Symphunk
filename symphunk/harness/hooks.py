import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def pre_tool_use(
    tool_name: str,
    tool_input: dict,
    *,
    approve: Callable[[str, dict], bool] | None = None,
) -> None:
    logger.debug("PRE  tool=%s input_keys=%s", tool_name, list(tool_input.keys()))
    if approve and not approve(tool_name, tool_input):
        raise ToolCallDenied(f"Tool '{tool_name}' denied by approval gate")


def post_tool_use(
    tool_name: str,
    tool_input: dict,
    result: Any,
    *,
    incident_id: str = "",
) -> None:
    logger.info("POST tool=%s incident=%s status=ok", tool_name, incident_id or "—")


class ToolCallDenied(Exception):
    pass
