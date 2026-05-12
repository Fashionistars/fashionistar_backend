#!/usr/bin/env python
"""Validation script to verify Cloudinary webhook signature fix."""
import os, sys, hashlib, time
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.config.development')
import django
django.setup()
from django.test import override_settings
from apps.common.utils.cloudinary import validate_cloudinary_webhook

FAKE_CLOUDINARY_STORAGE = {"CLOUD_NAME": "test-cloud", "API_KEY": "test-api-key", "API_SECRET": "test-secret"}

def make_sig(body: bytes, timestamp: str, secret: str) -> str:
    try:
        body_str = body.decode("utf-8")
    except UnicodeDecodeError:
        body_str = body.decode("latin-1")
    payload = (body_str + timestamp + secret).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()

with override_settings(CLOUDINARY_STORAGE=FAKE_CLOUDINARY_STORAGE):
    secret = FAKE_CLOUDINARY_STORAGE["API_SECRET"]
    ts = str(int(time.time()))
    body = b'{"test": "data"}'
    sig = make_sig(body, ts, secret)
    
    print(f"✅ VALIDATION TEST")
    print(f"Secret: {secret}")
    print(f"Timestamp: {ts}")
    print(f"Body: {body}")
    print(f"Signature: {sig}")
    result = validate_cloudinary_webhook(body, ts, sig)
    print(f"Result: {'✅ PASS' if result else '❌ FAIL'}")
    sys.exit(0 if result else 1)
