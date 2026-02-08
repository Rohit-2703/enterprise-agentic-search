"""Redis cache layer for fast query result caching."""
import json
import hashlib
from typing import Optional, Dict, Any
import redis
from backend.utils.config import settings
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


class RedisCache:
    """Redis cache client for L1 hot caching."""
    
    def __init__(self):
        """Initialize Redis connection."""
        self.client = redis.from_url(
            settings.redis_connection_url,
            decode_responses=True
        )
        self.default_ttl = settings.redis_cache_ttl
        logger.info(f"Redis cache initialized with TTL: {self.default_ttl}s")
    
    def _generate_key(self, prefix: str, identifier: str) -> str:
        """Generate cache key."""
        return f"{prefix}:{identifier}"
    
    def _hash_text(self, text: str) -> str:
        """Generate hash for text."""
        return hashlib.sha256(text.encode()).hexdigest()
    
    def get_query_result(self, query: str) -> Optional[Dict[str, Any]]:
        """Get cached query result."""
        query_hash = self._hash_text(query.lower().strip())
        key = self._generate_key("query", query_hash)
        
        try:
            cached_data = self.client.get(key)
            if cached_data:
                logger.info(f"Redis cache HIT for query hash: {query_hash[:8]}...")
                return json.loads(cached_data)
            logger.info(f"Redis cache MISS for query hash: {query_hash[:8]}...")
            return None
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            return None
    
    def set_query_result(
        self,
        query: str,
        result: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """Cache query result."""
        query_hash = self._hash_text(query.lower().strip())
        key = self._generate_key("query", query_hash)
        ttl = ttl or self.default_ttl
        
        try:
            self.client.setex(
                key,
                ttl,
                json.dumps(result)
            )
            logger.info(f"Cached query result with hash: {query_hash[:8]}... (TTL: {ttl}s)")
            return True
        except Exception as e:
            logger.error(f"Redis set error: {e}")
            return False
    
    def get_embedding(self, text: str) -> Optional[list]:
        """Get cached embedding."""
        text_hash = self._hash_text(text)
        key = self._generate_key("embed", text_hash)
        
        try:
            cached_data = self.client.get(key)
            if cached_data:
                logger.debug(f"Embedding cache HIT for hash: {text_hash[:8]}...")
                return json.loads(cached_data)
            return None
        except Exception as e:
            logger.error(f"Redis get embedding error: {e}")
            return None
    
    def set_embedding(
        self,
        text: str,
        embedding: list,
        ttl: int = 86400
    ) -> bool:
        """Cache embedding."""
        text_hash = self._hash_text(text)
        key = self._generate_key("embed", text_hash)
        
        try:
            self.client.setex(
                key,
                ttl,
                json.dumps(embedding)
            )
            logger.debug(f"Cached embedding with hash: {text_hash[:8]}...")
            return True
        except Exception as e:
            logger.error(f"Redis set embedding error: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        try:
            info = self.client.info()
            return {
                "connected_clients": info.get("connected_clients", 0),
                "used_memory_human": info.get("used_memory_human", "N/A"),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "total_commands_processed": info.get("total_commands_processed", 0)
            }
        except Exception as e:
            logger.error(f"Redis stats error: {e}")
            return {}
    
    def clear_all(self) -> bool:
        """Clear all cached data."""
        try:
            self.client.flushdb()
            logger.warning("Redis cache cleared!")
            return True
        except Exception as e:
            logger.error(f"Redis flush error: {e}")
            return False
    
    def health_check(self) -> bool:
        """Check if Redis is healthy."""
        try:
            return self.client.ping()
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False


redis_cache = RedisCache()
