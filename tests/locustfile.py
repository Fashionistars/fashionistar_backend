import uuid
import random
from locust import HttpUser, task, between

class FashionistarAuthTester(HttpUser):
    """
    Locust Load Testing suite for measuring 100,000 requests/sec capability.
    Run with: locust -f tests/locustfile.py --host=http://localhost:8000
    
    Warning: Hitting 100k req/s requires running Locust in distributed mode across 
    multiple worker machines against a properly load-balanced production cluster.
    """
    wait_time = between(0.1, 0.5)

    def on_start(self):
        """
        Setup: Register a user to be used during the load test
        """
        self.email = f"loadtest_{uuid.uuid4().hex[:8]}@fashionistar.io"
        self.password = "LoadTest!Password2026"
        self.phone = f"+1800555{random.randint(1000, 9999)}"
        
        # Register user
        self.client.post("/api/v1/auth/register/", json={
            "email": self.email,
            "phone_number": self.phone,
            "password": self.password,
            "password2": self.password,
            "first_name": "Load",
            "last_name": "Tester",
            "role": "client"
        })

    @task(3)
    def test_health_check(self):
        """ High throughput health checks """
        self.client.get("/api/v1/health/")

    @task(1)
    def test_login_unverified(self):
        """ Simulates login attempts without verification """
        self.client.post("/api/v1/auth/login/", json={
            "email_or_phone": self.email,
            "password": self.password
        })

    @task(2)
    def test_idempotent_reset_request(self):
        """ Simulates massive concurrent password reset requests (idempotency check) """
        self.client.post("/api/v1/password/reset-request/", json={
            "email_or_phone": self.email
        })
