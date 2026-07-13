from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database.base import Base


class WebhookEndpoint(Base):
    """Outbound webhook subscription for org-scoped event delivery."""

    __tablename__ = "webhook_endpoints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    events: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    secret: Mapped[str] = mapped_column(String(64), nullable=False)  # HMAC signing key
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    deliveries: Mapped[list[WebhookDelivery]] = relationship(
        back_populates="endpoint", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("idx_webhook_endpoint_org_active", "org_id", "is_active"),)


class WebhookDelivery(Base):
    """Individual webhook delivery attempt with retry tracking."""

    __tablename__ = "webhook_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    endpoint_id: Mapped[int] = mapped_column(
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), index=True, nullable=False
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_code: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    endpoint: Mapped[WebhookEndpoint] = relationship(back_populates="deliveries")

    __table_args__ = (
        Index("idx_webhook_delivery_endpoint_time", "endpoint_id", "created_at"),
        Index("idx_webhook_delivery_status_retry", "status", "next_retry_at"),
        Index(
            "idx_webhook_delivery_endpoint_status_created",
            "endpoint_id",
            "status",
            "created_at",
        ),
    )
