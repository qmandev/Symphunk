from enum import Enum


class IncidentStatus(str, Enum):
    NEW = "New"
    INVESTIGATING = "Investigating"
    RESOLVED = "Resolved"
    ESCALATED = "Escalated"


VALID_TRANSITIONS: dict[IncidentStatus, set[IncidentStatus]] = {
    IncidentStatus.NEW: {IncidentStatus.INVESTIGATING},
    IncidentStatus.INVESTIGATING: {IncidentStatus.RESOLVED, IncidentStatus.ESCALATED},
    IncidentStatus.RESOLVED: set(),
    IncidentStatus.ESCALATED: set(),
}


def transition(current: IncidentStatus, target: IncidentStatus) -> IncidentStatus:
    if target not in VALID_TRANSITIONS[current]:
        raise InvalidTransition(f"{current.value} → {target.value} is not a valid transition")
    return target


class InvalidTransition(Exception):
    pass
