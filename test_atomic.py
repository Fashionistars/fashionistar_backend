import os
import django
import asyncio
from asgiref.sync import sync_to_async

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from django.db import transaction

async def main():
    print(f"Django Version: {django.get_version()}")
    try:
        print("Attempting async with transaction.atomic()...")
        async with transaction.atomic():
            print("SUCCESS: Entered atomic block")
    except TypeError as e:
        print(f"FAILED: TypeError - {e}")
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    asyncio.run(main())
