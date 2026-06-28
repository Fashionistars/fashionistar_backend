import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.development")
django.setup()

from django.db import connection
with connection.cursor() as c:
    c.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'vendor_profile_collections'
        ORDER BY ordinal_position
    """)
    rows = c.fetchall()
    print("vendor_profile_collections columns:", [r[0] for r in rows])
    
    # Check what migrations think the column should be
    c.execute("""
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_name LIKE '%vendor%collection%'
        ORDER BY table_name, ordinal_position
    """)
    rows2 = c.fetchall()
    print("All vendor+collection tables:", rows2)
