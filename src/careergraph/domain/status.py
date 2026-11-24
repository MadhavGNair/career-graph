"""Application status enum and the allowed transitions between statuses."""

from __future__ import annotations

from enum import StrEnum


class ApplicationStatus(StrEnum):
    """Lifecycle of one tracked application. CareerGraph itself only ever writes READY."""

    SAVED = "saved"
    READY = "ready"
    APPLIED = "applied"
    SCREENING = "screening"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


S = ApplicationStatus
TRANSITIONS: dict[ApplicationStatus, frozenset[ApplicationStatus]] = {
    S.SAVED: frozenset({S.READY, S.APPLIED, S.WITHDRAWN}),
    S.READY: frozenset({S.APPLIED, S.WITHDRAWN}),
    S.APPLIED: frozenset({S.SCREENING, S.INTERVIEW, S.REJECTED, S.WITHDRAWN}),
    S.SCREENING: frozenset({S.INTERVIEW, S.REJECTED, S.WITHDRAWN}),
    S.INTERVIEW: frozenset({S.INTERVIEW, S.OFFER, S.REJECTED, S.WITHDRAWN}),
    S.OFFER: frozenset({S.WITHDRAWN, S.REJECTED}),
    S.REJECTED: frozenset(),
    S.WITHDRAWN: frozenset(),
}


class InvalidTransition(ValueError):
    """Raised when a status change is not allowed."""


def check_transition(current: ApplicationStatus, new: ApplicationStatus) -> None:
    """Raise InvalidTransition unless current -> new is allowed."""
    if new not in TRANSITIONS[current]:
        allowed = ", ".join(sorted(TRANSITIONS[current])) or "none (terminal)"
        raise InvalidTransition(f"cannot go from {current} to {new}; allowed: {allowed}")
