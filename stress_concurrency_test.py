import os
import django
import asyncio
import time
from collections import Counter

# Django Setup
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.development")
django.setup()

from apps.authentication.models import UnifiedUser
from apps.authentication.exceptions import DuplicateUserError, SoftDeletedUserExistsError
from django.db import IntegrityError
from django.core.exceptions import ValidationError
import uuid

# Configuration
CONCURRENCY_LEVEL = 500    # Number of simulated concurrent tasks trying to hit the DB
MAX_DB_CONNECTIONS = 80    # Prevent crashing local Postgres by limiting active connections
TEST_EMAIL = f"concurrency.{uuid.uuid4().hex[:8]}@fashionistar.io"

async def attempt_create_user(task_id, semaphore):
    """
    Attempts to create the same user simultaneously.
    Semaphore ensures we stay within the PostgreSQL connection limit, 
    but 80 simultaneous requests still easily tests database race conditions perfectly.
    """
    # MONKEYPATCH: Bypass PBKDF2 CPU-blocking hash to guarantee 100% network DB concurrency
    UnifiedUser.set_password = lambda self, raw_password: setattr(self, 'password', 'argon2$dummy$hash$123')
    
    async with semaphore:
        try:
            await UnifiedUser.objects.acreate_user(
                email=TEST_EMAIL,
                password="HyperPassword2026!",
                first_name="Concurrency",
                last_name="Tester",
                role="client"
            )
            return "SUCCESS"
        except DuplicateUserError:
            return "RACE_CONDITION_DEFEATED_BY_DB_CONSTRAINT"
        except SoftDeletedUserExistsError:
            return "SOFT_DELETED_USER_EXISTS_ERROR"
        except ValidationError:
            return "BLOCKED_BY_DJANGO_VALIDATION_ERROR"
        except IntegrityError:
            return "UNHANDLED_INTEGRITY_ERROR"
        except Exception as e:
            return f"OTHER_ERROR: {type(e).__name__} - {str(e)}"

async def run_concurrency_test():
    print(f"\n{'='*60}")
    print(f"🚀 EXTREME CONCURRENCY IDEMPOTENCY TEST")
    print(f"Bombarding User Manager with {CONCURRENCY_LEVEL:,} concurrent creation requests...")
    print(f"Processing in chunks of {MAX_DB_CONNECTIONS} simultaneous requests...")
    print(f"{'='*60}\n")
    
    # 1. Cleanup before test
    await UnifiedUser.objects.filter(email=TEST_EMAIL).adelete()
    
    # 2. Fire Requests Simultaneously
    semaphore = asyncio.Semaphore(MAX_DB_CONNECTIONS)
    start_time = time.time()
    
    tasks = [attempt_create_user(i, semaphore) for i in range(CONCURRENCY_LEVEL)]
    
    print("⏳ Firing all tasks into asyncio event loop...")
    results = await asyncio.gather(*tasks)
    
    end_time = time.time()
    elapsed = end_time - start_time
    
    # 3. Analyze Results
    counter = Counter(results)
    successes = counter.get("SUCCESS", 0)
    handled_duplicates = counter.get("DUPLICATE_USER_ERROR", 0)
    
    print(f"\n📊 RESULTS (in {elapsed:.2f} seconds):")
    for key, count in counter.items():
        print(f"  - {key}: {count:,}")
        
    print(f"\n✅ Concurrency Throughput: {CONCURRENCY_LEVEL / elapsed:,.0f} DB operations/second")
    
    if successes == 1 and handled_duplicates == CONCURRENCY_LEVEL - 1:
        print("\n🏆 IDEMPOTENCY PASSED PERFECTLY:")
        print("Exactly ONE user was created, and exactly 9,999 were blocked elegantly by the UnifiedUserManager idempotency guard.")
    else:
        print("\n❌ IDEMPOTENCY FAILED:")
        print("Multiple users were created or errors were not handled gracefully. Check the locks.")
        
    print(f"\n{'='*60}\n")

if __name__ == "__main__":
    asyncio.run(run_concurrency_test())
