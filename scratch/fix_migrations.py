import django
import os
from django.db import connection

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.development")
django.setup()

with connection.cursor() as cursor:
    cursor.execute("DELETE FROM django_migrations WHERE app='vendor'")
    cursor.execute("DELETE FROM django_migrations WHERE app='catalog'")
    cursor.execute("DELETE FROM django_migrations WHERE app='admin_backend' AND name='0003_remove_brand_user_remove_category_category_name_idx_and_more'")
    print("Cleared vendor, catalog, and admin_backend cleanup records")
