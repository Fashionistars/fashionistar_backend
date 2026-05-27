# apps/kyc/admin_backend/schemas.py
"""Django Ninja schemas for KYC admin API."""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class AdminKYCDocumentSchema(BaseModel):
    id: str
    document_type: str
    status: Optional[str] = None
    created_at: datetime
    class Config:
        from_attributes = True


class AdminKYCSubmissionListSchema(BaseModel):
    id: str
    user_id: str
    user_email: Optional[str] = None
    user_member_id: Optional[str] = None
    status: str
    legal_name: Optional[str] = None
    review_notes: Optional[str] = None
    provider_reference: Optional[str] = None
    submitted_at: datetime
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    class Config:
        from_attributes = True


class AdminKYCSubmissionDetailSchema(AdminKYCSubmissionListSchema):
    documents: list[AdminKYCDocumentSchema] = []


class AdminKYCStatsSchema(BaseModel):
    pending: int
    in_review: int
    approved: int
    rejected: int
    new_today: int
    total: int


class AdminKYCApproveSchema(BaseModel):
    legal_name: Optional[str] = None


class AdminKYCRejectSchema(BaseModel):
    notes: str
    allow_resubmit: bool = True


class AdminKYCActionResponse(BaseModel):
    success: bool = True
    message: str
    submission_id: Optional[str] = None
