"""Deterministic versioned layout interchange envelope."""

from __future__ import annotations

import hashlib
import json

SCHEMA_VERSION = "warehouse-layout/v1"


def canonical_checksum(payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(body.encode()).hexdigest()


def export_envelope(
    *, warehouse_map_id: int, layout_version: int, revision: int, entities: dict[str, list[dict]]
) -> dict:
    data = {
        "schema": SCHEMA_VERSION,
        "warehouse_map_id": warehouse_map_id,
        "layout_version": layout_version,
        "revision": revision,
        "entities": entities,
    }
    return {**data, "checksum_sha256": canonical_checksum(data)}


def validate_envelope(envelope: dict) -> list[dict[str, str]]:
    if envelope.get("schema") != SCHEMA_VERSION:
        raise ValueError("unsupported layout schema")
    checksum = envelope.get("checksum_sha256")
    content = {k: v for k, v in envelope.items() if k != "checksum_sha256"}
    if checksum != canonical_checksum(content):
        raise ValueError("layout checksum mismatch")
    return []
