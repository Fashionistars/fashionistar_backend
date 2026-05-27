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

