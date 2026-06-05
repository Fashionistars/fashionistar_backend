from .blog_admin import BlogMediaInline, BlogPostAdmin
from .brand_admin import BrandAdmin
from .catalog_2026_admin import (
    FabricAdmin,
    FashionStyleGuideAdmin,
    FashionTrendAdmin,
    LookbookAdmin,
    LookbookItemAdmin,
    SizeChartAdmin,
    SizeRecommendationAdmin,
    TrendingProductAdmin,
)
from .category_admin import CategoryAdmin
from .collection_admin import CollectionsAdmin

__all__ = [
    "BlogMediaInline",
    "BlogPostAdmin",
    "BrandAdmin",
    "CategoryAdmin",
    "CollectionsAdmin",
    # Phase 2 — 2026 catalog admin
    "FashionStyleGuideAdmin",
    "LookbookAdmin",
    "LookbookItemAdmin",
    "FashionTrendAdmin",
    "TrendingProductAdmin",
    "SizeChartAdmin",
    "SizeRecommendationAdmin",
    "FabricAdmin",
]
