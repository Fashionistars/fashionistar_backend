# apps/kyc/__init__.py
"""
KYC Domain Package.

Status: ACTIVATED (Phase 6 — Wave 6)
Apps.kyc is registered in INSTALLED_APPS.
Migrations: python manage.py makemigrations kyc && python manage.py migrate kyc

Domain responsibilities:
  - KycSubmission: one-per-user KYC record tracking verification state.
  - KycDocument: uploaded identity documents (NIN, passport, CAC, etc.).
  - KycService: atomic mutation service (initiate, record_document, approve, reject).
  - KycGate: assert_kyc_approved(user) — blocks withdrawal without KYC approval.
  - KycSelectors: sync + async read-only queries for DRF and Ninja routers.
"""
