"""Mission runtime state machine.

Defines the complete lifecycle state graph and provides validation helpers
used by the repository layer and API route handlers.

State diagram
-------------
planned ──────────────────────────────────────────────► failed
   │
   ▼
preflight ────────────────────────────────────────────► failed
   │
   ▼
queued ──────────────────────────────────────────────► aborted
   │                                                  ► failed
   ▼
arming ──────────────────────────────────────────────► aborting
   │                                                  ► failed
   ▼
airborne ───────────────────────────────────────────► completed
   │                                                 ► aborting
   │                                                 ► failed
   ▼
paused ─────────────────────────────────────────────► aborting
   │
   ▼
resumed ────────────────────────────────────────────► aborting
   │
   ▼
airborne  (cycle back)

aborting ────────────────────────────────────────────► aborted
                                                      ► failed

Terminal states: completed, aborted, failed
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# State sets
# ---------------------------------------------------------------------------

TERMINAL_STATES: frozenset[str] = frozenset({"completed", "aborted", "failed"})

# States that are counted as "active" when checking whether a mission is in
# progress (used for the single-active-mission guard and get_active() queries).
ACTIVE_STATES: frozenset[str] = frozenset(
    {
        "planned",
        "preflight",
        "queued",
        "arming",
        "airborne",
        "running",  # legacy alias kept for existing DB rows
        "paused",
        "resumed",
        "aborting",
    }
)

ALL_STATES: frozenset[str] = ACTIVE_STATES | TERMINAL_STATES

# ---------------------------------------------------------------------------
# Transition graph
# ---------------------------------------------------------------------------

# Maps each state to the set of states it may legally transition into.
# Code paths that bypass this graph (e.g. direct DB admin writes) are not
# prevented, but all API-driven transitions are validated here.
_TRANSITIONS: dict[str, frozenset[str]] = {
    # Pre-execution
    "planned": frozenset({"preflight", "queued", "failed"}),
    "preflight": frozenset({"queued", "failed"}),
    "queued": frozenset({"arming", "airborne", "running", "aborted", "failed"}),
    # Execution
    "arming": frozenset({"airborne", "running", "aborting", "failed"}),
    "airborne": frozenset({"paused", "aborting", "completed", "failed"}),
    "running": frozenset({"paused", "aborting", "airborne", "completed", "failed"}),  # legacy
    # Operator control
    "paused": frozenset({"resumed", "airborne", "aborting", "failed"}),
    "resumed": frozenset({"airborne", "running", "aborting", "failed"}),
    "aborting": frozenset({"aborted", "failed"}),
    # Terminal — no outbound transitions
    "completed": frozenset(),
    "aborted": frozenset(),
    "failed": frozenset(),
}

# ---------------------------------------------------------------------------
# Operator-command → allowed state transitions
# (subset of _TRANSITIONS, used by the API command handler)
# ---------------------------------------------------------------------------

# Maps (current_state, operator_command) → next_state.
COMMAND_TRANSITIONS: dict[tuple[str, str], str] = {
    ("queued", "abort"): "aborted",
    ("arming", "abort"): "aborting",
    ("airborne", "pause"): "paused",
    ("airborne", "abort"): "aborting",
    ("airborne", "rth"): "aborting",
    ("airborne", "land"): "aborting",
    ("running", "pause"): "paused",  # legacy
    ("running", "abort"): "aborting",  # legacy
    ("running", "rth"): "aborting",  # legacy
    ("running", "land"): "aborting",  # legacy
    ("paused", "resume"): "resumed",
    ("paused", "abort"): "aborting",
    ("paused", "land"): "aborting",
    ("resumed", "abort"): "aborting",
    ("resumed", "rth"): "aborting",
    ("resumed", "land"): "aborting",
    ("aborting", "abort"): "aborting",  # idempotent
    ("aborting", "rth"): "aborting",  # idempotent
    ("aborting", "land"): "aborting",  # idempotent
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def is_terminal(state: str) -> bool:
    """Return True if *state* is a terminal (no further transitions) state."""
    return state in TERMINAL_STATES


def is_active(state: str) -> bool:
    """Return True if *state* is considered an active (non-terminal) state."""
    return state in ACTIVE_STATES


def validate_transition(from_state: str, to_state: str) -> bool:
    """Return True if the *from_state* → *to_state* transition is allowed."""
    allowed = _TRANSITIONS.get(from_state)
    if allowed is None:
        # Unknown source state — conservative: deny
        return False
    return to_state in allowed


def allowed_command_target(current_state: str, command: str) -> str | None:
    """Return the target state for *command* from *current_state*, or None if invalid."""
    return COMMAND_TRANSITIONS.get((current_state, command))
