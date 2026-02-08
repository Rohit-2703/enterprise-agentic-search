"""Calculates multi-factor confidence scores for retrieved documents."""
from typing import Dict, Any, List
from datetime import datetime
from backend.agents.state import AgentState
from backend.utils.config import settings
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


class ConfidenceAgent:
    """Calculates confidence scores for retrieved results based on semantic match, authority, recency, and cross-validation."""
    
    SOURCE_AUTHORITY = {
        "google_docs": 1.0,  # Official documents
        "confluence": 0.95,  # Technical docs
        "wiki": 0.9,  # Internal knowledge base
        "github": 0.85,  # Code and technical discussions
        "slack": 0.7,  # Informal discussions
        "csv_data": 0.8  # Structured data
    }
    
    def __init__(self):
        """Initialize the confidence agent with threshold from settings."""
        self.threshold = settings.confidence_threshold
    
    def calculate(self, state: AgentState) -> AgentState:
        """Calculate confidence score for retrieval results using multiple factors."""
        retrieved_docs = state.get("all_retrieved_docs", [])
        decomposed_queries = state.get("decomposed_queries", [])
        
        if not retrieved_docs:
            logger.warning("No documents retrieved for confidence calculation")
            state["confidence_score"] = 0.0
            state["confidence_details"] = {
                "semantic_match": 0.0,
                "source_authority": 0.0,
                "recency": 0.0,
                "cross_validation": 0.0
            }
            return state
        
        logger.info(f"Calculating confidence for {len(retrieved_docs)} documents")
        
        semantic_score = self._calculate_semantic_score(retrieved_docs)
        authority_score = self._calculate_authority_score(retrieved_docs)
        recency_score = self._calculate_recency_score(retrieved_docs)
        retrieved_docs_per_query = state.get("retrieved_docs", {})
        cross_val_score = self._calculate_cross_validation_score(retrieved_docs, decomposed_queries, retrieved_docs_per_query)
        
        overall_confidence = (
            0.4 * semantic_score +
            0.25 * authority_score +
            0.15 * recency_score +
            0.20 * cross_val_score
        )
        
        state["confidence_score"] = round(overall_confidence, 3)
        state["confidence_details"] = {
            "semantic_match": round(semantic_score, 3),
            "source_authority": round(authority_score, 3),
            "recency": round(recency_score, 3),
            "cross_validation": round(cross_val_score, 3)
        }
        state["processing_steps"].append(
            f"Confidence Scoring: {state['confidence_score']:.3f}"
        )
        
        logger.info(f"Confidence calculation complete: {state['confidence_score']:.3f}")
        return state
    
    def _calculate_semantic_score(self, docs: list) -> float:
        """Calculate average semantic similarity score from document scores."""
        if not docs:
            return 0.0
        
        scores = [doc.get("score", 0.0) for doc in docs]
        return sum(scores) / len(scores) if scores else 0.0
    
    def _calculate_authority_score(self, docs: list) -> float:
        """Calculate average source authority score based on source type weights."""
        if not docs:
            return 0.0
        
        authority_scores = []
        for doc in docs:
            source_type = doc.get("metadata", {}).get("source_type", "unknown")
            authority_scores.append(
                self.SOURCE_AUTHORITY.get(source_type, 0.5)
            )
        
        return sum(authority_scores) / len(authority_scores) if authority_scores else 0.0
    
    def _calculate_recency_score(self, docs: list) -> float:
        """Calculate average recency score."""
        if not docs:
            return 0.0
        
        recency_scores = []
        for doc in docs:
            # Use recency_score if available (from re-ranking)
            if "recency_score" in doc:
                recency_scores.append(doc["recency_score"])
            else:
                # Calculate from timestamp
                timestamp = doc.get("metadata", {}).get("timestamp")
                if timestamp:
                    try:
                        from datetime import timezone
                        # Handle timezone-aware timestamps (e.g., from Google Drive)
                        doc_date = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        # Make timezone-aware if it's naive
                        if doc_date.tzinfo is None:
                            doc_date = doc_date.replace(tzinfo=timezone.utc)
                        
                        now = datetime.now(timezone.utc)
                        days_old = (now - doc_date).days
                        recency_score = 1.0 / (1 + days_old / 30)
                        recency_scores.append(recency_score)
                    except Exception as e:
                        logger.debug(f"Error calculating recency score: {e}")
                        recency_scores.append(0.5)
                else:
                    recency_scores.append(0.5)
        
        return sum(recency_scores) / len(recency_scores) if recency_scores else 0.0
    
    def _calculate_cross_validation_score(self, docs: list, queries: list, retrieved_docs_per_query: Dict[str, List[Dict[str, Any]]]) -> float:
        """Calculate cross-validation score by measuring how many sub-queries have supporting documents."""
        if not queries or len(queries) == 1:
            return 1.0 if docs else 0.0
        
        queries_with_results = sum(1 for q, results in retrieved_docs_per_query.items() if results)
        return queries_with_results / len(queries) if queries else 0.0


def confidence_node(state: AgentState) -> AgentState:
    """LangGraph node for confidence scoring."""
    agent = ConfidenceAgent()
    return agent.calculate(state)


def should_trigger_self_healing(state: AgentState) -> str:
    """Decision function to determine if self-healing should be triggered."""
    confidence = state.get("confidence_score", 0.0)
    retry_count = state.get("retry_count", 0)
    max_retries = settings.max_retries
    
    if (confidence < settings.confidence_threshold and 
        retry_count < max_retries and 
        settings.enable_self_healing):
        logger.info(f"Low confidence ({confidence:.3f}), triggering self-healing")
        return "self_healing"
    else:
        logger.info(f"Confidence acceptable ({confidence:.3f}), proceeding to synthesis")
        return "synthesis"
