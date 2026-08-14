from __future__ import annotations

from backend.core.events import MissionLifecycleEnvelopeV1, TelemetryEnvelopeV1


def _envelope_org_id(envelope: TelemetryEnvelopeV1 | MissionLifecycleEnvelopeV1) -> int | None:
    mission = getattr(envelope, "mission", None)
    if mission is None:
        return None
    org_id = getattr(mission, "org_id", None)
    return int(org_id) if org_id is not None else None
