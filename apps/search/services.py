# apps/search/services.py
"""
Search services (Hybrid: FULLTEXT + semantic rerank).
Aligned with modern async-first execution.
"""

from __future__ import annotations

import time
import math
import logging
import hashlib
import json
from typing import List, Dict, Any, Optional, Tuple

from django.db.models.expressions import RawSQL
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.cache import cache

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
    """Hybrid search service combining FULLTEXT and semantic rerank with Redis caching."""

    def __init__(self):
        # Final weights (configurable via settings)
        self.fts_weight = getattr(settings, 'SEARCH_FTS_WEIGHT', 0.6)
        self.semantic_weight = getattr(settings, 'SEARCH_SEMANTIC_WEIGHT', 0.4)
        # Cache TTL in seconds (default 5 minutes)
        self.cache_ttl = getattr(settings, 'SEARCH_CACHE_TTL', 300)
        # Cache key prefix
        self.cache_prefix = 'search:v1:'
        # Embedding cache TTL (default 24 hours)
        self.embedding_cache_ttl = getattr(settings, 'SEARCH_EMBEDDING_CACHE_TTL', 86400)
        # Embedding cache prefix
        self.embedding_cache_prefix = 'search:embed:v1:'
        # Enable semantic search (can be disabled if embedding service not available)
        self.semantic_enabled = getattr(settings, 'SEARCH_SEMANTIC_ENABLED', False)

    # ---------- Public Sync API ----------
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
        1) FULLTEXT on SearchableContent (candidates)
        2) Rerank candidates with embeddings (cosine similarity)
        3) Combine scores
        4) Check cache first
        """
        start_time = time.time()
        if not query_text or not query_text.strip():
            return {"results": [], "total_count": 0, "execution_time_ms": 0, "query": query_text}

        filters = filters or {}

        # Generate cache key
        cache_key = self._generate_cache_key(query_text, filters, limit, boolean_mode)
        
        # Try cache first
        cached_results = cache.get(cache_key)
        if cached_results:
            exec_ms = int((time.time() - start_time) * 1000)
            return {
                "results": cached_results,
                "total_count": len(cached_results),
                "execution_time_ms": exec_ms,
                "query": query_text,
                "filters": filters,
                "search_id": None,
                "cache_hit": True,
            }

        # 1) FULLTEXT candidates or fallback on SQLite
        fts_candidates = self._full_text_candidates(query_text, filters, candidate_limit, boolean_mode)

        # If there are no candidates, return empty results
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
                "cache_hit": False,
            }

        # 2) Semantic rerank on these candidates (currently without hard embedding dependency)
        semantic_scored = self._semantic_rerank(query_text, fts_candidates)

        # 3) Combine scores
        combined_results = self._combine_results(fts_candidates, semantic_scored, limit)

        # Execution time
        execution_time_ms = int((time.time() - start_time) * 1000)

        # Save query for analytics
        search_query_obj = SearchQueryModel.objects.create(
            query_text=query_text,
            filters=filters,
            user=user,
            results_count=len(combined_results),
            execution_time_ms=execution_time_ms,
        )

        # Cache results
        cache.set(cache_key, combined_results, self.cache_ttl)

        # Cache results in database
        self._cache_search_results(search_query_obj, combined_results)

        return {
            "results": combined_results,
            "total_count": len(combined_results),
            "execution_time_ms": execution_time_ms,
            "query": query_text,
            "filters": filters,
            "search_id": search_query_obj.id,
            "cache_hit": False,
        }

    # ---------- Public Async API ----------
    async def asearch(
        self,
        query_text: str,
        user: Optional[User] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 20,
        boolean_mode: bool = True,
        candidate_limit: int = 300,
    ) -> Dict[str, Any]:
        """
        Async version of hybrid search using native Django 6.0 async ORM with Redis caching.
        1) FULLTEXT on SearchableContent (candidates)
        2) Rerank candidates with embeddings (cosine)
        3) Combine scores
        4) Check cache first
        """
        start_time = time.time()
        if not query_text or not query_text.strip():
            return {"results": [], "total_count": 0, "execution_time_ms": 0, "query": query_text}

        filters = filters or {}

        # Generate cache key
        cache_key = self._generate_cache_key(query_text, filters, limit, boolean_mode)
        
        # Try cache first (async cache get)
        cached_results = cache.get(cache_key)
        if cached_results:
            exec_ms = int((time.time() - start_time) * 1000)
            return {
                "results": cached_results,
                "total_count": len(cached_results),
                "execution_time_ms": exec_ms,
                "query": query_text,
                "filters": filters,
                "search_id": None,
                "cache_hit": True,
            }

        # 1) FULLTEXT candidates using native async ORM
        fts_candidates = await self._afull_text_candidates(query_text, filters, candidate_limit, boolean_mode)

        if not fts_candidates:
            exec_ms = int((time.time() - start_time) * 1000)
            sq = await SearchQueryModel.objects.acreate(
                query_text=query_text, filters=filters, user=user, results_count=0, execution_time_ms=exec_ms
            )
            return {
                "results": [],
                "total_count": 0,
                "execution_time_ms": exec_ms,
                "query": query_text,
                "filters": filters,
                "search_id": sq.id,
                "cache_hit": False,
            }

        # 2) Semantic rerank
        semantic_scored = self._semantic_rerank(query_text, fts_candidates)

        # 3) Combine scores
        combined_results = self._combine_results(fts_candidates, semantic_scored, limit)

        execution_time_ms = int((time.time() - start_time) * 1000)

        # Save query for analytics
        search_query_obj = await SearchQueryModel.objects.acreate(
            query_text=query_text,
            filters=filters,
            user=user,
            results_count=len(combined_results),
            execution_time_ms=execution_time_ms,
        )

        # Cache results (async cache set)
        cache.set(cache_key, combined_results, self.cache_ttl)

        # Cache results using native async ORM
        await self._acache_search_results(search_query_obj, combined_results)

        return {
            "results": combined_results,
            "total_count": len(combined_results),
            "execution_time_ms": execution_time_ms,
            "query": query_text,
            "filters": filters,
            "search_id": search_query_obj.id,
            "cache_hit": False,
        }

    # ---------- Internal: FULLTEXT or fallback (Async) ----------
    async def _afull_text_candidates(
        self,
        query_text: str,
        filters: Dict[str, Any],
        candidate_limit: int,
        boolean_mode: bool,
    ) -> List[Dict[str, Any]]:
        """Async FULLTEXT with MATCH ... AGAINST if MySQL; otherwise fallback to contains/icontains."""
        try:
            qs = SearchableContent.objects.all()

            # Apply filters
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
                # SQLite/Postgres fallback: simple icontains with basic weighting
                text_q = Q(title__icontains=query_text) | Q(content__icontains=query_text) | Q(metadata_text__icontains=query_text)
                results = (
                    qs.filter(text_q)
                      .only("id", "encounter_id", "content_type", "content_id", "title", "content", "metadata")
                      .order_by("-created_at")[:candidate_limit]
                      .values("id", "encounter_id", "content_type", "content_id", "title", "content", "metadata")
                )
                # Add simple relevance (length of matched text as approximation)
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
            logger.error(f"Async FULLTEXT/fallback search failed: {e}")
            return []

    # ---------- Internal: FULLTEXT or fallback (Sync) ----------
    def _full_text_candidates(
        self,
        query_text: str,
        filters: Dict[str, Any],
        candidate_limit: int,
        boolean_mode: bool,
    ) -> List[Dict[str, Any]]:
        """FULLTEXT with MATCH ... AGAINST if MySQL; otherwise fallback to contains/icontains."""
        try:
            qs = SearchableContent.objects.all()

            # Apply filters
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
                # SQLite/Postgres fallback: simple icontains with basic weighting
                text_q = Q(title__icontains=query_text) | Q(content__icontains=query_text) | Q(metadata_text__icontains=query_text)
                results = (
                    qs.filter(text_q)
                      .only("id", "encounter_id", "content_type", "content_id", "title", "content", "metadata")
                      .order_by("-created_at")[:candidate_limit]
                      .values("id", "encounter_id", "content_type", "content_id", "title", "content", "metadata")
                )
                # Add simple relevance (length of matched text as approximation)
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

    # ---------- Internal: Semantic rerank (placeholder with embedding cache) ----------
    def _semantic_rerank(self, query_text: str, candidates: List[Dict[str, Any]]) -> Dict[Tuple[int, str, int], float]:
        """
        Rerank based on embedding distance (smaller is better). 
        Returns empty dict if embedding service is not available or disabled.
        Implements embedding caching to reduce API calls.
        """
        if not self.semantic_enabled:
            return {}

        try:
            # Try to get cached query embedding
            query_cache_key = f"{self.embedding_cache_prefix}query:{hashlib.md5(query_text.encode()).hexdigest()}"
            query_vec = cache.get(query_cache_key)
            
            if query_vec is None:
                query_vec = self._make_query_embedding(query_text)
                cache.set(query_cache_key, query_vec, self.embedding_cache_ttl)
            
            distances: Dict[Tuple[int, str, int], float] = {}
            
            for c in candidates:
                key = (c.get("encounter_id") or 0, c["content_type"], c["content_id"])
                
                # Try to get cached content embedding
                content_cache_key = f"{self.embedding_cache_prefix}content:{c['id']}"
                content_vec = cache.get(content_cache_key)
                
                if content_vec is None:
                    # Generate content embedding from title + content
                    content_text = f"{c.get('title', '')} {c.get('content', '')}"
                    content_vec = self._make_query_embedding(content_text)
                    cache.set(content_cache_key, content_vec, self.embedding_cache_ttl)
                
                # Calculate cosine similarity (1 - distance)
                if query_vec and content_vec:
                    similarity = self._cosine_similarity(query_vec, content_vec)
                    distances[key] = 1.0 - similarity  # Convert to distance (smaller is better)
                else:
                    distances[key] = 0.5  # Fallback static value
            
            return distances
        except Exception as e:
            logger.warning(f"Semantic rerank failed: {e}")
            return {}

    # ---------- Internal: Combine ----------
    def _combine_results(
        self,
        fts_candidates: List[Dict[str, Any]],
        semantic_dist: Dict[Tuple[int, str, int], float],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """
        Combination: similarity_sem = 1 - distance (clamped to [0,1])
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
    def _generate_cache_key(self, query_text: str, filters: Dict[str, Any], limit: int, boolean_mode: bool) -> str:
        """Generate a unique cache key for search parameters."""
        cache_data = {
            'query': query_text.lower().strip(),
            'filters': sorted(filters.items()) if filters else [],
            'limit': limit,
            'boolean_mode': boolean_mode,
        }
        cache_hash = hashlib.md5(json.dumps(cache_data, sort_keys=True).encode()).hexdigest()
        return f"{self.cache_prefix}{cache_hash}"

    def _generate_snippet(self, content: str, query_text: str, max_length: int = 200) -> str:
        if not content:
            return ""
        snippet = content[:max_length]
        if len(content) > max_length:
            snippet += "..."
        return snippet

    async def _acache_search_results(self, search_query_obj: SearchQueryModel, results: List[Dict[str, Any]]):
        """Async version of cache search results using native Django 6.0 async ORM."""
        try:
            await SearchResult.objects.filter(query=search_query_obj).adelete()
            bulk = []
            for rank, r in enumerate(results, 1):
                try:
                    sc = await SearchableContent.objects.aget(id=r["id"])
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
                await SearchResult.objects.abulk_create(bulk)
        except Exception as e:
            logger.error(f"Failed to cache search results (async): {e}")

    def _cache_search_results(self, search_query_obj: SearchQueryModel, results: List[Dict[str, Any]]):
        """Sync version of cache search results."""
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
        """Generate embedding for text (placeholder for actual embedding service integration)."""
        # TODO: Integrate with actual embedding service (OpenAI, SentenceTransformers, etc.)
        # For now, use deterministic hash-based placeholder
        import random
        random.seed(hash(text) & 0xFFFFFFFF)
        vec = [random.random() for _ in range(64)]  # Placeholder dimensions until integration
        s = math.sqrt(sum(x*x for x in vec)) or 1.0
        return [x / s for x in vec]

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(b * b for b in vec2))
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        return dot_product / (magnitude1 * magnitude2)
