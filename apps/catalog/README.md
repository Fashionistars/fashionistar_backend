# `apps/catalog` — Fashionistar Catalog App

> **Version:** v2.0 — Phase 11 Production Modernization (2026-05-30)  
> **Coverage:** Categories · Brands · Collections · Blog Posts · **Homepage Bundle**  
> **Performance:** All reads via Django-Ninja async router · Redis 5-min TTL · <30ms p95

---

## Overview

The `catalog` app provides the **read-only public-facing product taxonomy and content layer** for Fashionistar. It manages:

| Model | Purpose |
|-------|---------|
| `Category` | Product taxonomy (top-level grouping) |
| `Collections` | Curated merchandising surfaces (carousels) |
| `Brand` | Vendor brand registry |
| `BlogPost` | Editorial content for SEO/marketing |

All writes happen via Django Admin. All reads are served by the **async Ninja router** with Redis caching — zero DRF overhead on read paths.

---

## Directory Structure

```
apps/catalog/
├── apis/
│   ├── async_/
│   │   └── catalog_views.py         ← Ninja async router (ALL read endpoints)
│   └── catalog_router.py            ← Router registration
├── models/
│   └── catalog_models.py            ← Category, Collections, Brand, BlogPost
├── schemas/
│   └── catalog_schemas.py           ← Ninja response schemas (OpenAPI docs)
├── selectors/
│   ├── catalog_selectors.py         ← CatalogSelector class (all async reads)
│   └── __init__.py
├── serializers/
│   └── common.py                    ← safe_media_url() helper
├── admin.py
├── apps.py
└── README.md                        ← This file
```

---

## API Endpoints

All endpoints are mounted at `/api/v1/ninja/catalog/`.

### Standard Catalog Endpoints

| Method | URL | Auth | Cache TTL | Description |
|--------|-----|------|-----------|-------------|
| `GET` | `/categories/` | None | 5 min | Paginated active categories |
| `GET` | `/categories/{slug}/` | None | None | Single category by slug |
| `GET` | `/brands/` | None | 5 min | Paginated active brands |
| `GET` | `/brands/{slug}/` | None | None | Single brand by slug |
| `GET` | `/collections/` | None | 5 min | Paginated collections |
| `GET` | `/collections/{slug}/` | None | None | Single collection by slug |
| `GET` | `/blog/` | None | 10 min | Paginated published blog posts |
| `GET` | `/blog/{slug}/` | None | None | Single blog post by slug |

### Phase 11 — Homepage Bundle Endpoint ⭐

| Method | URL | Auth | Cache TTL | Description |
|--------|-----|------|-----------|-------------|
| `GET` | `/homepage/` | None | **5 min** | All homepage data in one request |

---

## Homepage Bundle Endpoint

### Architecture

```
GET /api/v1/ninja/catalog/homepage/
         │
         ▼
  Redis cache hit? → return immediately (sub-millisecond)
         │
         ▼ (cache miss)
  asyncio.gather(                    ← 5 queries fire simultaneously
    aget_homepage_collections(10),   ← catalog.selectors → Collections model
    aget_homepage_categories(10),    ← catalog.selectors → Category model
    aget_homepage_products(10),      ← product.selectors → Product (featured=True)
    aget_homepage_hot_deals(10),     ← product.selectors → Product (hot_deal=True)
    aget_homepage_reviews(8),        ← product.selectors → ProductReview (moderated)
  )
         │
         ▼
  Serialize → Cache (5 min TTL) → Return JSON
  
Total latency target: < 30ms p95 (single DB RTT, parallel reads on PgBouncer pool)
```

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `collections_limit` | int | 10 | Max collections to return |
| `categories_limit` | int | 10 | Max categories to return |
| `products_limit` | int | 10 | Max featured products |
| `hot_deals_limit` | int = | 10 | Max hot-deal products |
| `reviews_limit` | int | 8 | Max moderated reviews |

### Response Shape

