from .ad import CatalogAd, CatalogAdSlot
from .banner import BannerSlot, CatalogBanner
from .blog import BlogMedia, BlogPost, BlogPostStatus
from .brand import Brand
from .category import Category
from .collection import Collections
from .fabric import Fabric
from .lookbook import Lookbook, LookbookItem
from .size_guide import SizeChart, SizeRecommendation
from .style_guide import FashionStyleGuide
from .tag import Tag
from .trending import FashionTrend, TrendingProduct

__all__ = [
    # Ad campaigns (Phase B revenue model)
    "CatalogAd",
    "CatalogAdSlot",
    # Banners (CMS-managed homepage slots)
    "BannerSlot",
    "CatalogBanner",
    # Blog
    "BlogMedia",
    "BlogPost",
    "BlogPostStatus",
    # Core catalog entities
    "Brand",
    "Category",
    "Collections",
    # Tags (shared taxonomy)
    "Tag",
    # 2026 — Fabrics
    "Fabric",
    # 2026 — Lookbooks
    "Lookbook",
    "LookbookItem",
    # 2026 — Size guides + AI recommendations
    "SizeChart",
    "SizeRecommendation",
    # 2026 — Style guides (editorial/AI)
    "FashionStyleGuide",
    # 2026 — Trending (materialized signals)
    "FashionTrend",
    "TrendingProduct",
]

