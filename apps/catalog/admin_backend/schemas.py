from datetime import datetime
from uuid import UUID
from typing import Optional
from ninja import Schema

class AdminCategoryOut(Schema):
    model_config = {"from_attributes": True}
    id: UUID
    name: str
    slug: str = ""
    # Category model has no 'description' field
    active: bool = True
    created_at: datetime

class AdminBrandOut(Schema):
    model_config = {"from_attributes": True}
    id: UUID
    title: str          # Brand model uses 'title', not 'name'
    slug: str = ""
    description: Optional[str] = ""
    active: bool = True
    created_at: datetime

class AdminCollectionOut(Schema):
    model_config = {"from_attributes": True}
    id: UUID
    title: str          # Collections model uses 'title', not 'name'
    sub_title: Optional[str] = ""
    slug: str = ""
    description: Optional[str] = ""
    # Collections model has no 'active' field
    created_at: datetime



class AdminBlogPostOut(Schema):
    model_config = {"from_attributes": True}
    id: UUID
    title: str
    slug: str = ""
    excerpt: Optional[str] = ""
    content: str = ""
    status: str = "draft"
    tags: list = []
    is_featured: bool = False
    published_at: Optional[datetime] = None
    view_count: int = 0
    created_at: datetime


