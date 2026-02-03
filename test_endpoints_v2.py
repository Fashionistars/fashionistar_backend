import urllib.request
import json
import time

BASE_URL = "http://127.0.0.1:8000/api/v2/auth"

def make_request(endpoint, data):
    url = f"{BASE_URL}{endpoint}"
    print(f"Requesting: {url}")
    req = urllib.request.Request(
        url, 
        data=json.dumps(data).encode('utf-8'), 
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        with urllib.request.urlopen(req) as f:
            return f.getcode(), f.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8')
    except Exception as e:
        return 0, str(e)

# Only test Register and Resend (Verify without real OTP is trivial 400 check)
timestamp = int(time.time())
email = f"test_{timestamp}@example.com"
phone = f"+234{timestamp}" # Valid phone format usually needed
if len(phone) > 15: phone = phone[:15]

print("--- START TESTS ---")

print("Testing Register...")
status, resp = make_request("/register", {
    "email": email,
    # "phone": phone, # Cannot send both
    "password": "Password123!",
    "password_confirm": "Password123!",
    "role": "client"
})
print(f"Status: {status}\nResponse: {resp}")

if status == 201:
    print("\nTesting Resend...")
    resend_status, resend_resp = make_request("/resend-otp", {"email_or_phone": email})
    print(f"Status: {resend_status}\nResponse: {resend_resp}")

    print("\nTesting Verify (Invalid)...")
    try:
        uid = json.loads(resp)['user_id']
        v_status, v_resp = make_request("/verify-otp", {"user_id": uid, "otp": "123456"})
        print(f"Status: {v_status}\nResponse: {v_resp}")
    except:
        print("Could not parse user_id")
else:
    print("Skipping dependent tests due to registration failure.")

print("--- END TESTS ---")
