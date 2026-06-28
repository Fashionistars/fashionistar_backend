"""Patch backend/urls.py to add KYC URL mount."""

with open("backend/urls.py", "r", encoding="utf-8") as f:
    content = f.read()

KYC_LINE = '    # \u2500\u2500 Phase 6: Identity Verification (KYC) Domain \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n    path("api/v1/kyc/", include("apps.kyc.urls", namespace="kyc")),\n'

# Check if already patched
if 'apps.kyc.urls' in content:
    print("ALREADY PATCHED")
else:
    # Find the Ninja API line and insert KYC before it
    target = '    # \u2500\u2500 Phase 2: Central Async Ninja API'
    idx = content.find(target)
    if idx == -1:
        print("TARGET NOT FOUND")
        print(repr(content[5500:5700]))
    else:
        new_content = content[:idx] + KYC_LINE + content[idx:]
        with open("backend/urls.py", "w", encoding="utf-8") as f:
            f.write(new_content)
        print("SUCCESS")
