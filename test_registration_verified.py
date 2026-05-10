import os
import django
import json
import urllib.request
import time

# -----------------------------------------------------------------------------
# 1. Setup Django (for Cleanup)
# -----------------------------------------------------------------------------
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from apps.authentication.models import UnifiedUser

VERIFIED_PHONE = "+2349137654300" 
BASE_URL = "http://127.0.0.1:8001/api"

def cleanup_user():
    print(f"Cleaning up user with phone {VERIFIED_PHONE}...")
    try:
        user = UnifiedUser.objects.filter(phone=VERIFIED_PHONE).first()
        if user:
            user.delete() # Hard delete (or soft depending on mixin, but getting it out of the way)
            print("User deleted.")
        else:
            print("User not found, clean.")
    except Exception as e:
        print(f"Cleanup failed: {e}")

# -----------------------------------------------------------------------------
# 2. Test Execution
# -----------------------------------------------------------------------------
def make_request(url, data):
    print(f"Requesting: {url}")
    try:
        req = urllib.request.Request(
            url, 
            data=json.dumps(data).encode('utf-8'), 
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req) as f:
            return f.getcode(), f.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8')
    except Exception as e:
        return 0, str(e)

if __name__ == "__main__":
    cleanup_user()
    
    timestamp = int(time.time())

    # Payload using Verified Phone
    user_payload = {
        "phone": VERIFIED_PHONE,
        "password": "Password123!",
        "password2": "Password123!", # DRF
        "password_confirm": "Password123!", # Ninja
        "role": "client"
    }

    print("\n--- TEST: V1 SYNC REGISTRATION (VERIFIED PHONE) ---")
    # We use V1 or V2? Let's test V2 (Async/Ninja) as it's the newer one, 
    # but V1 is also fine. Let's do V2.
    
    code, body = make_request(f"{BASE_URL}/v2/auth/register", user_payload)
    print(f"V2 Verified Phone: {code}")
    print(body)
    
    if code == 201:
        print("SUCCESS: Registration with verified phone worked!")
    else:
        print("FAILED: Registration failed.")

