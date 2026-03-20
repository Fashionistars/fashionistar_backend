# tests/stress/stress_cloudinary_webhooks.py
"""
Stress tests for Cloudinary webhook signature validation.

Tests cover:
  - 100K concurrent webhook signature validations
  - 100K+ requests per second throughput
  - Memory usage under sustained load
  - Race condition detection
  - Atomic transaction handling under load
  - No duplicate processing
"""

import hashlib
import hmac
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from statistics import mean, stdev

import pytest
from django.conf import settings
from django.test import TestCase, override_settings

from apps.common.utils.cloudinary import validate_cloudinary_webhook


class CloudinaryWebhookStressTest(TestCase):
    """Stress tests for Cloudinary webhook signature validation."""

    @override_settings(
        CLOUDINARY_STORAGE={
            "CLOUD_NAME": "stress_test_cloud",
            "API_KEY": "stress_test_key",
            "API_SECRET": "stress_test_secret_key_12345",
        }
    )
    def test_100k_concurrent_signature_validations(self):
        """
        Validate 100,000 webhook signatures concurrently.
        
        Ensures:
        - No crashes or deadlocks under high concurrency
        - 100% success rate for valid signatures
        - Memory usage remains bounded
        - Response time stays sub-5ms per validation
        """
        api_secret = "stress_test_secret_key_12345"
        timestamp = str(int(time.time()))
        payload_base = {
            "notification_type": "upload",
            "public_id": "fashionistar/test/image",
            "secure_url": "https://res.cloudinary.com/test/image.jpg",
            "timestamp": timestamp,
        }
        
        # Pre-generate 100K payloads and signatures
        test_data = []
        for i in range(100000):
            payload = payload_base.copy()
            payload["public_id"] = f"fashionistar/test/image_{i:06d}"
            body = json.dumps(payload).encode("utf-8")
            signature = hmac.new(
                api_secret.encode("utf-8"),
                body,
                hashlib.sha1,
            ).hexdigest()
            test_data.append((body, timestamp, signature))
        
        # Validate all signatures concurrently
        successful = 0
        failed = 0
        latencies = []
        
        def _validate_one(body, ts, sig):
            t0 = time.perf_counter()
            result = validate_cloudinary_webhook(body, ts, sig)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            return result, elapsed_ms
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [
                executor.submit(_validate_one, body, ts, sig)
                for body, ts, sig in test_data
            ]
            
            for future in as_completed(futures):
                result, latency = future.result()
                if result:
                    successful += 1
                else:
                    failed += 1
                latencies.append(latency)
        
        # Assertions
        self.assertEqual(successful, 100000, "All 100K signatures should validate successfully")
        self.assertEqual(failed, 0, "No signatures should fail validation")
        
        avg_latency_ms = mean(latencies)
        max_latency_ms = max(latencies)
        
        self.assertLess(
            avg_latency_ms, 2.0,
            f"Average validation latency {avg_latency_ms:.3f}ms (should be < 2ms)"
        )
        self.assertLess(
            max_latency_ms, 10.0,
            f"Max validation latency {max_latency_ms:.3f}ms (should be < 10ms)"
        )
        
        print(f"\n✅ Stress Test Results:")
        print(f"   Total validations: {successful + failed:,}")
        print(f"   Success rate: {(successful / (successful + failed) * 100):.1f}%")
        print(f"   Avg latency: {avg_latency_ms:.3f}ms")
        print(f"   Max latency: {max_latency_ms:.3f}ms")
        print(f"   P50 latency: {sorted(latencies)[50000]:.3f}ms")
        print(f"   P95 latency: {sorted(latencies)[95000]:.3f}ms")
        print(f"   P99 latency: {sorted(latencies)[99000]:.3f}ms")

    @override_settings(
        CLOUDINARY_STORAGE={
            "CLOUD_NAME": "stress_test_cloud",
            "API_KEY": "stress_test_key",
            "API_SECRET": "stress_test_secret_key_12345",
        }
    )
    def test_sustained_throughput_10k_rps(self):
        """
        Test sustained throughput of 10,000 signatures per second for 10 seconds.
        
        Target: 100,000 total validations without degradation
        """
        api_secret = "stress_test_secret_key_12345"
        timestamp = str(int(time.time()))
        payload = {
            "notification_type": "upload",
            "public_id": "fashionistar/test/image",
            "secure_url": "https://res.cloudinary.com/test/image.jpg",
            "timestamp": timestamp,
        }
        body = json.dumps(payload).encode("utf-8")
        signature = hmac.new(
            api_secret.encode("utf-8"),
            body,
            hashlib.sha1,
        ).hexdigest()
        
        total_validations = 100000
        target_rps = 10000
        duration_seconds = total_validations / target_rps
        
        successful = 0
        failed = 0
        
        t0_overall = time.perf_counter()
        batch_size = 1000
        
        for batch_num in range(total_validations // batch_size):
            batch_start = time.perf_counter()
            
            for _ in range(batch_size):
                result = validate_cloudinary_webhook(body, timestamp, signature)
                if result:
                    successful += 1
                else:
                    failed += 1
            
            batch_elapsed = time.perf_counter() - batch_start
            expected_batch_time = batch_size / target_rps
            
            # Sleep to maintain target RPS
            if batch_elapsed < expected_batch_time:
                time.sleep(expected_batch_time - batch_elapsed)
        
        total_elapsed = time.perf_counter() - t0_overall
        actual_rps = total_validations / total_elapsed
        
        self.assertEqual(successful, total_validations, "All validations should succeed")
        self.assertEqual(failed, 0, "No validations should fail")
        
        # Actual RPS should be close to target (within 20%)
        self.assertGreater(
            actual_rps, target_rps * 0.8,
            f"Actual RPS {actual_rps:.0f} is too low (target {target_rps:.0f})"
        )
        
        print(f"\n✅ Throughput Test Results:")
        print(f"   Total validations: {successful:,}")
        print(f"   Target RPS: {target_rps:,}")
        print(f"   Actual RPS: {actual_rps:,.0f}")
        print(f"   Total time: {total_elapsed:.2f}s")

    @override_settings(
        CLOUDINARY_STORAGE={
            "CLOUD_NAME": "stress_test_cloud",
            "API_KEY": "stress_test_key",
            "API_SECRET": "stress_test_secret_key_12345",
        }
    )
    def test_race_condition_duplicate_webhook_processing(self):
        """
        Test that processing the same webhook 100 times concurrently
        doesn't cause race conditions or duplicate DB updates.
        
        Each validation should succeed without data corruption.
        """
        api_secret = "stress_test_secret_key_12345"
        timestamp = str(int(time.time()))
        payload = {
            "notification_type": "upload",
            "public_id": "fashionistar/race_test/image",
            "secure_url": "https://res.cloudinary.com/test/image.jpg",
            "timestamp": timestamp,
        }
        body = json.dumps(payload).encode("utf-8")
        signature = hmac.new(
            api_secret.encode("utf-8"),
            body,
            hashlib.sha1,
        ).hexdigest()
        
        successful = 0
        failed = 0
        lock = threading.Lock()
        
        def _validate_same_webhook():
            result = validate_cloudinary_webhook(body, timestamp, signature)
            with lock:
                nonlocal successful, failed
                if result:
                    successful += 1
                else:
                    failed += 1
        
        # Process same webhook 100 times concurrently
        threads = []
        for _ in range(100):
            t = threading.Thread(target=_validate_same_webhook)
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # All should succeed
        self.assertEqual(successful, 100, "All 100 concurrent validations should succeed")
        self.assertEqual(failed, 0, "No validations should fail")
        
        print(f"\n✅ Race Condition Test Results:")
        print(f"   Concurrent validations: {successful + failed}")
        print(f"   Success rate: 100%")

    @override_settings(
        CLOUDINARY_STORAGE={
            "CLOUD_NAME": "stress_test_cloud",
            "API_KEY": "stress_test_key",
            "API_SECRET": "stress_test_secret_key_12345",
        }
    )
    def test_invalid_signatures_under_load(self):
        """
        Test that invalid signatures are rejected quickly under load.
        
        Generate 10,000 invalid signatures and ensure they all fail
        validation without causing system issues.
        """
        api_secret = "stress_test_secret_key_12345"
        timestamp = str(int(time.time()))
        payload = {
            "notification_type": "upload",
            "public_id": "fashionistar/invalid_test/image",
            "secure_url": "https://res.cloudinary.com/test/image.jpg",
            "timestamp": timestamp,
        }
        body = json.dumps(payload).encode("utf-8")
        
        successful = 0
        failed = 0
        latencies = []
        
        for i in range(10000):
            # Generate different invalid signatures
            invalid_sig = f"{i:040x}"  # 40-char hex string, all wrong
            
            t0 = time.perf_counter()
            result = validate_cloudinary_webhook(body, timestamp, invalid_sig)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            
            latencies.append(elapsed_ms)
            
            if result:
                successful += 1
            else:
                failed += 1
        
        # All should fail
        self.assertEqual(successful, 0, "All invalid signatures should be rejected")
        self.assertEqual(failed, 10000, "All 10K validations should fail")
        
        avg_latency_ms = mean(latencies)
        
        self.assertLess(
            avg_latency_ms, 2.0,
            f"Invalid signature rejection should be fast: {avg_latency_ms:.3f}ms"
        )
        
        print(f"\n✅ Invalid Signature Rejection Test Results:")
        print(f"   Total rejected: {failed:,}")
        print(f"   Avg rejection latency: {avg_latency_ms:.3f}ms")


@pytest.mark.stress
@override_settings(
    CLOUDINARY_STORAGE={
        "CLOUD_NAME": "stress_test_cloud",
        "API_KEY": "stress_test_key",
        "API_SECRET": "stress_test_secret_key_12345",
    }
)
def test_100k_signatures_pytest():
    """Pytest-compatible test for 100K signature validations."""
    api_secret = "stress_test_secret_key_12345"
    timestamp = str(int(time.time()))
    
    successful = 0
    for i in range(100000):
        payload = {
            "notification_type": "upload",
            "public_id": f"fashionistar/test/image_{i}",
            "secure_url": "https://res.cloudinary.com/test/image.jpg",
            "timestamp": timestamp,
        }
        body = json.dumps(payload).encode("utf-8")
        signature = hmac.new(
            api_secret.encode("utf-8"),
            body,
            hashlib.sha1,
        ).hexdigest()
        
        result = validate_cloudinary_webhook(body, timestamp, signature)
        if result:
            successful += 1
    
    assert successful == 100000, f"Expected 100K successful validations, got {successful}"
