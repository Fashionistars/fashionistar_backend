#!/usr/bin/env python
"""
Debug script to understand Cloudinary webhook signature validation.

This script tests multiple possible signature algorithms to identify which one
Cloudinary is actually using for webhook notifications.
"""

import os
import sys
import json
import hmac
import hashlib

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.config.development')
import django
django.setup()

from django.conf import settings

# Real values from the logs
RECEIVED_SIG = "902e4e0b1d25819b4545987c68be4c7b1bb03151"  # From logs
TIMESTAMP = "1774013483"
BODY_LEN = 2293
BODY_START = '{"notification_type":"upload","timestamp":"2026-03-20T13:04:15+00:00","request_id":"92bc214420fac11f5ba43a908878a450",'

API_SECRET = settings.CLOUDINARY_STORAGE.get("API_SECRET", "")

print("=" * 100)
print("CLOUDINARY WEBHOOK SIGNATURE DIAGNOSIS")
print("=" * 100)
print(f"\nKnown Values:")
print(f"  Received Signature: {RECEIVED_SIG}")
print(f"  Timestamp: {TIMESTAMP}")
print(f"  Body Length: {BODY_LEN} bytes")
print(f"  Body Start: {BODY_START[:60]}...")
print(f"  API Secret: {API_SECRET[:10]}***{API_SECRET[-5:] if len(API_SECRET) > 15 else ''}")
print()

# Test different signature algorithms
test_cases = [
    ("1. HMAC-SHA1(body only)", lambda body: hmac.new(API_SECRET.encode(), body, hashlib.sha1).hexdigest()),
    ("2. HMAC-SHA256(body only)", lambda body: hmac.new(API_SECRET.encode(), body, hashlib.sha256).hexdigest()),
    ("3. HMAC-SHA1(body as string)", lambda body: hmac.new(API_SECRET.encode(), body.decode('utf-8', errors='replace').encode(), hashlib.sha1).hexdigest()),
    ("4. HMAC-SHA1(body + timestamp)", lambda body: hmac.new(API_SECRET.encode(), body + TIMESTAMP.encode(), hashlib.sha1).hexdigest()),
    ("5. HMAC-SHA1(timestamp + body)", lambda body: hmac.new(API_SECRET.encode(), TIMESTAMP.encode() + body, hashlib.sha1).hexdigest()),
    ("6. SHA1(body)", lambda body: hashlib.sha1(body).hexdigest()),
    ("7. SHA256(body)", lambda body: hashlib.sha256(body).hexdigest()),
]

# Create a test body (we'll use simulated data)
test_body = BODY_START.encode('utf-8')

print("Testing Signature Algorithms:")
print("-" * 100)

for name, algo_func in test_cases:
    try:
        generated_sig = algo_func(test_body)
        match = generated_sig.lower() == RECEIVED_SIG.lower()
        
        status = "✅ MATCH!" if match else "❌ no match"
        print(f"\n{name}")
        print(f"  Generated: {generated_sig[:40]}...")
        print(f"  Length: {len(generated_sig)}")
        print(f"  Status: {status}")
        
    except Exception as e:
        print(f"\n{name}")
        print(f"  ERROR: {e}")

print("\n" + "=" * 100)
print("\nKEY INSIGHTS:")
print("  - Length 40 = SHA1")
print("  - Length 64 = SHA256")
print("  - If no match found, body format or secret might be wrong")
print("=" * 100)
