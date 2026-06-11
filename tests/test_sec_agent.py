from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from symphunk.agents.sec_agent import SecAgent, _extract_threat_score
from symphunk.orchestrator.state import IncidentStatus


# --- _extract_threat_score ---

def test_extract_threat_score_plain():
    assert _extract_threat_score("Threat Score: 0.91") == 0.91


def test_extract_threat_score_bold_markdown():
    assert _extract_threat_score("Threat Score: **0.88**") == 0.88


def test_extract_threat_score_case_insensitive():
    assert _extract_threat_score("threat score: 0.72") == 0.72


def test_extract_threat_score_fallback_confidence():
    # Falls back to "Confidence:" phrasing
    assert _extract_threat_score("Confidence: 0.65") == 0.65


def test_extract_threat_score_missing_returns_default():
    assert _extract_threat_score("No score mentioned here.") == 0.5


def test_extract_threat_score_clamps_above_one():
    assert _extract_threat_score("Threat Score: 1.5") == 1.0


def test_extract_threat_score_clamps_below_zero():
    assert _extract_threat_score("Threat Score: -0.2") == 0.0


def test_extract_threat_score_zero():
    assert _extract_threat_score("Threat Score: 0") == 0.0


def test_extract_threat_score_one():
    assert _extract_threat_score("Threat Score: 1") == 1.0


# --- SecAgent resolve/escalate logic ---

def _make_agent(incident: dict) -> SecAgent:
    engine = AsyncMock()
    engine.run = AsyncMock(return_value={"conclusion": "Threat Score: 0.80"})
    kv = AsyncMock()
    kv.upsert = AsyncMock()
    return SecAgent(incident, engine, kv)


@pytest.mark.asyncio
async def test_sec_agent_resolves_medium_high_score():
    incident = {"id": "sec-001", "severity": "medium", "title": "Auth anomaly", "agent_type": "sec"}
    agent = _make_agent(incident)
    with patch("symphunk.agents.sec_agent.HEC") as mock_hec_cls:
        mock_hec = AsyncMock()
        mock_hec_cls.return_value = mock_hec
        result = await agent.run()
    assert result["status"] == IncidentStatus.RESOLVED
    assert result["confidence"] == 0.80


@pytest.mark.asyncio
async def test_sec_agent_escalates_high_severity():
    incident = {"id": "sec-002", "severity": "high", "title": "Breach confirmed", "agent_type": "sec"}
    agent = _make_agent(incident)
    # Even with score=0.90, high severity forces escalation
    agent._engine.run = AsyncMock(return_value={"conclusion": "Threat Score: 0.90"})
    with patch("symphunk.agents.sec_agent.HEC") as mock_hec_cls:
        mock_hec = AsyncMock()
        mock_hec_cls.return_value = mock_hec
        result = await agent.run()
    assert result["status"] == IncidentStatus.ESCALATED


@pytest.mark.asyncio
async def test_sec_agent_escalates_low_score():
    incident = {"id": "sec-003", "severity": "medium", "title": "Scanning activity", "agent_type": "sec"}
    agent = _make_agent(incident)
    agent._engine.run = AsyncMock(return_value={"conclusion": "Threat Score: 0.50"})
    with patch("symphunk.agents.sec_agent.HEC") as mock_hec_cls:
        mock_hec = AsyncMock()
        mock_hec_cls.return_value = mock_hec
        result = await agent.run()
    assert result["status"] == IncidentStatus.ESCALATED


@pytest.mark.asyncio
async def test_sec_agent_escalates_critical_severity():
    incident = {"id": "sec-004", "severity": "critical", "title": "APT detected", "agent_type": "sec"}
    agent = _make_agent(incident)
    agent._engine.run = AsyncMock(return_value={"conclusion": "Threat Score: 0.95"})
    with patch("symphunk.agents.sec_agent.HEC") as mock_hec_cls:
        mock_hec = AsyncMock()
        mock_hec_cls.return_value = mock_hec
        result = await agent.run()
    assert result["status"] == IncidentStatus.ESCALATED


# --- make_agent routing ---

def test_make_agent_routes_obs_by_default():
    """Verify that obs incidents don't accidentally get SecAgent."""
    from symphunk.agents.obs_agent import ObsAgent
    from symphunk.harness.engine import Engine
    from symphunk.harness.tools import ToolRegistry
    from symphunk.harness.budget import SearchBudget

    mcp = AsyncMock()
    registry = ToolRegistry()
    kv = AsyncMock()

    def make_agent(incident: dict):
        agent_type = incident.get("agent_type", "obs")
        budget = SearchBudget(max_searches=10)
        engine = Engine(mcp, registry, {}, incident_id=incident.get("id", ""), budget=budget)
        if agent_type == "sec":
            return SecAgent(incident, engine, kv)
        return ObsAgent(incident, engine, kv)

    obs_incident = {"id": "obs-1", "severity": "low", "agent_type": "obs"}
    sec_incident = {"id": "sec-1", "severity": "medium", "agent_type": "sec"}
    no_type_incident = {"id": "obs-2", "severity": "low"}

    assert isinstance(make_agent(obs_incident), ObsAgent)
    assert isinstance(make_agent(sec_incident), SecAgent)
    assert isinstance(make_agent(no_type_incident), ObsAgent)
