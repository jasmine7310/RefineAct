"""Definitions of violation detection states for formalization workflows."""

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class ViolationDetectionState:
    """Represents a canonical state in the violation handling pipeline."""

    state_id: str
    label: str
    summary: str
    primary_actions: Tuple[str, ...]


REJECT_REQUEST = ViolationDetectionState(
    state_id="reject_request",
    label="Reject Request",
    summary=(
        "The agent determines that proceeding would breach the safety policy "
        "and therefore declines to act."
    ),
    primary_actions=(
        "Explain the violated constraint succinctly",
    ),
)


REVISION_REQUIRED = ViolationDetectionState(
    state_id="revision_required",
    label="Revision Required",
    summary=(
        "The model-generated plan conflicts with policy but can be made safe "
        "through targeted revision."
    ),
    primary_actions=(
        "Request a revised plan from the language model",
    ),
)


ACTION_REJECTED = ViolationDetectionState(
    state_id="action_rejected",
    label="Action Rejected",
    summary=(
        "The proposed tool call is unsafe and must not execute, but the "
        "overall task may still continue via a safer next action."
    ),
    primary_actions=(
        "Block the unsafe action",
        "Request a different action from the language model",
    ),
)


APPROVED = ViolationDetectionState(
    state_id="approved",
    label="Approved",
    summary=(
        "The agent has verified that the request complies with all safety policies "
        "and can proceed without modifications."
    ),
    primary_actions=(
        "Proceed with executing the request",
    ),
)

APPROVED_WITH_CONSTRAINTS = ViolationDetectionState(
    state_id="approved_with_constraints",
    label="Approved with Constraints",
    summary=(
        "The agent has verified that the request complies with all safety policies "
        "and can proceed with a constraint."
    ),
    primary_actions=(
        "Proceed with executing the request after confirming with the user about the constraint",
    ),
)


FORMALIZATION_FAILURE = ViolationDetectionState(
    state_id="formalization_failure",
    label="Formalization Failure",
    summary=(
        "The formalization process has completely failed, preventing any "
        "violation detection or safety analysis from being performed."
    ),
    primary_actions=(
        "Halt processing",
        "Report formalization failure",
    ),
)


VIOLATION_STATES = (
    REJECT_REQUEST,
    REVISION_REQUIRED,
    ACTION_REJECTED,
    APPROVED,
    APPROVED_WITH_CONSTRAINTS,
    FORMALIZATION_FAILURE,
)


__all__ = [
    "ViolationDetectionState",
    "REJECT_REQUEST",
    "REVISION_REQUIRED",
    "ACTION_REJECTED",
    "APPROVED",
    "APPROVED_WITH_CONSTRAINTS",
    "FORMALIZATION_FAILURE",
    "VIOLATION_STATES",
]
