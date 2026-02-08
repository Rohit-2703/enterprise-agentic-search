"""Retrieves relevant documents from Pinecone and MCP sources using parallel execution strategies."""
from typing import Dict, List, Any, Optional
import concurrent.futures
from backend.agents.state import AgentState
from backend.retrieval.hybrid_search import hybrid_search
from backend.retrieval.embeddings import embedding_generator
from backend.mcp import postgresql_mcp, github_mcp, jira_mcp
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


class RetrievalAgent:
    """Retrieves relevant documents using hybrid search (Pinecone + MCP) with intelligent execution strategies."""
    
    PINECONE_SOURCES = ["slack", "google_docs", "confluence", "github", "wiki", "csv_data"]
    
    MCP_SOURCES = {
        "postgresql_mcp": postgresql_mcp,
        "github_mcp": github_mcp,
        "jira_mcp": jira_mcp
    }
    
    def __init__(self):
        """Initialize the retrieval agent with hybrid search and embedding generator."""
        self.search = hybrid_search
        self.embedder = embedding_generator
    
    def retrieve(self, state: AgentState) -> AgentState:
        """Retrieve relevant documents for each routed query using the specified execution strategy."""
        self._current_state = state
        source_routing = state.get("source_routing", {})
        
        if not source_routing:
            logger.warning("No routing information available")
            state["retrieved_docs"] = {}
            state["all_retrieved_docs"] = []
            return state
        
        logger.info(f"Retrieving documents for {len(source_routing)} queries")
        
        all_results = {}
        
        for query, routing_plan in source_routing.items():
            try:
                if isinstance(routing_plan, list):
                    routing_plan = {
                        "sources": routing_plan,
                        "execution_strategy": "parallel",
                        "primary_source": None,
                        "secondary_sources": [],
                        "reasoning": "Legacy routing format",
                        "explicit_detection": False
                    }
                
                sources = routing_plan.get("sources", [])
                execution_strategy = routing_plan.get("execution_strategy", "parallel")
                primary_source = routing_plan.get("primary_source")
                secondary_sources = routing_plan.get("secondary_sources", [])
                explicit_detection = routing_plan.get("explicit_detection", False)
                
                logger.info(f"Retrieving for query: {query[:50]}... (sources: {sources}, strategy: {execution_strategy})")
                
                if execution_strategy == "parallel":
                    results = self._execute_parallel(query, sources, explicit_detection)
                elif execution_strategy == "sequential":
                    results = self._execute_sequential(query, primary_source, secondary_sources, explicit_detection)
                elif execution_strategy == "fallback":
                    results = self._execute_fallback(query, primary_source, secondary_sources, explicit_detection)
                else:
                    results = self._execute_parallel(query, sources, explicit_detection)
                
                all_results[query] = results
                logger.info(f"Retrieved {len(results)} docs for query: {query[:50]}...")
                
            except Exception as e:
                logger.error(f"Retrieval error for query '{query}': {e}")
                all_results[query] = []
        
        deduped_results = self.search.deduplicate_results(all_results)
        ranked_results = self.search.rerank_by_recency(deduped_results)
        
        state["retrieved_docs"] = all_results
        state["all_retrieved_docs"] = ranked_results
        state["processing_steps"].append(
            f"Retrieval: Retrieved {len(ranked_results)} unique documents (Hybrid: Pinecone + MCP)"
        )
        
        logger.info(f"Hybrid retrieval complete: {len(ranked_results)} unique documents")
        return state
    
    def _execute_parallel(self, query: str, sources: List[str], explicit_detection: bool) -> List[Dict[str, Any]]:
        """Execute retrieval from all sources in parallel using ThreadPoolExecutor."""
        pinecone_sources = [s for s in sources if s in self.PINECONE_SOURCES]
        mcp_sources = [s for s in sources if s in self.MCP_SOURCES]
        
        results = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {}
            
            if pinecone_sources:
                future_pinecone = executor.submit(
                    self._retrieve_from_pinecone,
                    query,
                    pinecone_sources,
                    explicit_detection
                )
                futures["pinecone"] = future_pinecone
            
            for mcp_source in mcp_sources:
                future_mcp = executor.submit(
                    self._retrieve_from_mcp,
                    query,
                    [mcp_source]
                )
                futures[mcp_source] = future_mcp
            
            for name, future in futures.items():
                try:
                    source_results = future.result(timeout=30)
                    results.extend(source_results)
                    logger.info(f"Parallel: {name} returned {len(source_results)} results")
                except Exception as e:
                    logger.error(f"Error retrieving from {name}: {e}")
        
        return results
    
    def _execute_sequential(self, query: str, primary_source: Optional[str], secondary_sources: List[str], explicit_detection: bool) -> List[Dict[str, Any]]:
        """Execute retrieval sequentially: try primary source first, then secondary sources if primary has results."""
        results = []
        if primary_source:
            if primary_source in self.PINECONE_SOURCES:
                primary_results = self._retrieve_from_pinecone(
                    query, [primary_source], explicit_detection
                )
            elif primary_source in self.MCP_SOURCES:
                primary_results = self._retrieve_from_mcp(query, [primary_source])
            else:
                primary_results = []
            
            results.extend(primary_results)
            logger.info(f"Sequential: Primary source {primary_source} returned {len(primary_results)} results")
        
        if results and secondary_sources:
            for secondary_source in secondary_sources:
                try:
                    if secondary_source in self.PINECONE_SOURCES:
                        secondary_results = self._retrieve_from_pinecone(
                            query, [secondary_source], explicit_detection
                        )
                    elif secondary_source in self.MCP_SOURCES:
                        secondary_results = self._retrieve_from_mcp(query, [secondary_source])
                    else:
                        continue
                    
                    results.extend(secondary_results)
                    logger.info(f"Sequential: Secondary source {secondary_source} returned {len(secondary_results)} results")
                except Exception as e:
                    logger.error(f"Error retrieving from secondary source {secondary_source}: {e}")
        
        return results
    
    def _execute_fallback(self, query: str, primary_source: Optional[str], secondary_sources: List[str], explicit_detection: bool) -> List[Dict[str, Any]]:
        """Execute retrieval with fallback: try primary source first, only use secondary if primary returns no results."""
        results = []
        if primary_source:
            if primary_source in self.PINECONE_SOURCES:
                primary_results = self._retrieve_from_pinecone(
                    query, [primary_source], explicit_detection
                )
            elif primary_source in self.MCP_SOURCES:
                primary_results = self._retrieve_from_mcp(query, [primary_source])
            else:
                primary_results = []
            
            results.extend(primary_results)
            logger.info(f"Fallback: Primary source {primary_source} returned {len(primary_results)} results")
        
        if not results and secondary_sources:
            logger.info(f"Fallback: Primary source returned no results, trying secondary sources")
            for secondary_source in secondary_sources:
                try:
                    if secondary_source in self.PINECONE_SOURCES:
                        secondary_results = self._retrieve_from_pinecone(
                            query, [secondary_source], explicit_detection
                        )
                    elif secondary_source in self.MCP_SOURCES:
                        secondary_results = self._retrieve_from_mcp(query, [secondary_source])
                    else:
                        continue
                    
                    if secondary_results:
                        results.extend(secondary_results)
                        logger.info(f"Fallback: Secondary source {secondary_source} returned {len(secondary_results)} results")
                        break  # Use first secondary source that returns results
                except Exception as e:
                    logger.error(f"Error retrieving from fallback source {secondary_source}: {e}")
        
        return results
    
    def _retrieve_from_pinecone(self, query: str, source_types: List[str], apply_filter: bool = True) -> List[Dict[str, Any]]:
        """Retrieve documents from Pinecone vector database."""
        try:
            from backend.utils.config import settings
            
            pinecone_results = self.search.search(
                query=query,
                top_k=5,
                source_types=None,
                min_score=settings.min_similarity_score
            )
            
            logger.info(f"Pinecone: Retrieved {len(pinecone_results)} docs")
            return pinecone_results
            
        except Exception as e:
            logger.error(f"Error retrieving from Pinecone: {e}")
            return []
    
    def _retrieve_from_mcp(self, query: str, mcp_sources: List[str]) -> List[Dict[str, Any]]:
        """Retrieve documents from MCP sources (PostgreSQL, GitHub, JIRA)."""
        mcp_results = []
        
        for source_name in mcp_sources:
            mcp_client = self.MCP_SOURCES.get(source_name)
            
            if not mcp_client:
                logger.warning(f"MCP source '{source_name}' not found")
                continue
            
            if source_name == "postgresql_mcp" and not postgresql_mcp.is_available():
                logger.warning("PostgreSQL MCP not available (database connection failed)")
                continue
            
            try:
                extracted_entities = getattr(self, '_current_state', {}).get('extracted_entities', [])
                if source_name == "github_mcp" and extracted_entities:
                    mcp_docs = mcp_client.search(query, limit=5, extracted_entities=extracted_entities)
                else:
                    mcp_docs = mcp_client.search(query, limit=5)
                
                for doc in mcp_docs:
                    try:
                        content = doc.get("content", doc.get("metadata", {}).get("text", ""))
                        embedding = self.embedder.generate(content, use_cache=True)
                        
                        query_embedding = self.embedder.generate(query, use_cache=True)
                        score = self._cosine_similarity(embedding, query_embedding)
                        
                        result = {
                            "id": doc["id"],
                            "score": score,
                            "metadata": doc["metadata"]
                        }
                        mcp_results.append(result)
                        
                    except Exception as e:
                        logger.error(f"Error processing MCP document: {e}")
                        continue
                
                logger.info(f"Retrieved {len(mcp_docs)} docs from {source_name}")
                
            except Exception as e:
                import traceback
                error_msg = str(e) if str(e) else type(e).__name__
                logger.error(f"Error retrieving from MCP source '{source_name}': {error_msg}")
                logger.debug(f"Traceback: {traceback.format_exc()}")
        
        return mcp_results
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        try:
            import numpy as np
            
            v1 = np.array(vec1)
            v2 = np.array(vec2)
            
            dot_product = np.dot(v1, v2)
            norm1 = np.linalg.norm(v1)
            norm2 = np.linalg.norm(v2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            similarity = dot_product / (norm1 * norm2)
            
            return float(max(0.0, min(1.0, (similarity + 1) / 2)))
            
        except Exception as e:
            logger.error(f"Error calculating cosine similarity: {e}")
            return 0.5


def retrieval_node(state: AgentState) -> AgentState:
    """LangGraph node for retrieval."""
    agent = RetrievalAgent()
    return agent.retrieve(state)