```json
{
  "collections": [
    {
      "id": "uuid",
      "title": "Summer Collection",
      "slug": "summer-collection",
      "sub_title": "Light & Breezy",
      "image_url": "/media/collections/summer.jpg",
      "background_image_url": "/media/collections/summer-bg.jpg",
      "created_at": "2026-05-01T00:00:00Z"
    }
  ],
  "categories": [
    {
      "id": "uuid",
      "name": "Senator Outfits",
      "slug": "senator-outfits",
      "image_url": "/media/categories/senator.jpg",
      "active": true
    }
  ],
  "featured_products": [
    {
      "id": "uuid",
      "title": "Agbada Premium",
      "slug": "agbada-premium",
      "price": "45000.00",
      "old_price": "55000.00",
      "discount_percentage": 18,
      "image_url": "https://res.cloudinary.com/.../w_480,h_480,c_fill/product.jpg",
      "rating": 4.8,
      "computed_avg_rating": 4.8,
      "hot_deal": false,
      "featured": true,
      "requires_measurement": true,
      "vendor_name": "Lagos Tailors Hub",
      "sizes": [{"id": "uuid", "name": "L"}],
      "colors": [{"id": "uuid", "name": "Navy", "hex_code": "#001F5B"}]
    }
  ],
  "hot_deals": [ /* same shape as featured_products */ ],
  "reviews": [
    {
      "id": "uuid",
      "reviewer_name": "Emeka Okafor",
      "reviewer_avatar_url": "https://res.cloudinary.com/.../w_120,h_120,c_fill/avatar.jpg",
      "product_title": "Classic Senator Outfit",
      "rating": 5,
      "review_text": "Perfect fit from day one!",
      "helpful_votes": 12,
      "created_at": "2026-04-15T10:30:00Z"
    }
  ],
  "meta": {
    "collections_count": 10,
    "categories_count": 10,
    "products_count": 10,
    "hot_deals_count": 7,
    "reviews_count": 8
  }
}
```

---

## Selectors — `CatalogSelector`

All methods are `@staticmethod async def` — ZERO `sync_to_async`, ZERO `threading.local`.

```python
from apps.catalog.selectors import CatalogSelector

# Standard selectors (return async QuerySet)
CatalogSelector.acategories()               # → AsyncQuerySet[Category]
CatalogSelector.acategory_by_slug(slug)     # → Category | None
CatalogSelector.acollections()              # → AsyncQuerySet[Collections]
CatalogSelector.acollection_by_slug(slug)   # → Collections | None
CatalogSelector.abrands()                   # → AsyncQuerySet[Brand]
CatalogSelector.abrand_by_slug(slug)        # → Brand | None
CatalogSelector.ablog_posts()               # → AsyncQuerySet[BlogPost]
CatalogSelector.ablog_post_by_slug(slug)    # → BlogPost | None

# Phase 11 — Homepage bundle selectors (return plain list[dict])
await CatalogSelector.aget_homepage_categories(limit=10)  # → list[dict]
await CatalogSelector.aget_homepage_collections(limit=10) # → list[dict]
```

### Phase 11 Selectors — Design Notes

`aget_homepage_categories` and `aget_homepage_collections` use `.values()` instead of full model instantiation:

```python
# .values() avoids model instantiation — no Cloudinary storage descriptor evaluation
qs = Category.objects.filter(active=True).values("id", "name", "slug", "image").order_by("name")[:limit]
return [row async for row in qs]
```

This delivers a 40–60% reduction in per-row Python overhead vs instantiating full ORM model objects, critical when returning 10+ items in a gather.

---

## Caching Strategy

```
Cache Key Pattern:  catalog:{resource}:{page}:{page_size}
Homepage Bundle:    catalog:homepage:bundle:{col}:{cat}:{prod}:{deal}:{rev}

TTL:
  categories / brands / collections  → 300s (5 min)
  blog posts                          → 600s (10 min)
  homepage bundle                     → 300s (5 min)

Backend:  django-redis (IGNORE_EXCEPTIONS=True — degrades to DB on Redis outage)
Utility:  apps/common/utils/redis.py → api_cache_get / api_cache_set
```

**Cache Invalidation:**
```python
# In Django admin post-save signals for Category/Collections/Brand/BlogPost:
from apps.common.utils.redis import api_cache_delete_pattern
api_cache_delete_pattern("catalog:*")  # wipes all catalog cache entries
```

