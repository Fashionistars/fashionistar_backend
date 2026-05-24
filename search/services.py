"""
سرویس‌های جستجو (Hybrid: FULLTEXT + semantic rerank)
مطابق نمونهٔ مستندات در sample_codes/search/services.py با تطبیق به محیط فعلی
"""

from __future__ import annotations

import time
import math
import logging
from typing import List, Dict, Any, Optional, Tuple
from functools import reduce
from operator import or_ as OR

from django.db.models.expressions import RawSQL
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.conf import settings

from .models import SearchableContent, SearchQuery as SearchQueryModel, SearchResult

logger = logging.getLogger(__name__)
User = get_user_model()


class SearchService:
    """Thin wrapper delegating to HybridSearchService (backward-compat for tests)."""
    def __init__(self):
        self._hybrid = HybridSearchService()

    def search(self, *args, **kwargs):
        # Return only the results list for compatibility
        return [r for r in self._hybrid.search(*args, **kwargs).get("results", [])]


class HybridSearchService:
    """Hybrid search service combining FULLTEXT (MySQL) and semantic rerank."""

    def __init__(self):
        # وزن‌دهی نهایی
        self.fts_weight = 0.6
        self.semantic_weight = 0.4

    # ---------- Public API ----------
    def search(
        self,
        query_text: str,
        user: Optional[User] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
        boolean_mode: bool = True,
        candidate_limit: int = 300,
    ) -> Dict[str, Any]:
        """
        1) FULLTEXT روی SearchableContent (کاندیدا)
        2) ریرنک کاندیدا با امبدینگ‌ها (cosine)
        3) ترکیب امتیازها
        """
        start_time = time.time()
        if not query_text or not query_text.strip():
            return {"results": [], "total_count": 0, "execution_time_ms": 0, "query": query_text}

        filters = filters or {}

        # 1) FULLTEXT candidates یا fallback روی sqlite
        fts_candidates = self._full_text_candidates(query_text, filters, candidate_limit, boolean_mode)

        # اگر هیچ کاندیدایی نیست، خالی برگرد
        if not fts_candidates:
            exec_ms = int((time.time() - start_time) * 1000)
            sq = SearchQueryModel.objects.create(
                query_text=query_text, filters=filters, user=user, results_count=0, execution_time_ms=exec_ms
            )
            return {
                "results": [],
                "total_count": 0,
                "execution_time_ms": exec_ms,
                "query": query_text,
                "filters": filters,
                "search_id": sq.id,
            }

        # 2) semantic rerank روی همین کاندیداها (فعلاً بدون وابستگی به embeddings)
        semantic_scored = self._semantic_rerank(query_text, fts_candidates)

        # 3) ترکیب امتیازها
        combined_results = self._combine_results(fts_candidates, semantic_scored, limit)

        # زمان اجرا
        execution_time_ms = int((time.time() - start_time) * 1000)

        # ذخیرهٔ کوئری برای آنالیتیکس
        search_query_obj = SearchQueryModel.objects.create(
            query_text=query_text,
            filters=filters,
            user=user,
            results_count=len(combined_results),
            execution_time_ms=execution_time_ms,
        )

        # کش نتایج
        self._cache_search_results(search_query_obj, combined_results)

        return {
            "results": combined_results,
            "total_count": len(combined_results),
            "execution_time_ms": execution_time_ms,
            "query": query_text,
            "filters": filters,
            "search_id": search_query_obj.id,
        }

    # ---------- Internal: FULLTEXT or fallback ----------
    def _full_text_candidates(
        self,
        query_text: str,
        filters: Dict[str, Any],
        candidate_limit: int,
        boolean_mode: bool,
    ) -> List[Dict[str, Any]]:
        """FULLTEXT با MATCH ... AGAINST اگر MySQL؛ در غیر این صورت fallback contains/icontains."""
        try:
            qs = SearchableContent.objects.all()

            # فیلترها
            if filters.get("encounter_id"):
                qs = qs.filter(encounter_id=filters["encounter_id"])
            if filters.get("content_type"):
                cts = filters["content_type"]
                if isinstance(cts, str):
                    cts = [cts]
                qs = qs.filter(content_type__in=cts)
            if filters.get("date_from"):
                qs = qs.filter(created_at__gte=filters["date_from"])
            if filters.get("date_to"):
                qs = qs.filter(created_at__lte=filters["date_to"])

            engine = settings.DATABASES.get('default', {}).get('ENGINE', '')
            is_mysql = 'mysql' in engine or 'mariadb' in engine

            if is_mysql:
                mode_sql = "IN BOOLEAN MODE" if boolean_mode else "IN NATURAL LANGUAGE MODE"
                raw = RawSQL(f"MATCH(fulltext_all) AGAINST (%s {mode_sql})", (query_text,))
                results = (
                    qs.annotate(relevance=raw)
                      .filter(relevance__gt=0)
                      .only("id", "encounter_id", "content_type", "content_id", "title", "content", "metadata")
                      .order_by("-relevance", "-created_at")[:candidate_limit]
                      .values("id", "encounter_id", "content_type", "content_id", "title", "content", "metadata", "relevance")
                )
            else:
                # sqlite/postgres fallback: ساده با icontains و وزن‌دهی ابتدایی
                text_q = Q(title__icontains=query_text) | Q(content__icontains=query_text) | Q(metadata_text__icontains=query_text)
                results = (
                    qs.filter(text_q)
                      .only("id", "encounter_id", "content_type", "content_id", "title", "content", "metadata")
                      .order_by("-created_at")[:candidate_limit]
                      .values("id", "encounter_id", "content_type", "content_id", "title", "content", "metadata")
                )
                # افزودن relevance ساده (طول matched text به‌عنوان تقریبی)
                for r in results:
                    r["relevance"] = float(len(query_text))

            formatted: List[Dict[str, Any]] = []
            for r in results:
                formatted.append({
                    "id": r["id"],
                    "encounter_id": r.get("encounter_id"),
                    "content_type": r["content_type"],
                    "content_id": r["content_id"],
                    "title": r["title"],
                    "content": r["content"],
                    "metadata": r.get("metadata") or {},
                    "keyword_relevance": float(r.get("relevance", 1.0)),
                })
            return formatted

        except Exception as e:
            logger.error(f"FULLTEXT/fallback search failed: {e}")
            return []

    # ---------- Internal: Semantic rerank (placeholder) ----------
    def _semantic_rerank(self, query_text: str, candidates: List[Dict[str, Any]]) -> Dict[Tuple[int, str, int], float]:
        """
        بر اساس امبدینگ: distance (کوچک‌تر بهتر). اگر سرویس امبدینگ موجود نبود، دیکشنری خالی برگردان.
        """
        try:
            query_vec = self._make_query_embedding(query_text)
        except Exception:
            return {}

        distances: Dict[Tuple[int, str, int], float] = {}
        # بدون دیتابیس امبدینگ، مقداردهی تصادفی ثابت بر اساس hash
        for c in candidates:
            key = (c.get("encounter_id") or 0, c["content_type"], c["content_id"])
            distances[key] = 0.5  # مقدار ثابت تا زمان یکپارچه‌سازی embeddings
        return distances

    # ---------- Internal: Combine ----------
    def _combine_results(
        self,
        fts_candidates: List[Dict[str, Any]],
        semantic_dist: Dict[Tuple[int, str, int], float],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """
        ترکیب: similarity_sem = 1 - distance (clamped to [0,1])
        combined = w_ft * norm(keyword_relevance) + w_sem * similarity_sem
        """
        if fts_candidates:
            max_kw = max(c.get("keyword_relevance", 1.0) for c in fts_candidates) or 1.0
        else:
            max_kw = 1.0

        results = []
        for c in fts_candidates:
            key = (c.get("encounter_id") or 0, c["content_type"], c["content_id"])
            dist = semantic_dist.get(key)
            sem_sim = 0.0 if dist is None else max(0.0, min(1.0, 1.0 - float(dist)))

            kw_norm = float(c.get("keyword_relevance", 1.0)) / max_kw
            combined = kw_norm * self.fts_weight + sem_sim * self.semantic_weight

            results.append({
                "id": c["id"],
                "encounter_id": c.get("encounter_id"),
                "content_type": c["content_type"],
                "content_id": c["content_id"],
                "title": c["title"],
                "content": c["content"],
                "snippet": self._generate_snippet(c["content"], ""),
                "score": float(kw_norm),
                "semantic_similarity": float(sem_sim),
                "combined_score": float(combined),
                "search_type": "hybrid" if dist is not None else "full_text",
                "metadata": c.get("metadata") or {},
                "created_at": None,
            })

        results.sort(key=lambda x: x["combined_score"], reverse=True)
        return results[:limit]

    # ---------- Helpers ----------
    def _generate_snippet(self, content: str, query_text: str, max_length: int = 200) -> str:
        if not content:
            return ""
        snippet = content[:max_length]
        if len(content) > max_length:
            snippet += "..."
        return snippet

    def _cache_search_results(self, search_query_obj: SearchQueryModel, results: List[Dict[str, Any]]):
        try:
            SearchResult.objects.filter(query=search_query_obj).delete()
            bulk = []
            for rank, r in enumerate(results, 1):
                try:
                    sc = SearchableContent.objects.get(id=r["id"])
                except SearchableContent.DoesNotExist:
                    continue
                bulk.append(SearchResult(
                    query=search_query_obj,
                    content=sc,
                    relevance_score=r["combined_score"],
                    rank=rank,
                    snippet=r["snippet"],
                ))
            if bulk:
                SearchResult.objects.bulk_create(bulk)
        except Exception as e:
            logger.error(f"Failed to cache search results: {e}")

    def _make_query_embedding(self, text: str) -> List[float]:
        import random
        random.seed(hash(text) & 0xFFFFFFFF)
        vec = [random.random() for _ in range(64)]  # ابعاد موقت تا زمان یکپارچه‌سازی
        s = math.sqrt(sum(x*x for x in vec)) or 1.0
        return [x / s for x in vec]

