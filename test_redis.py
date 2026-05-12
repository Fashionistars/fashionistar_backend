import os
import django
import sys
from django.conf import settings

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django_redis import get_redis_connection

def test_redis():
    print("Testing Redis Connection...")
    try:
        con = get_redis_connection("default")
        print(f"Redis Config: {con.connection_pool.connection_kwargs}")
        con.ping()
        print("SUCCESS: Redis is reachable!")
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    test_redis()
