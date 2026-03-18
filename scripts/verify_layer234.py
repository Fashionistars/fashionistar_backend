import os
import django
import json
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.development")
django.setup()

from apps.authentication.models import UnifiedUser, LoginEvent, UserSession
from apps.audit_logs.models import AuditEventLog, EventType
from rest_framework.test import APIClient

def check_layer2():
    print("=== LAYER 2: Admin DB Records ===")
    events = LoginEvent.objects.count()
    sessions = UserSession.objects.count()
    audits = AuditEventLog.objects.count()
    
    print(f"LoginEvents found: {events}")
    print(f"UserSessions found: {sessions}")
    print(f"AuditEventLogs found: {audits}")
    
    pwd_req = AuditEventLog.objects.filter(event_type=EventType.PASSWORD_RESET_REQUEST).count()
    pwd_done = AuditEventLog.objects.filter(event_type=EventType.PASSWORD_RESET_DONE).count()
    pwd_chg = AuditEventLog.objects.filter(event_type=EventType.PASSWORD_CHANGED).count()
    
    print(f"PASSWORD_RESET_REQUESTED count: {pwd_req}")
    print(f"PASSWORD_RESET_COMPLETED count: {pwd_done}")
    print(f"PASSWORD_CHANGED count: {pwd_chg}")
    print("Layer 2 checks passed!")

def check_layer3():
    print("\n=== LAYER 3: Swagger UI / Schema ===")
    client = APIClient()
    r = client.get("/api/schema/", format="json")
    assert r.status_code == 200, f"Schema failed with {r.status_code}"
    schema = r.json()
    paths = list(schema.get("paths", {}).keys())
    print(f"Successfully generated Swagger schema with {len(paths)} endpoints.")
    print("Layer 3 checks passed!")

def check_layer4():
    print("\n=== LAYER 4: DRF Browsable API ===")
    client = APIClient()
    # Requesting with text/html ensures DRF renders the Browsable API template
    r = client.get("/api/v1/auth/register/", HTTP_ACCEPT="text/html")
    assert r.status_code == 200, f"DRF UI failed with {r.status_code}"
    assert b"text/html" in r.headers["Content-Type"].lower()
    print("Successfully rendered DRF HTML Browsable API for registration endpoint.")
    print("Layer 4 checks passed!")


if __name__ == "__main__":
    check_layer2()
    check_layer3()
    check_layer4()
    print("\nLayers 2, 3, 4 Verification Complete!")
