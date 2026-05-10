import urllib.request
import json
import time

BASE_URL = "http://127.0.0.1:8001/api"

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

timestamp = int(time.time())

# Test Data
user_v1_email = {
    "email": f"sync_email_{timestamp}@example.com",
    "password": "Password123!",
    "password2": "Password123!", # DRF Serializer field
    "role": "client"
}
user_v1_phone = {
    "phone": f"+234803{timestamp % 10000000:07d}", # Standard NG mobile format
    "password": "Password123!",
    "password2": "Password123!",
    "role": "client"
}

user_v2_email = {
    "email": f"async_email_{timestamp}@example.com",
    "password": "Password123!",
    "password_confirm": "Password123!", # Pydantic Schema field
    "role": "client"
}

user_v2_phone = {
    "phone": f"+234813{timestamp % 10000000:07d}",
    "password": "Password123!",
    "password_confirm": "Password123!",
    "role": "client"
}

user_invalid_mixed = {
    "email": f"mixed_{timestamp}@example.com",
    "phone": f"+23490{timestamp}",
    "password": "Password123!",
    "password_confirm": "Password123!",
    "role": "client"
}

print("\n--- TEST: V1 SYNC REGISTRATION (DRF) ---")
# 1. Email Success
code, body = make_request(f"{BASE_URL}/v1/auth/register/", user_v1_email)
print(f"V1 Email: {code} (Expect 201)")
if code != 201: print(body)

# 2. Phone Success
code, body = make_request(f"{BASE_URL}/v1/auth/register/", user_v1_phone)
print(f"V1 Phone: {code} (Expect 201)")
if code != 201: print(body)

# 3. Duplicate Failure
code, body = make_request(f"{BASE_URL}/v1/auth/register/", user_v1_email)
print(f"V1 Duplicate: {code} (Expect 400)")


print("\n--- TEST: V2 ASYNC REGISTRATION (NINJA) ---")
# 1. Email Success
code, body = make_request(f"{BASE_URL}/v2/auth/register", user_v2_email)
print(f"V2 Email: {code} (Expect 201)")
if code != 201: print(body)

# 2. Phone Success
code, body = make_request(f"{BASE_URL}/v2/auth/register", user_v2_phone)
print(f"V2 Phone: {code} (Expect 201)")
if code != 201: print(body)

# 3. Validation Failure (Mixed)
code, body = make_request(f"{BASE_URL}/v2/auth/register", user_invalid_mixed)
print(f"V2 Mixed (Invalid): {code} (Expect 422)")
if code != 422: print(body)

print("\n--- TEST COMPLETE ---")
