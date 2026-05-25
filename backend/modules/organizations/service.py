from __future__ import annotations

import re

from sqlalchemy import or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from backend.modules.identity.models import User, UserRole
from backend.modules.organizations.models import Organization, Project

ORG_ELEVATED_ROLES = {
    UserRole.admin,
    UserRole.org_admin,
    UserRole.ops_manager,
}


def slugify(value: str, *, fallback: str = "workspace") -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return normalized[:48] or fallback


def can_manage_org(user: User) -> bool:
    return user.role in ORG_ELEVATED_ROLES


def can_access_org_scope(user: User) -> bool:
    if user.role == UserRole.admin:
        return True
    return user.org_id is not None


def ownership_clause(
    *,
    user: User,
    owner_col,
    org_col=None,
) -> ColumnElement[bool]:
    if user.role == UserRole.admin:
        return true()
    if org_col is not None and user.org_id is not None and can_access_org_scope(user):
        return or_(owner_col == user.id, org_col == user.org_id)
    return owner_col == user.id


def user_can_access_resource(
    user: User,
    *,
    owner_id: int | None,
    org_id: int | None,
) -> bool:
    if user.role == UserRole.admin:
        return True
    if owner_id is not None and int(owner_id) == int(user.id):
        return True
    return user.org_id is not None and org_id is not None and int(user.org_id) == int(org_id)


async def get_default_project(db: AsyncSession, *, org_id: int) -> Project | None:
    result = await db.execute(
        select(Project)
        .where(Project.org_id == org_id)
        .order_by(Project.is_default.desc(), Project.id.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_or_create_default_project(
    db: AsyncSession,
    *,
    org_id: int,
    created_by_user_id: int | None = None,
    name: str = "Default Project",
) -> Project:
    project = await get_default_project(db, org_id=org_id)
    if project is not None:
        return project

    project = Project(
        org_id=org_id,
        name=name,
        slug="default",
        created_by_user_id=created_by_user_id,
        is_default=True,
    )
    db.add(project)
    await db.flush()
    return project


async def ensure_user_workspace(db: AsyncSession, *, user: User) -> tuple[Organization, Project]:
    org = None
    if user.org_id is not None:
        org = await db.get(Organization, user.org_id)
    if org is None:
        local_part = (user.email or f"user-{user.id}").split("@", 1)[0]
        base_slug = slugify(local_part, fallback=f"user-{user.id}")
        org = Organization(
            name=f"{user.full_name or user.email or f'User {user.id}'} Workspace",
            slug=f"{base_slug}-{user.id}",
            owner_id=user.id,
        )
        db.add(org)
        await db.flush()
        user.org_id = org.id
        if user.role == UserRole.operator:
            user.role = UserRole.org_admin

    project = await get_or_create_default_project(
        db,
        org_id=int(org.id),
        created_by_user_id=int(user.id),
    )
    return org, project
