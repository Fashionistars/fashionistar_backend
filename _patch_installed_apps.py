"""Patch base.py: add apps.kyc to INSTALLED_APPS and update kyc __init__.py."""

# ── Patch INSTALLED_APPS ──────────────────────────────────────────────────────
with open("backend/config/base.py", "r", encoding="utf-8") as f:
    content = f.read()

if "apps.kyc" in content:
    print("INSTALLED_APPS: ALREADY PATCHED")
else:
    old = '        "apps.support",        # Phase 5 (P2): Customer dispute & ticket management domain'
    new = (
        '        "apps.support",        # Phase 5 (P2): Customer dispute & ticket management domain\n'
        '        "apps.kyc",            # Phase 6: Identity verification (KYC) domain'
    )
    if old in content:
        content = content.replace(old, new, 1)
        with open("backend/config/base.py", "w", encoding="utf-8") as f:
            f.write(content)
        print("INSTALLED_APPS: SUCCESS")
    else:
        # Try unicode escape variant
        old2 = '        "apps.support",        # Phase 5 (P2): Customer dispute \u0026 ticket management domain'
        if old2 in content:
            new2 = (
                '        "apps.support",        # Phase 5 (P2): Customer dispute \u0026 ticket management domain\n'
                '        "apps.kyc",            # Phase 6: Identity verification (KYC) domain'
            )
            content = content.replace(old2, new2, 1)
            with open("backend/config/base.py", "w", encoding="utf-8") as f:
                f.write(content)
            print("INSTALLED_APPS: SUCCESS (unicode variant)")
        else:
            # Find by line proximity
            idx = content.find('"apps.support"')
            print(f"NOT FOUND - apps.support at idx={idx}")
            print(repr(content[idx:idx+100]))

# ── Update kyc __init__.py to reflect activation ─────────────────────────────
kyc_init_path = "apps/kyc/__init__.py"
with open(kyc_init_path, "r", encoding="utf-8") as f:
    kyc_init = f.read()

if "ACTIVATED" not in kyc_init:
    new_init = '''# apps/kyc/__init__.py
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
'''
    with open(kyc_init_path, "w", encoding="utf-8") as f:
        f.write(new_init)
    print("KYC __init__: UPDATED")
else:
    print("KYC __init__: ALREADY UPDATED")
