"""Durable, tenant-scoped lifecycle events for reconnecting clients.

Imports intentionally stay out of this package initializer because SQLAlchemy's
model registry loads ``models`` while the shared session module is still being
constructed.
"""
