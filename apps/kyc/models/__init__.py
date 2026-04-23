# apps/kyc/models/__init__.py
"""
KYC Models — SCAFFOLD (not yet in INSTALLED_APPS).
"""
from apps.kyc.models.kyc_submission import KycSubmission
from apps.kyc.models.kyc_document import KycDocument

__all__ = ["KycSubmission", "KycDocument"]
