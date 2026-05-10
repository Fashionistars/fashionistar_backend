# Cloudinary Webhook HMAC Signature Fix — Implementation Plan

**Date:** March 20, 2026  
**Version:** 1.0  
**Status:** In Progress  
**Owner:** Backend Engineering Team

---

## 🎯 Executive Summary

### Problem
Cloudinary webhook notifications are being **rejected due to HMAC signature mismatch**:
- Cloudinary sends **SHA1** signatures (per API standard)
- Current code attempts **SHA256** validation
- Result: **0% webhook success rate** ❌

### Root Cause Analysis
From production logs:
```
⚠️ Cloudinary webhook SIG MISMATCH
received=a37e2e87641d894845ca415d75134b47074e1e59 (len=40 — SHA1 output)
sha256=579a75fb5099d93af56147c7b3037b92efbf23b0813eb53100e4fe5b8c65e7a4 ✗
body_len=1589 | timestamp=1774011535
```

The received signature is **exactly 40 characters** (SHA1), but we're comparing to SHA256 (64 chars).

### Solution
1. **Use SHA1** for webhook signature validation (Cloudinary standard)
2. **Add timestamp validation** (7200s max age for replay protection)
3. **Use constant-time comparison** to prevent timing attacks
4. **Add comprehensive test coverage** (unit + integration + load)

---

## 📋 Phase 1: Code Changes

### 1.1 Fix `apps/common/utils/cloudinary.py`

**File:** `apps/common/utils/cloudinary.py`  
**Function:** `validate_cloudinary_webhook()`  
**Change:** Update to use SHA1 instead of SHA256

**Current Implementation (BROKEN):**
```python
# Uses SDK method which falls back to SHA256
# This is incorrect per Cloudinary docs
```

**New Implementation (FIXED):**
```python
def validate_cloudinary_webhook(
    body: bytes,
    timestamp: str,
    signature: str,
    *,
    max_age_seconds: int = 7200,
) -> bool:
    """
    Validate Cloudinary webhook HMAC-SHA1 signature.
    
    ⚠️ CRITICAL DETAIL: Cloudinary uses SHA1 (not SHA256)
    Per official docs: https://cloudinary.com/documentation/notifications_api
    
    Args:
        body: Raw HTTP request body (bytes)
        timestamp: X-Cld-Timestamp header value
        signature: X-Cld-Signature header value (hex string, 40 chars for SHA1)
        max_age_seconds: Reject webhooks older than this (default 7200s)
    
    Returns:
        True if signature is valid AND timestamp is fresh
    """
    import hashlib
    import hmac
    import time
    
    if not timestamp or not signature:
        logger.warning("Cloudinary webhook: missing timestamp or signature")
        return False
    
    api_secret = settings.CLOUDINARY_STORAGE.get("API_SECRET", "")
    if not api_secret:
        logger.error("Cloudinary webhook: API_SECRET not configured")
        return False
    
    # ── Step 1: Timestamp validation (replay protection) ──────────────────
    try:
        webhook_timestamp = int(timestamp)
        current_time = int(time.time())
        age_seconds = current_time - webhook_timestamp
        
        if age_seconds < 0:
            logger.warning(
                "Cloudinary webhook: timestamp is in the future (clock skew). "
                "age=%ds", age_seconds
            )
            return False
        
        if age_seconds > max_age_seconds:
            logger.warning(
                "Cloudinary webhook: expired. age=%ds (max=%ds)",
                age_seconds, max_age_seconds
            )
            return False
            
    except (ValueError, TypeError) as exc:
        logger.error("Cloudinary webhook: invalid timestamp '%s': %s", timestamp, exc)
        return False
    
    # ── Step 2: Generate expected signature (SHA1) ────────────────────────
    # Cloudinary formula: HMAC-SHA1(raw_body, api_secret)
    # Reference: https://cloudinary.com/documentation/notifications_api#signed_notifications
    expected_signature = hmac.new(
        api_secret.encode("utf-8"),
        body,
        hashlib.sha1,  # ← KEY FIX: Use SHA1, not SHA256
    ).hexdigest()
    
    # ── Step 3: Compare signatures (constant-time to prevent timing attacks) ──
    signature_valid = hmac.compare_digest(
        expected_signature.lower(),
        signature.lower()
    )
    
    if not signature_valid:
        logger.warning(
            "Cloudinary webhook SIG MISMATCH — "
            "received=%s | expected=%s | body_len=%d | timestamp=%s",
            signature[:20], expected_signature[:20], len(body), timestamp
        )
        return False
    
    logger.info(
        "✅ Cloudinary webhook signature VALID: timestamp=%s age=%ds",
        timestamp, age_seconds
    )
    return True
```

