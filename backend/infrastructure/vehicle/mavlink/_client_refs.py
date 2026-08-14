"""Resolve patchable symbols from ``mavlink_client`` after module init."""

from __future__ import annotations


def client_module():
    import backend.infrastructure.vehicle.mavlink_client as mc

    return mc
