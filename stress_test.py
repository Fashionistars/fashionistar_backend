import asyncio
import aiohttp
import time
import uuid

# Configuration
ENDPOINT = "http://localhost:8000/api/v1/auth/register/" 
# We'll also test the async Ninja endpoint
NINJA_ENDPOINT = "http://localhost:8000/api/v1/ninja/auth/register"

CONCURRENCY_LEVEL = 1000 # Simulate a burst of 1000 requests 
TOTAL_REQUESTS = 2000

PAYLOADS = [
    {
        "email": "stress_test_atomic_drf@example.com",
        "password": "SecurePassword@2026!",
        "role": "client"
    },
    {
        "email": "stress_test_atomic_ninja@example.com",
        "password": "SecurePassword@2026!",
        "role": "vendor"
    }
]

async def send_request(session, url, payload):
    try:
        start_time = time.time()
        async with session.post(url, json=payload) as response:
            status = response.status
            body = await response.json()
            return status, body, time.time() - start_time
    except Exception as e:
        return 0, str(e), 0

async def perform_stress_test(name, url, payload, concurrency):
    print(f"\n--- Starting Race Condition / Atomic Transaction Test for {name} ---")
    print(f"Target: {url}")
    print(f"Bursting {concurrency} simultaneous asynchronous requests with identical payloads.")
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        for _ in range(concurrency):
            tasks.append(send_request(session, url, payload))
            
        start_burst = time.time()
        results = await asyncio.gather(*tasks)
        end_burst = time.time()
        
    status_counts = {}
    success_responses = []
    error_responses = []
    
    for status, body, duration in results:
        status_counts[status] = status_counts.get(status, 0) + 1
        if status == 201 or status == 200:
            success_responses.append(body)
        else:
            if isinstance(body, dict) and "errors" in body:
                error_responses.append(body.get("errors"))
            else:
                error_responses.append(body)
                
    total_time = end_burst - start_burst
    req_per_sec = concurrency / total_time if total_time > 0 else 0
    
    print("\n[Results]")
    print(f"Total Requests: {concurrency}")
    print(f"Time Taken: {total_time:.2f} seconds")
    print(f"Requests per Second: {req_per_sec:.2f} req/s")
    print("\nStatus Codes Distribution:")
    for code, count in status_counts.items():
        print(f"  HTTP {code}: {count}")
        
    print(f"\nSuccessful Creations (HTTP 201/200): {len(success_responses)}")
    print("If atomic transactions are working correctly, this must be EXACTLY 1.")
    
    if len(success_responses) == 1:
        print("✅ ATOMIC TRANSACTION PASSED: Only 1 user was created despite massive concurrency.")
    elif len(success_responses) == 0:
        print("❌ FAILED: No users were created! Server might be down.")
    else:
        print(f"❌ FAILED: Race condition detected! {len(success_responses)} users created.")
        
    # Check for 500 Server Errors
    has_500s = status_counts.get(500, 0) > 0
    if has_500s:
        print("❌ FAILED: TransactionManagementError or other 500 error occurred!")
    else:
        print("✅ STABILITY PASSED: No 500 Internal Server Errors occurred (savepoint handling works).")
        
    # Idempotency check
    if status_counts.get(400, 0) == concurrency - 1:
        print("✅ IDEMPOTENCY PASSED: All other requests safely rejected as duplicates (HTTP 400).")
    else:
        print("⚠️ NOTE: Some requests failed with non-400 errors (e.g. rate limit, timeouts).")


async def main():
    print("Initializing Stress Test Tool...")
    print("Warming up server with 1 request to clear compile time overhead...")
    
    async with aiohttp.ClientSession() as session:
        await send_request(session, ENDPOINT, PAYLOADS[0])
        await send_request(session, NINJA_ENDPOINT, PAYLOADS[1])
        
    # Slightly modify email to ensure a fresh test
    payload_drf = PAYLOADS[0].copy()
    payload_drf["email"] = f"test_drf_{uuid.uuid4().hex[:6]}@example.com"
    
    payload_ninja = PAYLOADS[1].copy()
    payload_ninja["email"] = f"test_ninja_{uuid.uuid4().hex[:6]}@example.com"
    
    # Run test for DRF endpoint
    await perform_stress_test("DRF Sync API", ENDPOINT, payload_drf, CONCURRENCY_LEVEL)
    
    # Short wait before slamming the next endpoint
    await asyncio.sleep(2)
    
    # Run test for Ninja async endpoint
    await perform_stress_test("Ninja Async API", NINJA_ENDPOINT, payload_ninja, CONCURRENCY_LEVEL)


if __name__ == "__main__":
    asyncio.run(main())
