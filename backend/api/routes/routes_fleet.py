"""Fleet management endpoints — operator certifications and device readiness.

Prefix  : /fleet  (mounted under /tasks in api_main.py)
Auth    : require_org_user
Models  : OperatorCertification, DeviceReadiness, User
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from backend.auth.deps import OrgUser, require_org_user
from backend.db.models import DeviceReadiness, OperatorCertification, User
from backend.db.session import Session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fleet", tags=["fleet"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CertCreate(BaseModel):
    user_id: int | None = None  # defaults to current user
    cert_type: str  # FAA_PART_107 | ICAO_RPAS | OTHER
    cert_number: str
    issued_at: datetime
    expires_at: datetime | None = None
    issuing_authority: str | None = None
    document_url: str | None = None


class CertPatch(BaseModel):
    cert_type: str | None = None
    cert_number: str | None = None
    issued_at: datetime | None = None
    expires_at: datetime | None = None
    issuing_authority: str | None = None
    document_url: str | None = None


class DeviceReadinessCreate(BaseModel):
    device_id: str
    device_name: str
    last_inspection_at: datetime | None = None
    next_inspection_due: datetime | None = None
    status: str = "airworthy"  # airworthy | grounded | limited
    notes: str | None = None


class DeviceReadinessUpdate(BaseModel):
    device_name: str | None = None
    last_inspection_at: datetime | None = None
    next_inspection_due: datetime | None = None
    status: str | None = None
    notes: str | None = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _cert_out(cert: OperatorCertification, user_email: str | None = None) -> dict[str, Any]:
    return {
        "id": cert.id,
        "user_id": cert.user_id,
        "user_email": user_email,
        "org_id": cert.org_id,
        "cert_type": cert.cert_type,
        "cert_number": cert.cert_number,
        "issued_at": cert.issued_at.isoformat(),
        "expires_at": cert.expires_at.isoformat() if cert.expires_at else None,
        "issuing_authority": cert.issuing_authority,
        "document_url": cert.document_url,
        "created_at": cert.created_at.isoformat(),
        "updated_at": cert.updated_at.isoformat(),
    }


def _device_out(device: DeviceReadiness) -> dict[str, Any]:
    return {
        "id": device.id,
        "device_id": device.device_id,
        "org_id": device.org_id,
        "device_name": device.device_name,
        "last_inspection_at": (
            device.last_inspection_at.isoformat() if device.last_inspection_at else None
        ),
        "next_inspection_due": (
            device.next_inspection_due.isoformat() if device.next_inspection_due else None
        ),
        "status": device.status,
        "notes": device.notes,
        "created_at": device.created_at.isoformat(),
        "updated_at": device.updated_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Certification routes
# ---------------------------------------------------------------------------


@router.get("/certifications")
async def list_certifications(
    org_user: OrgUser = Depends(require_org_user),
) -> list[dict[str, Any]]:
    """List all certifications for the org (or unscoped user if no org)."""
    async with Session() as db:
        stmt = select(OperatorCertification)
        if org_user.org_id is not None:
            stmt = stmt.where(OperatorCertification.org_id == org_user.org_id)
        else:
            stmt = stmt.where(OperatorCertification.user_id == org_user.user.id)
        stmt = stmt.order_by(OperatorCertification.created_at.desc())

        certs = (await db.execute(stmt)).scalars().all()

        # Batch-load user emails
        user_ids = list({c.user_id for c in certs})
        email_map: dict[int, str] = {}
        if user_ids:
            rows = (
                await db.execute(select(User.id, User.email).where(User.id.in_(user_ids)))
            ).all()
            email_map = {uid: email for uid, email in rows}

        return [_cert_out(c, email_map.get(c.user_id)) for c in certs]


@router.post("/certifications", status_code=201)
async def create_certification(
    payload: CertCreate,
    org_user: OrgUser = Depends(require_org_user),
) -> dict[str, Any]:
    """Create a certification. user_id defaults to the authenticated user."""
    effective_user_id = payload.user_id if payload.user_id is not None else org_user.user.id

    async with Session() as db:
        cert = OperatorCertification(
            user_id=effective_user_id,
            org_id=org_user.org_id,
            cert_type=payload.cert_type,
            cert_number=payload.cert_number,
            issued_at=payload.issued_at,
            expires_at=payload.expires_at,
            issuing_authority=payload.issuing_authority,
            document_url=payload.document_url,
        )
        db.add(cert)
        await db.commit()
        await db.refresh(cert)

        # Fetch user email for response
        q = await db.execute(select(User.email).where(User.id == effective_user_id))
        email = q.scalar_one_or_none()
        return _cert_out(cert, email)


@router.patch("/certifications/{cert_id}")
async def patch_certification(
    cert_id: int,
    payload: CertPatch,
    org_user: OrgUser = Depends(require_org_user),
) -> dict[str, Any]:
    """Partially update a certification. Scoped to org."""
    async with Session() as db:
        q = await db.execute(
            select(OperatorCertification).where(OperatorCertification.id == cert_id)
        )
        cert = q.scalar_one_or_none()
        if not cert:
            raise HTTPException(status_code=404, detail="Certification not found")

        # Scope check: same org or same user
        if (org_user.org_id is not None and cert.org_id != org_user.org_id) or (
            org_user.org_id is None and cert.user_id != org_user.user.id
        ):
            raise HTTPException(status_code=403, detail="Not authorized")

        if payload.cert_type is not None:
            cert.cert_type = payload.cert_type
        if payload.cert_number is not None:
            cert.cert_number = payload.cert_number
        if payload.issued_at is not None:
            cert.issued_at = payload.issued_at
        if payload.expires_at is not None:
            cert.expires_at = payload.expires_at
        if payload.issuing_authority is not None:
            cert.issuing_authority = payload.issuing_authority
        if payload.document_url is not None:
            cert.document_url = payload.document_url

        await db.commit()
        await db.refresh(cert)

        q2 = await db.execute(select(User.email).where(User.id == cert.user_id))
        email = q2.scalar_one_or_none()
        return _cert_out(cert, email)


@router.delete("/certifications/{cert_id}", status_code=204)
async def delete_certification(
    cert_id: int,
    org_user: OrgUser = Depends(require_org_user),
) -> None:
    """Delete a certification. Scoped to org."""
    async with Session() as db:
        q = await db.execute(
            select(OperatorCertification).where(OperatorCertification.id == cert_id)
        )
        cert = q.scalar_one_or_none()
        if not cert:
            raise HTTPException(status_code=404, detail="Certification not found")

        if (org_user.org_id is not None and cert.org_id != org_user.org_id) or (
            org_user.org_id is None and cert.user_id != org_user.user.id
        ):
            raise HTTPException(status_code=403, detail="Not authorized")

        await db.delete(cert)
        await db.commit()


# ---------------------------------------------------------------------------
# Device readiness routes
# ---------------------------------------------------------------------------


@router.get("/device-readiness")
async def list_device_readiness(
    org_user: OrgUser = Depends(require_org_user),
) -> list[dict[str, Any]]:
    """List all device readiness records for the org."""
    async with Session() as db:
        stmt = select(DeviceReadiness)
        if org_user.org_id is not None:
            stmt = stmt.where(DeviceReadiness.org_id == org_user.org_id)
        stmt = stmt.order_by(DeviceReadiness.updated_at.desc())
        devices = (await db.execute(stmt)).scalars().all()
        return [_device_out(d) for d in devices]


@router.post("/device-readiness", status_code=201)
async def upsert_device_readiness(
    payload: DeviceReadinessCreate,
    org_user: OrgUser = Depends(require_org_user),
) -> dict[str, Any]:
    """Create or update a device readiness record by device_id + org_id."""
    async with Session() as db:
        # Upsert: find by (device_id, org_id)
        stmt = select(DeviceReadiness).where(
            DeviceReadiness.device_id == payload.device_id,
            DeviceReadiness.org_id == org_user.org_id,
        )
        q = await db.execute(stmt)
        device = q.scalar_one_or_none()

        if device is None:
            device = DeviceReadiness(
                device_id=payload.device_id,
                org_id=org_user.org_id,
                device_name=payload.device_name,
                last_inspection_at=payload.last_inspection_at,
                next_inspection_due=payload.next_inspection_due,
                status=payload.status,
                notes=payload.notes,
            )
            db.add(device)
        else:
            device.device_name = payload.device_name
            device.last_inspection_at = payload.last_inspection_at
            device.next_inspection_due = payload.next_inspection_due
            device.status = payload.status
            device.notes = payload.notes

        await db.commit()
        await db.refresh(device)
        return _device_out(device)


@router.patch("/device-readiness/{device_id_pk}")
async def patch_device_readiness(
    device_id_pk: int,
    payload: DeviceReadinessUpdate,
    org_user: OrgUser = Depends(require_org_user),
) -> dict[str, Any]:
    """Partially update a device readiness record by primary key."""
    async with Session() as db:
        q = await db.execute(
            select(DeviceReadiness).where(DeviceReadiness.id == device_id_pk)
        )
        device = q.scalar_one_or_none()
        if not device:
            raise HTTPException(status_code=404, detail="Device readiness record not found")

        if org_user.org_id is not None and device.org_id != org_user.org_id:
            raise HTTPException(status_code=403, detail="Not authorized")

        if payload.device_name is not None:
            device.device_name = payload.device_name
        if payload.last_inspection_at is not None:
            device.last_inspection_at = payload.last_inspection_at
        if payload.next_inspection_due is not None:
            device.next_inspection_due = payload.next_inspection_due
        if payload.status is not None:
            device.status = payload.status
        if payload.notes is not None:
            device.notes = payload.notes

        await db.commit()
        await db.refresh(device)
        return _device_out(device)


@router.delete("/device-readiness/{device_id_pk}", status_code=204)
async def delete_device_readiness(
    device_id_pk: int,
    org_user: OrgUser = Depends(require_org_user),
) -> None:
    """Delete a device readiness record by primary key."""
    async with Session() as db:
        q = await db.execute(
            select(DeviceReadiness).where(DeviceReadiness.id == device_id_pk)
        )
        device = q.scalar_one_or_none()
        if not device:
            raise HTTPException(status_code=404, detail="Device readiness record not found")

        if org_user.org_id is not None and device.org_id != org_user.org_id:
            raise HTTPException(status_code=403, detail="Not authorized")

        await db.delete(device)
        await db.commit()
