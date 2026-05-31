from unittest.mock import AsyncMock, MagicMock
from symphunk.harness.engine import Engine
from symphunk.harness.tools import ToolRegistry


def test_engine_instantiates():
    registry = ToolRegistry()
    mcp = AsyncMock()
    engine = Engine(mcp, registry, skills={}, incident_id="test-001")
    assert engine is not None


def test_tool_registry_claude_defs_empty():
    registry = ToolRegistry()
    assert registry.claude_tool_defs() == []


def test_tool_registry_registers_local():
    registry = ToolRegistry()
    registry.register_local("my_tool", "Does something", {"type": "object", "properties": {}})
    assert "my_tool" in registry
    assert len(registry) == 1


def test_tool_registry_cache_last():
    registry = ToolRegistry()
    registry.register_local("tool_a", "A", {"type": "object", "properties": {}})
    registry.register_local("tool_b", "B", {"type": "object", "properties": {}})
    defs = registry.claude_tool_defs(cache_last=True)
    assert "cache_control" in defs[-1]
    assert "cache_control" not in defs[0]
