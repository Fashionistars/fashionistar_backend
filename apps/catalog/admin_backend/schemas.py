from datetime import datetime
from ninja import Schema

class AdminCategoryOut(Schema):
    model_config = {"from_attributes": True}
    id: str
    name: str
    slug: str
    description: str = ""
    active: bool = True
    created_at: datetime

class AdminBrandOut(Schema):
    model_config = {"from_attributes": True}
    id: str
    name: str
    slug: str
    description: str = ""
    active: bool = True
    created_at: datetime

class AdminCollectionOut(Schema):
    model_config = {"from_attributes": True}
    id: str
    name: str
    slug: str
    description: str = ""
    active: bool = True
    created_at: datetime


class AdminBlogPostOut(Schema):
    model_config = {"from_attributes": True}
    id: str
    title: str
    slug: str
    excerpt: str = ""
    content: str
    status: str
    tags: list = []
    is_featured: bool = False
    published_at: datetime | None = None
    view_count: int = 0
    created_at: datetime


