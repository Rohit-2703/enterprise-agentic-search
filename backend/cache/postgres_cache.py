"""PostgreSQL cache layer for L2 warm caching and analytics."""
import hashlib
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import and_
from backend.database.models import QueryCache
from backend.database.connection import get_db_session
from backend.utils.config import settings
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


class PostgresCache:
    """PostgreSQL cache client for L2 warm caching."""
    
    def __init__(self):
        """Initialize PostgreSQL cache."""
        self.cache_ttl_days = settings.postgres_cache_ttl // 86400  # Convert to days
        logger.info(f"PostgreSQL cache initialized with TTL: {self.cache_ttl_days} days")
    
    def _hash_text(self, text: str) -> str:
        """Generate hash for text."""
        return hashlib.sha256(text.encode()).hexdigest()
    
    def get_query_result(self, query: str) -> Optional[Dict[str, Any]]:
        """Get cached query result from PostgreSQL."""
        query_hash = self._hash_text(query.lower().strip())
        
        try:
            with get_db_session() as db:
                cutoff_date = datetime.utcnow() - timedelta(days=self.cache_ttl_days)
                cache_entry = db.query(QueryCache).filter(
                    and_(
                        QueryCache.query_embedding_hash == query_hash,
                        QueryCache.created_at >= cutoff_date
                    )
                ).first()
                
                if cache_entry:
                    cache_entry.hit_count += 1
                    db.commit()
                    
                    logger.info(f"PostgreSQL cache HIT for query hash: {query_hash[:8]}...")
                    return {
                        "answer": cache_entry.answer,
                        "citations": cache_entry.citations,
                        "confidence_score": cache_entry.confidence_score
                    }
                
                logger.info(f"PostgreSQL cache MISS for query hash: {query_hash[:8]}...")
                return None
        except Exception as e:
            logger.error(f"PostgreSQL get error: {e}")
            return None
    
    def set_query_result(
        self,
        query: str,
        answer: str,
        citations: list,
        confidence_score: float
    ) -> bool:
        """Cache query result in PostgreSQL."""
        query_hash = self._hash_text(query.lower().strip())
        
        try:
            with get_db_session() as db:
                existing = db.query(QueryCache).filter(
                    QueryCache.query_embedding_hash == query_hash
                ).first()
                
                if existing:
                    existing.query_text = query
                    existing.answer = answer
                    existing.citations = citations
                    existing.confidence_score = confidence_score
                    existing.updated_at = datetime.utcnow()
                    logger.info(f"Updated PostgreSQL cache for hash: {query_hash[:8]}...")
                else:
                    new_cache = QueryCache(
                        query_text=query,
                        query_embedding_hash=query_hash,
                        answer=answer,
                        citations=citations,
                        confidence_score=confidence_score,
                        hit_count=1
                    )
                    db.add(new_cache)
                    logger.info(f"Created PostgreSQL cache entry for hash: {query_hash[:8]}...")
                
                db.commit()
                return True
        except Exception as e:
            logger.error(f"PostgreSQL set error: {e}")
            return False
    
    def update_feedback(
        self,
        query: str,
        feedback_score: float
    ) -> bool:
        """Update average feedback score for cached query."""
        query_hash = self._hash_text(query.lower().strip())
        
        try:
            with get_db_session() as db:
                cache_entry = db.query(QueryCache).filter(
                    QueryCache.query_embedding_hash == query_hash
                ).first()
                
                if cache_entry:
                    if cache_entry.avg_feedback_score is None:
                        cache_entry.avg_feedback_score = feedback_score
                    else:
                        current_avg = cache_entry.avg_feedback_score
                        cache_entry.avg_feedback_score = (
                            (current_avg * (cache_entry.hit_count - 1) + feedback_score) 
                            / cache_entry.hit_count
                        )
                    
                    db.commit()
                    logger.info(f"Updated feedback for hash: {query_hash[:8]}...")
                    return True
                
                return False
        except Exception as e:
            logger.error(f"PostgreSQL feedback update error: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        try:
            with get_db_session() as db:
                total_entries = db.query(QueryCache).count()
                
                if total_entries == 0:
                    return {
                        "total_cached_queries": 0,
                        "avg_hit_count": 0.0,
                        "avg_confidence": 0.0,
                        "avg_feedback": 0.0
                    }
                
                from sqlalchemy import func
                stats = db.query(
                    func.count(QueryCache.id).label('count'),
                    func.avg(QueryCache.hit_count).label('avg_hits'),
                    func.avg(QueryCache.confidence_score).label('avg_confidence'),
                    func.avg(QueryCache.avg_feedback_score).label('avg_feedback')
                ).first()
                
                return {
                    "total_cached_queries": stats.count or 0,
                    "avg_hit_count": round(float(stats.avg_hits or 0), 2),
                    "avg_confidence": round(float(stats.avg_confidence or 0), 2),
                    "avg_feedback": round(float(stats.avg_feedback or 0), 2)
                }
        except Exception as e:
            logger.error(f"PostgreSQL stats error: {e}")
            return {}
    
postgres_cache = PostgresCache()