---

## Frontend Integration (Next.js 16)

### Usage in RSC (React Server Component)

```typescript
// app/(home)/page.tsx — single fetch, all homepage data
import { getHomepageBundle } from "@/features/catalog";

export default async function Home() {
  const bundle = await getHomepageBundle();
  // bundle.collections, bundle.categories, bundle.featured_products,
  // bundle.hot_deals, bundle.reviews, bundle.meta
}
```

### Individual Catalog Fetches

```typescript
import {
  getCatalogCategories,
  getCatalogCollections,
  getCatalogBrands,
  getCatalogBlogPosts,
  getCatalogBlogPostBySlug,
  getHomepageBundle,
} from "@/features/catalog";
```

### ISR Revalidation

```typescript
// catalog.server.ts — all fetches use:
next: { revalidate: 300, tags: ["homepage-bundle"] }

// On-demand cache invalidation (e.g. after admin save):
import { revalidateTag } from "next/cache";
revalidateTag("homepage-bundle");
```

---

## Schemas — `catalog_schemas.py`

| Schema | Used In |
|--------|---------|
| `CatalogCategoryOut` | `/categories/{slug}/` |
| `CatalogBrandOut` | `/brands/{slug}/` |
| `CatalogCollectionOut` | `/collections/{slug}/` |
| `CatalogBlogPostOut` | `/blog/{slug}/` |
| `HomepageBundleOut` | OpenAPI docs for `/homepage/` |
| `HomepageProductCardOut` | Sub-schema of bundle |
| `HomepageReviewCardOut` | Sub-schema of bundle |
| `HomepageCollectionCardOut` | Sub-schema of bundle |
| `HomepageCategoryCardOut` | Sub-schema of bundle |
| `HomepageBundleMetaOut` | Sub-schema of bundle |

> **Note:** The `/homepage/` endpoint returns `dict` for speed (no Pydantic validation cost on the response path). The `HomepageBundleOut` schema is used **only for OpenAPI documentation**.

---

## Cross-App Import Pattern

The homepage bundle endpoint imports product selectors at request time (not at module import) to prevent circular imports:

```python
# apps/catalog/apis/async_/catalog_views.py
@router.get("/homepage/")
async def get_homepage_bundle(request, ...):
    # Guarded import — runs inside the view, not at module import time
    from apps.product.selectors import (
        aget_homepage_products,
        aget_homepage_hot_deals,
        aget_homepage_reviews,
    )
    
    (collections, categories, products, hot_deals, reviews) = await asyncio.gather(
        CatalogSelector.aget_homepage_collections(limit=10),
        CatalogSelector.aget_homepage_categories(limit=10),
        aget_homepage_products(limit=10),
        aget_homepage_hot_deals(limit=10),
        aget_homepage_reviews(limit=8),
    )
```

---

## Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| `/homepage/` cache hit | <5ms | Redis lookup |
| `/homepage/` cache miss (gather) | <30ms p95 | 5 parallel DB queries |
| `/categories/` cache hit | <5ms | Redis lookup |
| `/categories/` cache miss | <15ms p95 | Single paginated query |
| Frontend ISR cache | <1ms | Next.js edge cache |

---

## Admin Integration

- **Category** admin: `active`, `name`, `slug`, `image` (Cloudinary via `CloudinaryUploadAdminMixin`)
- **Collections** admin: `title`, `slug`, `sub_title`, `description`, `image`, `background_image`
- **Brand** admin: `title`, `slug`, `active`, `image`
- **BlogPost** admin: full editorial workflow (`draft → review → published → archived`)

After any admin save, the post-save signal fires:
```python
api_cache_delete_pattern("catalog:*")
```
This invalidates the homepage bundle cache so the next request gets fresh data.

---

## Regulatory & Compliance Notes

- All catalog data is **public and unauthenticated** — no PII is stored in catalog models.
- `BlogPost` content undergoes editorial review before `status=published`.
- Cloudinary image URLs are served with signed transformations where applicable.
- The homepage bundle endpoint intentionally returns **aggregated public data only** — no user-specific fields.
