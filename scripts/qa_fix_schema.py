import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.development")
django.setup()

from django.db import connection

print("Checking current column names in vendor_profile_collections...")
with connection.cursor() as c:
    c.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'vendor_profile_collections'
        ORDER BY ordinal_position
    """)
    cols = c.fetchall()
    print("Current columns:", cols)

# The DB has 'collection_id' but Django expects 'collections_id'
# We need to rename it.
print("\nRenaming collection_id -> collections_id...")
with connection.cursor() as c:
    try:
        c.execute("""
            ALTER TABLE vendor_profile_collections 
            RENAME COLUMN collection_id TO collections_id
        """)
        print("SUCCESS: column renamed")
    except Exception as e:
        print(f"ERROR: {e}")
        print("Trying alternative approach...")
        # If rename fails, check if collections_id already exists
        c.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'vendor_profile_collections'
            AND column_name = 'collections_id'
        """)
        exists = c.fetchone()
        if exists:
            print("collections_id already exists — no action needed")
        else:
            print("collections_id does not exist and rename failed")

print("\nVerifying final state...")
with connection.cursor() as c:
    c.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'vendor_profile_collections'
        ORDER BY ordinal_position
    """)
    print("Final columns:", [r[0] for r in c.fetchall()])
