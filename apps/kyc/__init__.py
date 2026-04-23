# apps/kyc/__init__.py
"""
KYC (Know Your Customer) Compliance Domain — Future Sprint Scaffold.

This package is NOT yet in INSTALLED_APPS.
It is scaffolded here so the file structure, interfaces, and contracts
are defined early, enabling frontend/backend teams to prepare in parallel.

Activation Checklist (when the KYC sprint begins):
  [ ] Add "apps.kyc" to INSTALLED_APPS in backend/config/base.py
  [ ] Install external KYC provider SDK (e.g. Smile ID, Youverify, Dojah)
  [ ] Set KYC_PROVIDER and KYC_API_KEY in .env
  [ ] Wire kyc.urls into backend/urls.py
  [ ] Register kyc Ninja router in backend/ninja_api.py
  [ ] Run: make mmig app=kyc
  [ ] Run: make mig app=kyc
  [ ] Update VendorSetupState.id_verified → True on KYC approval webhook

Architecture Decision:
  The KYC domain is intentionally separated from the vendor and client domains
  to keep compliance logic isolated. KYC is a cross-cutting concern:
    - Vendors need government ID + business registration verification
    - Clients may need identity verification for high-value transactions
    - Future: CAC (Corporate Affairs Commission) checks for Nigerian businesses
"""