### 1.2 Verify `apps/common/views.py` (No changes needed)

The webhook view is already correctly implemented:
- ✅ Correctly extracts `X-Cld-Timestamp` header
- ✅ Correctly extracts `X-Cld-Signature` header
- ✅ Returns 200 status for both valid and invalid signatures (prevents retry storms)
- ✅ Dispatches Celery task for async processing

**No changes required to views.py**

---

## 📊 Phase 2: Comprehensive Testing

### 2.1 Unit Tests

**File:** `tests/test_cloudinary_webhook.py`  
**Tests:**
- ✅ Valid SHA1 signature passes validation
- ✅ Invalid signature rejected
- ✅ Expired timestamp rejected
- ✅ Future timestamp rejected (clock skew)
- ✅ Missing API_SECRET handled gracefully

### 2.2 Integration Tests

**File:** `tests/integration/test_cloudinary_webhook_flow.py`  
**Tests:**
- ✅ Full upload flow: Presign → Upload → Webhook → DB update
- ✅ Multiple webhooks processed in parallel
- ✅ Idempotency: duplicate webhook processed correctly

### 2.3 Load Tests (100K+ requests/sec)

**File:** `tests/stress/stress_cloudinary_webhooks.py`  
**Tests:**
- ✅ 100K concurrent webhook signatures generated + validated
- ✅ Race condition testing with database transactions
- ✅ Memory usage under sustained load

### 2.4 Manual Testing

```bash
# 1. Start dev server with tunnel
make dev-tunnel
make ngrok-dev

# 2. Open test HTML page
open http://127.0.0.1:5502/fashionistar_backend/templates/test_cloudinary_upload.html

# 3. Paste JWT token and click "Start Upload Test"
# Expected: Avatar URL persisted in database within 15 seconds

# 4. Check Django logs for success message:
# [INFO] ✅ Cloudinary webhook signature VALID: timestamp=...
# [INFO] Cloudinary webhook: saved user_avatar=...
```

### 2.5 cURL Testing

```bash
#!/bin/bash
# Generate test payload
PAYLOAD='{"notification_type":"upload","public_id":"test_image","secure_url":"https://res.cloudinary.com/test.jpg"}'

# Get timestamp and generate SHA1 signature
TIMESTAMP=$(date +%s)
SIGNATURE=$(echo -n "$PAYLOAD" | openssl dgst -sha1 -hmac "YOUR_API_SECRET" | sed 's/^.* //')

# Send webhook
curl -X POST http://localhost:8000/api/v1/upload/webhook/cloudinary/ \
  -H "Content-Type: application/json" \
  -H "X-Cld-Timestamp: $TIMESTAMP" \
  -H "X-Cld-Signature: $SIGNATURE" \
  -d "$PAYLOAD" \
  -v

# Expected response: {"status": "received"}
```

---

## 🚀 Phase 3: Testing Criteria Checklist

### 3.1 Curl API Endpoint Testing
- [ ] Valid signature accepted
- [ ] Invalid signature rejected with 200 (no retry)
- [ ] Expired timestamp rejected
- [ ] Missing headers handled gracefully

### 3.2 Admin Panel Testing
- [ ] Avatar URL appears in UnifiedUser admin after webhook
- [ ] No duplicate avatars (idempotency)
- [ ] Correct folder path (fashionistar/users/avatars/user_*)

### 3.3 Swagger UI Testing
- [ ] Presign endpoint returns valid parameters
- [ ] Webhook endpoint accepts POST requests
- [ ] Health check returns "healthy" status

