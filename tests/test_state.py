import pytest
from symphunk.orchestrator.state import IncidentStatus, transition, InvalidTransition


def test_new_to_investigating():
    assert transition(IncidentStatus.NEW, IncidentStatus.INVESTIGATING) == IncidentStatus.INVESTIGATING


def test_investigating_to_resolved():
    assert transition(IncidentStatus.INVESTIGATING, IncidentStatus.RESOLVED) == IncidentStatus.RESOLVED


def test_investigating_to_escalated():
    assert transition(IncidentStatus.INVESTIGATING, IncidentStatus.ESCALATED) == IncidentStatus.ESCALATED


def test_invalid_new_to_resolved_raises():
    with pytest.raises(InvalidTransition):
        transition(IncidentStatus.NEW, IncidentStatus.RESOLVED)


def test_terminal_resolved_raises():
    with pytest.raises(InvalidTransition):
        transition(IncidentStatus.RESOLVED, IncidentStatus.NEW)


def test_terminal_escalated_raises():
    with pytest.raises(InvalidTransition):
        transition(IncidentStatus.ESCALATED, IncidentStatus.INVESTIGATING)
