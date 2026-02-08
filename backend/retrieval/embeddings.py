"""Embedding generation with Redis caching."""
from typing import List, Union
from openai import OpenAI
from backend.utils.config import settings
from backend.utils.logger import setup_logger
from backend.cache.redis_cache import redis_cache

logger = setup_logger(__name__)


class EmbeddingGenerator:
    """Generate embeddings using OpenAI with caching."""
    
    def __init__(self):
        """Initialize OpenAI client."""
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_embedding_model
        logger.info(f"Embedding generator initialized with model: {self.model}")
    
    def generate(
        self,
        text: Union[str, List[str]],
        use_cache: bool = True
    ) -> Union[List[float], List[List[float]]]:
        """Generate embeddings for text."""
        is_batch = isinstance(text, list)
        texts = text if is_batch else [text]
        
        embeddings = []
        uncached_texts = []
        uncached_indices = []
        
        for idx, t in enumerate(texts):
            if use_cache and settings.enable_caching:
                cached_embedding = redis_cache.get_embedding(t)
                if cached_embedding:
                    embeddings.append(cached_embedding)
                else:
                    uncached_texts.append(t)
                    uncached_indices.append(idx)
                    embeddings.append(None)
            else:
                uncached_texts.append(t)
                uncached_indices.append(idx)
                embeddings.append(None)
        
        if uncached_texts:
            try:
                response = self.client.embeddings.create(
                    input=uncached_texts,
                    model=self.model
                )
                
                for i, idx in enumerate(uncached_indices):
                    embedding = response.data[i].embedding
                    embeddings[idx] = embedding
                    
                    if use_cache and settings.enable_caching:
                        redis_cache.set_embedding(uncached_texts[i], embedding)
                
                logger.info(f"Generated {len(uncached_texts)} new embeddings")
            except Exception as e:
                logger.error(f"Error generating embeddings: {e}")
                raise
        
        return embeddings if is_batch else embeddings[0]


embedding_generator = EmbeddingGenerator()
