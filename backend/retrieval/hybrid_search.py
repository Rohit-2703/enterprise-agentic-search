"""Hybrid search combining semantic search (metadata filtering is disabled by default)."""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from backend.retrieval.pinecone_client import pinecone_client
from backend.retrieval.embeddings import embedding_generator
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


class HybridSearch:
    """Hybrid search with semantic similarity. Metadata filtering is disabled by default (searches all sources)."""
    
    def __init__(self):
        """Initialize hybrid search."""
        self.pinecone = pinecone_client
        self.embedder = embedding_generator
    
    def search(
        self,
        query: str,
        top_k: int = 10,
        source_types: Optional[List[str]] = None,
        date_range: Optional[tuple] = None,
        access_control: Optional[List[str]] = None,
        min_score: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Perform hybrid search."""
        try:
            query_vector = self.embedder.generate(query)
            
            filter_dict = self._build_filter(
                source_types=source_types,
                date_range=date_range,
                access_control=access_control
            )
            
            results = self.pinecone.query(
                vector=query_vector,
                top_k=top_k * 2,
                filter=filter_dict,
                include_metadata=True
            )
            
            processed_results = []
            filtered_out = []
            
            for match in results.matches:
                if match.score >= min_score:
                    processed_results.append({
                        "id": match.id,
                        "score": match.score,
                        "metadata": match.metadata
                    })
                else:
                    filtered_out.append({
                        "id": match.id,
                        "score": match.score,
                        "source": match.metadata.get("source_type", "unknown") if match.metadata else "unknown"
                    })
            
            if results.matches:
                scores = [m.score for m in results.matches]
                logger.info(
                    f"Pinecone scores - Top: {max(scores):.3f}, Min: {min(scores):.3f}, "
                    f"Avg: {sum(scores)/len(scores):.3f}, Threshold: {min_score}"
                )
                if filtered_out:
                    logger.debug(
                        f"Filtered out {len(filtered_out)} results below threshold. "
                        f"Top filtered score: {max(f['score'] for f in filtered_out):.3f}"
                    )
            
            if not processed_results and results.matches:
                logger.warning(
                    f"No results met threshold {min_score}. Trying adaptive threshold..."
                )
                adaptive_threshold = max(0.5, results.matches[0].score - 0.1)
                logger.info(f"Using adaptive threshold: {adaptive_threshold:.3f}")
                
                for match in results.matches:
                    if match.score >= adaptive_threshold:
                        processed_results.append({
                            "id": match.id,
                            "score": match.score,
                            "metadata": match.metadata
                        })
            
            processed_results = processed_results[:top_k]
            
            logger.info(f"Hybrid search returned {len(processed_results)} results (min_score: {min_score})")
            return processed_results
        except Exception as e:
            logger.error(f"Hybrid search error: {e}")
            return []
    
    def _build_filter(
        self,
        source_types: Optional[List[str]] = None,
        date_range: Optional[tuple] = None,
        access_control: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """Build Pinecone metadata filter."""
        filters = []
        
        if source_types:
            filters.append({"source_type": {"$in": source_types}})
        
        if date_range:
            start_date, end_date = date_range
            if isinstance(start_date, str):
                start_date = datetime.fromisoformat(start_date)
            if isinstance(end_date, str):
                end_date = datetime.fromisoformat(end_date)
            
            filters.append({
                "timestamp": {
                    "$gte": start_date.isoformat(),
                    "$lte": end_date.isoformat()
                }
            })
        
        if access_control:
            filters.append({"access_control": {"$in": access_control}})
        
        if not filters:
            return None
        elif len(filters) == 1:
            return filters[0]
        else:
            return {"$and": filters}
    
    def deduplicate_results(
        self,
        results: Dict[str, List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """Deduplicate results from multiple queries."""
        seen_ids = set()
        deduped = []
        
        all_results = []
        for query_results in results.values():
            all_results.extend(query_results)
        
        all_results.sort(key=lambda x: x["score"], reverse=True)
        
        for result in all_results:
            if result["id"] not in seen_ids:
                seen_ids.add(result["id"])
                deduped.append(result)
        
        logger.info(f"Deduplicated {len(all_results)} results to {len(deduped)}")
        return deduped
    
    def rerank_by_recency(
        self,
        results: List[Dict[str, Any]],
        recency_weight: float = 0.3
    ) -> List[Dict[str, Any]]:
        """Re-rank results considering recency."""
        if not results:
            return results
        
        from datetime import timezone
        now = datetime.now(timezone.utc)
        
        for result in results:
            timestamp = result["metadata"].get("timestamp")
            if timestamp:
                try:
                    doc_date = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    if doc_date.tzinfo is None:
                        doc_date = doc_date.replace(tzinfo=timezone.utc)
                    if now.tzinfo is None:
                        now = now.replace(tzinfo=timezone.utc)
                    
                    days_old = (now - doc_date).days
                    
                    recency_score = 1.0 / (1 + days_old / 30)
                except Exception as e:
                    logger.debug(f"Error calculating recency for timestamp {timestamp}: {e}")
                    recency_score = 0.5
            else:
                recency_score = 0.5
            
            semantic_score = result["score"]
            combined_score = (
                (1 - recency_weight) * semantic_score +
                recency_weight * recency_score
            )
            
            result["combined_score"] = combined_score
            result["recency_score"] = recency_score
        
        results.sort(key=lambda x: x.get("combined_score", 0), reverse=True)
        
        logger.info(f"Re-ranked {len(results)} results by recency")
        return results


hybrid_search = HybridSearch()
