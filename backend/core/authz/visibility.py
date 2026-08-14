"""Shared org / personal visibility rules for SQLAlchemy queries and record checks."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement


def org_or_owner_visibility(
    *,
    org_column: InstrumentedAttribute[Any],
    owner_column: InstrumentedAttribute[Any],
    user_org_id: int | None,
    user_id: int,
) -> ColumnElement[bool]:
    """Org members see org rows; personal users see rows they uploaded/created."""
    if user_org_id is not None:
        return org_column == user_org_id
    return owner_column == user_id


def org_scoped_visibility(
    *,
    org_column: InstrumentedAttribute[Any],
    user_org_id: int | None,
) -> ColumnElement[bool]:
    """Org members see org rows; personal users see only unscoped rows."""
    if user_org_id is not None:
        return org_column == user_org_id
    return org_column.is_(None)


def agriculture_flight_visibility(
    *,
    org_column: InstrumentedAttribute[Any],
    user_org_id: int | None,
) -> ColumnElement[bool]:
    return org_scoped_visibility(org_column=org_column, user_org_id=user_org_id)


def org_scoped_record_visible(*, record_org_id: int | None, user_org_id: int | None) -> bool:
    """Return whether a row's org_id is visible to the caller."""
    if user_org_id is not None:
        return record_org_id == user_org_id
    return record_org_id is None


def profile_visible_to_user(profile: Any, user: Any) -> bool:
    """Return whether an agriculture field profile is visible to the caller."""
    profile_org_id = getattr(profile, "org_id", None)
    user_org_id = getattr(user, "org_id", None)
    if user_org_id is not None:
        return profile_org_id in {None, user_org_id}
    return profile_org_id is None