### 3.4 DRF Browser Testing
- [ ] Presign endpoint shows authentication requirement
- [ ] Correct response format for presign
- [ ] Clear error messages for invalid requests

### 3.5 RapidAPI Client Testing
- [ ] Full upload flow succeeds
- [ ] Avatar updates within 15 seconds
- [ ] No timeout errors in webhook processing

---

## 🧪 Phase 4: Concurrency & Race Condition Tests

### 4.1 Idempotency Testing
- Send same webhook payload 5 times
- Verify avatar URL is only updated once (no duplicates)

### 4.2 Race Condition Testing
- Send 100 webhooks for same user simultaneously
- Verify all signatures validate
- Verify final database state is correct (no orphaned records)

### 4.3 Database Transaction Atomicity
- Wrap webhook processing in `transaction.atomic()`
- Rollback webhook if subsequent processing fails
- Verify no partial updates persist

### 4.4 Load Test: 100K Requests/Sec

```bash
uv run pytest tests/stress/stress_cloudinary_webhooks.py -v --tb=short -k "100k"
```

Expected metrics:
- **Webhook validation latency:** < 5ms per request
- **Memory usage:** < 500MB for 100K requests
- **CPU:** < 40% per core
- **Success rate:** 100%
- **Race conditions:** 0

---

## 📝 Phase 5: Monitoring & Rollback

### 5.1 Post-Deployment Monitoring

Add these logs to production dashboard:
- Count of valid webhook signatures per hour
- Count of rejected signatures (monitor for attacks)
- Webhook processing latency (target: < 100ms)
- Avatar update success rate (target: > 99.5%)

### 5.2 Rollback Plan

If production issues occur:

```bash
# Step 1: Revert to previous version
git revert HEAD

# Step 2: Restart all services
docker-compose restart web celery

# Step 3: Disable Cloudinary webhooks temporarily
# (set CLOUDINARY_NOTIFICATION_URL to empty string in .env)

# Step 4: Investigate and fix
# (run tests locally before redeployment)
```

---

## 📦 Files Modified

| File | Changes | Lines |
|------|---------|-------|
| `apps/common/utils/cloudinary.py` | SHA1 signature validation | ~80 |
| `tests/test_cloudinary_webhook.py` | Unit tests (NEW) | ~200 |
| `tests/integration/test_cloudinary_webhook_flow.py` | Integration tests (NEW) | ~150 |
| `tests/stress/stress_cloudinary_webhooks.py` | Load tests (NEW) | ~300 |

---

## ✅ Success Criteria

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| Webhook validation success rate | 0% | 100% | ⏳ |
| Avatar URL persistence | 0% | 100% | ⏳ |
| Signature validation latency | — | < 5ms | ⏳ |
| Concurrent webhook capacity | — | 100K/s | ⏳ |
| Race condition occurrences | — | 0 | ⏳ |
| Atomic transaction rollback | — | 100% | ⏳ |

---

## 🚀 Deployment Timeline

| Phase | Duration | Owner |
|-------|----------|-------|
| Code changes | 30 min | Backend |
| Unit testing | 15 min | QA |
| Integration testing | 30 min | QA |
| Load testing | 45 min | Performance |
| Staging deployment | 15 min | DevOps |
| Staging validation | 30 min | QA |
| Production deployment | 10 min | DevOps |
| Post-deploy monitoring | 60 min (ongoing) | SRE |

**Total Time:** ~3.5 hours

---

## 📞 Contact & Support

- **Backend Lead:** [Contact info]
- **On-call:** [Contact info]
- **Escalation:** [Contact info]

---

## 📚 References

- [Cloudinary Webhook Documentation](https://cloudinary.com/documentation/notifications_api)
- [HMAC-SHA1 RFC 2104](https://tools.ietf.org/html/rfc2104)
- [Django Transactions & Atomicity](https://docs.djangoproject.com/en/6.0/topics/db/transactions/)
- [Celery Task Best Practices](https://docs.celery.io/en/stable/getting-started/first-steps-with-celery.html)

---

**Document Version:** 1.0  
**Last Updated:** 2026-03-20 14:05:00 UTC  
**Status:** READY FOR IMPLEMENTATION
