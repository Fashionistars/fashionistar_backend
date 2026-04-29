"""Django-Ninja response schemas for catalog async read endpoints."""

from __future__ import annotations

from datetime import datetime

from ninja import Schema


class CatalogCategoryOut(Schema):
    """Public catalog category payload."""

    id: str
    name: str
    title: str
    slug: str
    image: str | None
    image_url: str
    active: bool
    created_at: datetime
    updated_at: datetime


class CatalogBrandOut(Schema):
    """Public catalog brand payload."""

    id: str
    name: str
    title: str
    slug: str
    description: str
    image: str | None
    image_url: str
    active: bool
    created_at: datetime
    updated_at: datetime


class CatalogCollectionOut(Schema):
    """Public merchandising collection payload."""

    id: str
    name: str
    title: str
    slug: str
    sub_title: str
    description: str
    image: str | None
    image_url: str
    background_image: str | None
    background_image_url: str
    created_at: datetime
    updated_at: datetime


class CatalogBlogPostOut(Schema):
    """Public catalog blog payload."""

    id: str
    author: str | None
    author_name: str
    category: str | None
    category_name: str
    title: str
    slug: str
    excerpt: str
    content: str
    featured_image: str | None
    image_url: str
    gallery_media: list[str] | None
    status: str
    tags: list[str]
    seo_title: str
    seo_description: str
    is_featured: bool
    published_at: datetime | None
    view_count: int
    created_at: datetime
    updated_at: datetime
