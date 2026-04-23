# apps/kyc/admin.py
"""
KYC Domain Admin — SCAFFOLD (not yet in INSTALLED_APPS).

When activated, provides:
  - Full KycSubmission list with status badges
  - Inline KycDocument viewer (never deletes originals)
  - Bulk approve / reject / request-resubmission actions
  - Triggers VendorSetupState.id_verified update on approval
"""
# from django.contrib import admin
# from apps.kyc.models import KycSubmission, KycDocument
#
# Uncomment when "apps.kyc" is added to INSTALLED_APPS.
