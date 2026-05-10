import urllib.request
import urllib.error
import urllib.parse
import json

base_url = 'http://127.0.0.1:8000'

def test_endpoint(name, url, method="GET", data=None, headers=None, expected_status=200):
    if headers is None:
        headers = {}
    
    req_data = None
    if data:
        req_data = json.dumps(data).encode('utf-8')
        headers['Content-Type'] = 'application/json'

    req = urllib.request.Request(url, data=req_data, method=method, headers=headers)
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            status = response.status
            body_preview = response.read(150).decode('utf-8', errors='replace').replace('\n', ' ')
            result = "✅ PASS" if status == expected_status else f"❌ FAIL (Got {status}, want {expected_status})"
            print(f"{result} - {name} ({method} {url})")
            print(f"  HTTP {status} | body snippet: {body_preview}...")
            return status == expected_status
    except urllib.error.HTTPError as e:
        status = e.code
        body_preview = e.read(150).decode('utf-8', errors='replace').replace('\n', ' ')
        result = "✅ PASS" if status == expected_status else f"❌ FAIL (Got {status}, want {expected_status})"
        print(f"{result} - {name} ({method} {url})")
        print(f"  HTTP {status} | Error snippet: {body_preview}...")
        return status == expected_status
    except Exception as e:
        print(f"❌ ERROR - {name} | {str(e)}")
        return False

print("\n" + "="*50)
print(" STRESS TESTS CONFIGURATION:")
print(" 1. DJANGO ADMIN UI")
print(" 2. CURL API TEST")
print(" 3. RAPIDAPI EXTENSION (Simulated via JSON POST)")
print(" 4. SWAGGER DOCS UI")
print(" 5. DRF BROWSABLE API")
print("="*50 + "\n")

# 1. Django Admin UI
test_endpoint(
    "1. DJANGO ADMIN UI: GET /admin/login/",
    f"{base_url}/admin/login/",
    method="GET",
    expected_status=200
)

# 2. CURL API TEST (Simulating pure curl terminal request)
test_endpoint(
    "2. CURL TEST: POST /api/v1/auth/login/ with valid credentials",
    f"{base_url}/api/v1/auth/login/",
    method="POST",
    data={"email_or_phone": "admin@fashionistar.io", "password": "FashionAdmin2026!"},
    expected_status=200
)

# 3. RapidAPI Testing Environment Simulation (JSON with extra generic headers)
test_endpoint(
    "3. RAPIDAPI EXTENSION: Missing credentials error handling",
    f"{base_url}/api/v1/auth/login/",
    method="POST",
    headers={"User-Agent": "RapidAPI/1.0", "Accept": "application/json"},
    data={"email_or_phone": "admin@fashionistar.io"},
    expected_status=400
)

# 4. SWAGGER TESTING
test_endpoint(
    "4. SWAGGER DOCS: GET /swagger/",
    f"{base_url}/swagger/",
    method="GET",
    headers={"Accept": "text/html"},
    expected_status=200
)

# 5. NORMAL DRF BROWSER TESTING UI
test_endpoint(
    "5. DRF BROWSER UI: GET /api/v1/auth/login/",
    f"{base_url}/api/v1/auth/login/",
    method="GET",
    headers={"Accept": "text/html,application/xhtml+xml"},
    expected_status=405  # GET is not allowed on the login endpoint, it renders the 405 error page in DRF standard HTML if browsable API is on.
)

print("\n" + "="*50)
print(" ALL TESTS COMPLETED")
print("="*50 + "\n")
