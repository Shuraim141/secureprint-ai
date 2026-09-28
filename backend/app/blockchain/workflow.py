"""The manufacturing provenance workflow (Module D): a fixed, linear sequence of events per
part, matching the specification's pipeline diagram exactly.

DESIGN_CREATED -> DESIGN_APPROVED -> SLICED -> PRINT_STARTED -> QUALITY_INSPECTED ->
QUALITY_APPROVED -> CERTIFIED -> SHIPPED -> RECEIVED

Order is enforced (the next event for a part must be the next step in this list) so the
provenance chain reflects a real process, not an arbitrary log. This is a deliberate MVP
choice: it makes an out-of-order or skipped step immediately visible as a rejected request
rather than a silent gap in the ledger.
"""
WORKFLOW_STEPS = [
    "DESIGN_CREATED", "DESIGN_APPROVED", "SLICED", "PRINT_STARTED", "QUALITY_INSPECTED",
    "QUALITY_APPROVED", "CERTIFIED", "SHIPPED", "RECEIVED",
]
FIRST_STEP = WORKFLOW_STEPS[0]
TERMINAL_STEP = WORKFLOW_STEPS[-1]


class WorkflowOrderError(ValueError):
    """Requested action is not the next step in the workflow for this part."""


def next_expected_action(last_action: str | None) -> str:
    if last_action is None:
        return FIRST_STEP
    try:
        index = WORKFLOW_STEPS.index(last_action)
    except ValueError as exc:
        raise WorkflowOrderError(f"Unknown workflow action recorded: {last_action}") from exc
    if index + 1 >= len(WORKFLOW_STEPS):
        raise WorkflowOrderError(f"Part has already completed the workflow ({TERMINAL_STEP})")
    return WORKFLOW_STEPS[index + 1]


def validate_next_action(last_action: str | None, requested_action: str) -> None:
    expected = next_expected_action(last_action)
    if requested_action != expected:
        raise WorkflowOrderError(
            f"Expected next step '{expected}' for this part, got '{requested_action}'"
        )
