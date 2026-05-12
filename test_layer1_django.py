import os
import django
import sys
from pprint import pprint

# Setup Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.development")
django.setup()

from rest_framework.test import APIClient
from apps.authentication.models import UnifiedUser
from django.core.cache import cache
import uuid

from unittest.mock import patch

def run_tests():
    # Mock OTP so we predictably know it's 123456
    patcher = patch("apps.common.utils.generate_numeric_otp", return_value="123456")
    patcher.start()

    client = APIClient()
    email = f"curltest_{uuid.uuid4().hex[:6]}@fashionistar.io"
    phone = "+1800555" + str(uuid.uuid4().int)[:4]
    password = "StrongPassword#2026"
    
    print("\n1. Health Check")
    r = client.get("/api/v1/health/")
    import json
    try: data = r.json()
    except: data = json.loads(r.content)
    print(r.status_code, data)
    assert r.status_code == 200

    print("\n2. Register")
    r = client.post("/api/v1/auth/register/", {
        "email": email,
        "phone_number": phone,
        "password": password,
        "password2": password,
        "first_name": "Curl",
        "last_name": "Test",
        "role": "client"
    }, format="json")
    try: data = r.json()
    except: data = json.loads(r.content)
    print(r.status_code, data)
    if r.status_code != 201:
        print("REGISTER FAILED WITH DATA:")
        import json
        print(json.dumps(data, indent=2))
        return
    assert r.status_code == 201
    
    print("\n3. Login (Unverified)")
    r = client.post("/api/v1/auth/login/", {"email_or_phone": email, "password": password}, format="json")
    try: data = r.json()
    except: data = json.loads(r.content)
    print(r.status_code, data)
    assert r.status_code == 403
    assert "account_not_verified" in data.get("code", "")
    assert "resend-otp" in data.get("message", "")
    
    print("\n4. Resend OTP")
    r = client.post("/api/v1/auth/resend-otp/", {"email_or_phone": email}, format="json")
    try: data = r.json()
    except: data = json.loads(r.content)
    print(r.status_code, data)
    assert r.status_code == 200
    
    otp = "123456"
    print(f"-> Using Predictable Mocked OTP: {otp}")
    
    print("\n5. Verify OTP")
    r = client.post("/api/v1/auth/verify-otp/", {"otp": otp}, format="json")
    print(r.status_code)
    # Don't print full tokens to avoid terminal spam
    assert r.status_code == 200
    
    print("\n6. Login (Verified)")
    r = client.post("/api/v1/auth/login/", {"email_or_phone": email, "password": password}, format="json")
    print(r.status_code)
    try: data = r.json()
    except: data = json.loads(r.content)
    assert r.status_code == 200
    access = data["data"]["access"]
    refresh = data["data"]["refresh"]
    
    print("\n7. Token Refresh")
    r = client.post("/api/v1/auth/token/refresh/", {"refresh": refresh}, format="json")
    try: data = r.json()
    except: data = json.loads(r.content)
    print(r.status_code, data)
    assert r.status_code == 200
    
    # Handle possible rotation of refresh token
    new_access = data.get("access", data.get("data", {}).get("access", access))
    new_refresh = data.get("refresh", data.get("data", {}).get("refresh", refresh))
    
    print("\n8. Logout")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {new_access}")
    r = client.post("/api/v1/auth/logout/", {"refresh": new_refresh}, format="json")
    try: data = r.json()
    except: data = json.loads(r.content)
    print(r.status_code, data)
    assert r.status_code == 200
    
    print("\n9. Change Password (requires re-login first)")
    r_login = client.post("/api/v1/auth/login/", {"email_or_phone": email, "password": password}, format="json")
    try: data_login = r_login.json()
    except: data_login = json.loads(r_login.content)
    access_for_pwd = data_login.get("access", data_login.get("data", {}).get("access"))
    
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_for_pwd}")
    r = client.post("/api/v1/password/change/", {
        "old_password": password,
        "new_password": "New!Password#2026",
        "confirm_password": "New!Password#2026"
    }, format="json")
    try: data = r.json()
    except: data = json.loads(r.content)
    print(r.status_code, data)
    assert r.status_code == 200
    
    client.credentials() # clear credentials
    
    print("\n10. Password Reset Request")
    r = client.post("/api/v1/password/reset-request/", {"email_or_phone": email}, format="json")
    try: data = r.json()
    except: data = json.loads(r.content)
    print(r.status_code, data)
    assert r.status_code == 200
    
    print("\n11. Password Reset Phone Confirm (Bad OTP)")
    r = client.post("/api/v1/password/reset-phone-confirm/", {
        "email_or_phone": email,
        "otp": "999999", # wrong
        "password": "YetAnother!Password#2026",
        "password2": "YetAnother!Password#2026"
    }, format="json")
    try: data = r.json()
    except: data = json.loads(r.content)
    print(r.status_code, data)
    assert r.status_code == 400
    assert "resend_otp" in data.get("errors", {}).get("actions", {})
    
    print("\n12. Password Reset Email Confirm (Bad Token)")
    r = client.post("/api/v1/password/reset-confirm/MTA/bad-token/", {
        "password": "YetAnother!Password#2026",
        "password2": "YetAnother!Password#2026"
    }, format="json")
    try: data = r.json()
    except: data = json.loads(r.content)
    print(r.status_code, data)
    assert r.status_code == 400
    assert "forgot_password_page" in data.get("errors", {}).get("actions", {})

    print("\n13. Presign Upload (Auth Required)")
    # Must login again with new password
    # Sleep to avoid auth_burst rate limit (Retry-After: 5.5s)
    import time
    time.sleep(6)
    r_login2 = client.post("/api/v1/auth/login/", {"email_or_phone": email, "password": "New!Password#2026"}, format="json")
    try: data_login = r_login2.json()
    except: data_login = json.loads(r_login2.content)
    access2 = data_login["data"]["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access2}")
    
    r = client.post("/api/v1/upload/presign/", {"asset_type": "avatar"}, format="json")
    print(r.status_code)
    assert r.status_code == 200
    
    print("\n14. Cloudinary Webhook (Bad Signature)")
    client.credentials() # clear auth
    r = client.post("/api/v1/upload/webhook/cloudinary/", {}, format="json", HTTP_X_CLD_SIGNATURE="badsig")
    try: data = r.json()
    except: data = json.loads(r.content)
    print(r.status_code, data)
    assert r.status_code == 200
    assert data.get("status") == "rejected"

    print("\n=== LAYER 1 TESTING COMPLETE ===")

if __name__ == "__main__":
    run_tests()
