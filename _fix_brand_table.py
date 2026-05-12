"""Fix catalog_brand table: rebuild with UUID PK to match current model."""
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django
django.setup()

from django.db import connection

SQL_CREATE = """
CREATE TABLE IF NOT EXISTS catalog_brand_new (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    is_deleted boolean NOT NULL DEFAULT false,
    deleted_at timestamptz NULL,
    user_id uuid NOT NULL REFERENCES authentication_unifieduser(id) ON DELETE CASCADE,
    title varchar(100) NOT NULL,
    description text NOT NULL DEFAULT '',
    image varchar(200) NOT NULL DEFAULT '',
    active boolean NOT NULL DEFAULT true,
    slug varchar(200) NOT NULL UNIQUE
)
"""

SQL_COPY = """
INSERT INTO catalog_brand_new
    (created_at, updated_at, is_deleted, deleted_at, user_id, title, description, image, active, slug)
SELECT
    created_at, updated_at, is_deleted, deleted_at, user_id, title, description, image, active, slug
FROM catalog_brand
"""

with connection.cursor() as cur:
    cur.execute(SQL_CREATE)
    print("New table created")
    cur.execute(SQL_COPY)
    print("Data copied")
    cur.execute("DROP TABLE catalog_brand CASCADE")
    print("Old table dropped")
    cur.execute("ALTER TABLE catalog_brand_new RENAME TO catalog_brand")
    print("Table renamed")
    cur.execute("SELECT COUNT(*) FROM catalog_brand")
    print("Rows in catalog_brand:", cur.fetchone()[0])

print("=== catalog_brand rebuilt with UUID PK ===")
