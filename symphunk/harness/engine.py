from __future__ import annotations

import logging
from typing import Any

import anthropic

from symphunk.config import settings
from symphunk.harness.budget import SearchBudget
from symphunk.harness.hooks import pre_tool_use, post_tool_use, ToolCallDenied
from symphunk.harness.permissions import requires_approval

logger = logging.getLogger(__name__)

_CACHE = {"type": "ephemeral"}
_SEARCH_TOOLS = {"splunk_run_query", "splunk_run_saved_search"}
_MAX_RESULT_CHARS = 2000


def _truncate(text: str) -> str:
    if len(text) <= _MAX_RESULT_CHARS:
        return text
    return text[:_MAX_RESULT_CHARS] + f"\n... [truncated {len(text) - _MAX_RESULT_CHARS} chars]"


class Engine:
    """Claude tool-use loop with prompt caching."""

    def __init__(
        self,
        mcp_client,
        tool_registry,
        skills: dict[str, str],
        *,
        incident_id: str = "",
        budget: SearchBudget | None = None,
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._mcp = mcp_client
        self._registry = tool_registry
        self._skills = skills
        self._incident_id = incident_id
        self._budget = budget

    def _system_prompt(self) -> list[dict]:
        skills_block = "\n\n---\n\n".join(
            f"# Skill: {name}\n{content}" for name, content in self._skills.items()
        )
        return [
            {
                "type": "text",
                "text": (
                    "You are Symphunk's ObsAgent — an observability triage agent for Splunk.\n"
                    "Investigate incidents methodically. Use tstats and bounded time windows "
                    "to conserve search capacity. Build an evidence package before concluding.\n"
                    "End your response with: Confidence: <0.0–1.0>\n\n"
                    + skills_block
                ),
                "cache_control": _CACHE,
            }
        ]

    async def run(self, prompt: str, *, severity: str = "low") -> dict[str, Any]:
        messages: list[dict] = [{"role": "user", "content": prompt}]
        tools = self._registry.claude_tool_defs(cache_last=True)

        while True:
            response = await self._client.messages.create(
                model=settings.anthropic_model,
                max_tokens=4096,
                system=self._system_prompt(),
                tools=tools,
                messages=messages,
            )
            logger.debug(
                "Engine response stop_reason=%s usage=%s",
                response.stop_reason,
                response.usage,
            )

            if response.stop_reason == "end_turn":
                text = next((b.text for b in response.content if hasattr(b, "text")), "")
                return {"conclusion": text, "messages": messages}

            if response.stop_reason != "tool_use":
                break

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                try:
                    pre_tool_use(
                        block.name,
                        block.input,
                        approve=lambda n, _: not requires_approval(n, severity),
                    )
                    if self._budget and block.name in _SEARCH_TOOLS:
                        expensive = "tstats" not in str(block.input).lower()
                        self._budget.check(expensive=expensive)
                    result = await self._mcp.call_tool(block.name, block.input)
                    post_tool_use(block.name, block.input, result, incident_id=self._incident_id)
                    result_str = _truncate(str(result))
                except ToolCallDenied as exc:
                    result_str = f"[DENIED] {exc}"
                except Exception as exc:
                    result_str = f"[ERROR] {exc}"
                    logger.warning("Tool call failed tool=%s: %s", block.name, exc)

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_str,
                })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        return {"conclusion": "", "messages": messages}
