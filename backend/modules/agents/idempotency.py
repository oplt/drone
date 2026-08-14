from __future__ import annotations

import hashlib
import json

from backend.modules.agents.schemas import AgentContext, MissionAgentId


def derive_agent_idempotency_key(
    agent_id: MissionAgentId,
    context: AgentContext,
) -> str:
    if context.idempotency_key:
        return context.idempotency_key
    payload = {
        "agent_id": agent_id.value,
        "phase": context.phase.value,
        "mission_runtime_id": context.mission_runtime_id,
        "client_flight_id": context.client_flight_id,
        "structured_payload": context.structured_payload,
        "question": context.question,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()
    return f"agent:{digest[:48]}"
