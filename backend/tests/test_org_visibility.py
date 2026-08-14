from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, select

from backend.core.authz.visibility import (
    agriculture_flight_visibility,
    org_or_owner_visibility,
    org_scoped_record_visible,
    org_scoped_visibility,
    profile_visible_to_user,
)

metadata = MetaData()
_assets = Table(
    "visibility_assets",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("org_id", Integer),
    Column("uploaded_by_user_id", Integer),
)


def test_org_or_owner_visibility_prefers_org_membership() -> None:
    clause = org_or_owner_visibility(
        org_column=_assets.c.org_id,
        owner_column=_assets.c.uploaded_by_user_id,
        user_org_id=7,
        user_id=99,
    )
    compiled = str(select(_assets.c.id).where(clause))
    assert "org_id" in compiled
    assert "uploaded_by_user_id" not in compiled


def test_org_or_owner_visibility_falls_back_to_owner_for_personal_users() -> None:
    clause = org_or_owner_visibility(
        org_column=_assets.c.org_id,
        owner_column=_assets.c.uploaded_by_user_id,
        user_org_id=None,
        user_id=12,
    )
    compiled = str(select(_assets.c.id).where(clause))
    assert "uploaded_by_user_id" in compiled


def test_org_scoped_visibility_limits_personal_users_to_unscoped_rows() -> None:
    clause = org_scoped_visibility(org_column=_assets.c.org_id, user_org_id=None)
    compiled = str(select(_assets.c.id).where(clause))
    assert "org_id IS NULL" in compiled


def test_agriculture_flight_visibility_matches_org_scoped_rule() -> None:
    assert str(
        agriculture_flight_visibility(org_column=_assets.c.org_id, user_org_id=3)
    ) == str(org_scoped_visibility(org_column=_assets.c.org_id, user_org_id=3))


def test_org_scoped_record_visible() -> None:
    assert org_scoped_record_visible(record_org_id=3, user_org_id=3) is True
    assert org_scoped_record_visible(record_org_id=4, user_org_id=3) is False
    assert org_scoped_record_visible(record_org_id=None, user_org_id=None) is True
    assert org_scoped_record_visible(record_org_id=3, user_org_id=None) is False


@pytest.mark.parametrize(
    ("profile_org", "user_org", "expected"),
    [
        (7, 7, True),
        (None, 7, True),
        (8, 7, False),
        (None, None, True),
        (7, None, False),
    ],
)
def test_profile_visible_to_user(profile_org, user_org, expected) -> None:
    profile = SimpleNamespace(org_id=profile_org)
    user = SimpleNamespace(org_id=user_org)
    assert profile_visible_to_user(profile, user) is expected
