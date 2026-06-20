# apps/product/migrations/0029_composite_indices_cleanup.py
"""
Phase 1 — Composite M2M Faceted Indices & Schema Cleanup.

Operations:
  1. Idempotent DDL drop of stale sub_category_id FK column on product_product
     (guard: IF EXISTS ensures this is a no-op if already removed).

  2. Composite B-tree indices on the product ↔ category M2M through-table
     (product_product_categories) using CREATE INDEX CONCURRENTLY to avoid
     table-level locks in production. Django does NOT manage these indices via
     the ORM because the through-table is auto-generated — RunSQL is required.

     Index (category_id, product_id):
       Optimises: WHERE category_id = X ORDER BY product_id DESC
       Used by:   storefront category listing, faceted search filters

     Index (product_id, category_id):
       Optimises: WHERE product_id = X (fetch all categories for a product)
       Used by:   product detail API, serializer category population

Performance Target: sub-100ms catalog filter API at 10k+ RPS.
"""

from django.db import migrations


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ('product', '0028_remove_product_sub_categories'),
        ('catalog', '0001_initial'),
    ]

    operations = [
        # ── 1. Idempotent column removal (guard against stale DDL) ─────────
        migrations.RunSQL(
            sql="""
                ALTER TABLE product_product
                DROP COLUMN IF EXISTS sub_category_id CASCADE;
            """,
            reverse_sql="-- Irreversible: sub_category_id was permanently removed.",
        ),

        # ── 2a. Composite index: category → product ─────────────────────────
        # Optimises faceted catalog queries:
        #   SELECT * FROM product_product_categories
        #   WHERE category_id = X ORDER BY product_id DESC;
        migrations.RunSQL(
            sql="""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS
                    idx_product_categories_cat_prod
                ON product_product_categories (category_id, product_id);
            """,
            reverse_sql="""
                DROP INDEX CONCURRENTLY IF EXISTS idx_product_categories_cat_prod;
            """,
        ),

        # ── 2b. Composite index: product → category ─────────────────────────
        # Optimises product-detail serializer category population:
        #   SELECT * FROM product_product_categories
        #   WHERE product_id = X;
        migrations.RunSQL(
            sql="""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS
                    idx_product_categories_prod_cat
                ON product_product_categories (product_id, category_id);
            """,
            reverse_sql="""
                DROP INDEX CONCURRENTLY IF EXISTS idx_product_categories_prod_cat;
            """,
        ),
    ]
