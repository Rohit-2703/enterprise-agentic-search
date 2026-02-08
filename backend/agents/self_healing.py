"""Reformulates queries when confidence is low to improve retrieval results."""
from typing import Dict, Any, List
from openai import OpenAI
from backend.agents.state import AgentState
from backend.utils.config import settings
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


class SelfHealingAgent:
    """Reformulates queries on low confidence to improve retrieval."""
    
    def __init__(self):
        """Initialize the OpenAI client for query reformulation."""
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
    
    def heal(self, state: AgentState) -> AgentState:
        """Reformulate query and retry retrieval while preserving original sources and merging results."""
        original_query = state["original_query"]
        confidence = state.get("confidence_score", 0.0)
        retry_count = state.get("retry_count", 0)
        
        logger.info(f"Self-healing triggered (confidence: {confidence:.3f}, retry: {retry_count})")
        
        state["retry_count"] = retry_count + 1
        state["self_healing_triggered"] = True
        
        try:
            original_routing = state.get("source_routing", {}).copy()
            original_docs = state.get("all_retrieved_docs", []).copy()
            original_retrieved_docs = state.get("retrieved_docs", {}).copy()
            
            retrieved_docs = state.get("all_retrieved_docs", [])
            reformulated = self._reformulate_query(
                original_query=original_query,
                low_confidence_reason=self._diagnose_issue(state),
                existing_results=len(retrieved_docs)
            )
            
            logger.info(f"Reformulated query: {reformulated}")
            
            state["reformulated_query"] = reformulated
            original_decomposed = state.get("decomposed_queries", [])
            state["decomposed_queries"] = [reformulated]
            state["processing_steps"].append(f"Self-Healing: Reformulated query (attempt {state['retry_count']})")
            
            from backend.agents.routing import RoutingAgent
            from backend.agents.retrieval import RetrievalAgent
            
            routing_agent = RoutingAgent()
            state = routing_agent.route(state)
            new_routing = state.get("source_routing", {})
            
            merged_routing = self._merge_routing_plans(original_routing, new_routing, reformulated)
            state["source_routing"] = merged_routing
            logger.info(f"Merged routing: {len(merged_routing)} queries (preserved {len(original_routing)} original)")
            
            retrieval_agent = RetrievalAgent()
            state = retrieval_agent.retrieve(state)
            
            new_docs = state.get("all_retrieved_docs", [])
            merged_docs = self._merge_results(original_docs, new_docs)
            state["all_retrieved_docs"] = merged_docs
            
            new_retrieved_docs = state.get("retrieved_docs", {})
            for query, docs in original_retrieved_docs.items():
                if query not in new_retrieved_docs:
                    new_retrieved_docs[query] = []
                new_retrieved_docs[query].extend(docs)
            state["retrieved_docs"] = new_retrieved_docs
            
            logger.info(f"Merged results: {len(original_docs)} original + {len(new_docs)} new = {len(merged_docs)} total")
            
            from backend.agents.confidence import ConfidenceAgent
            confidence_agent = ConfidenceAgent()
            state = confidence_agent.calculate(state)
            
            logger.info(f"Self-healing complete. New confidence: {state['confidence_score']:.3f}")
            
        except Exception as e:
            logger.error(f"Self-healing error: {e}")
            state["processing_steps"].append(f"Self-Healing: Error occurred - {str(e)}")
        
        return state
    
    def _merge_routing_plans(self, original_routing: Dict[str, Any], new_routing: Dict[str, Any], reformulated_query: str) -> Dict[str, Any]:
        """Merge original and new routing plans."""
        merged = original_routing.copy()
        
        if new_routing:
            new_sources = set()
            for query, plan in new_routing.items():
                if isinstance(plan, dict):
                    new_sources.update(plan.get("sources", []))
                elif isinstance(plan, list):
                    new_sources.update(plan)
            
            for query, plan in merged.items():
                if isinstance(plan, dict):
                    original_sources = set(plan.get("sources", []))
                    merged_sources = list(original_sources | new_sources)
                    plan["sources"] = merged_sources
                    plan["execution_strategy"] = "parallel"
                    plan["reasoning"] = f"Self-healing: Merged original sources with reformulated query sources"
        
        if reformulated_query not in merged and new_routing:
            for query, plan in new_routing.items():
                merged[reformulated_query] = plan
                break
        
        return merged
    
    def _merge_results(self, original_docs: List[Dict[str, Any]], new_docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merge original and new results."""
        seen_ids = set()
        merged = []
        
        for doc in original_docs:
            doc_id = doc.get("metadata", {}).get("id") or doc.get("id")
            if doc_id and doc_id not in seen_ids:
                seen_ids.add(doc_id)
                merged.append(doc)
        
        for doc in new_docs:
            doc_id = doc.get("metadata", {}).get("id") or doc.get("id")
            if doc_id and doc_id not in seen_ids:
                seen_ids.add(doc_id)
                merged.append(doc)
        
        return merged
    
    def _diagnose_issue(self, state: AgentState) -> str:
        """Diagnose why confidence was low by analyzing state details."""
        details = state.get("confidence_details", {})
        docs = state.get("all_retrieved_docs", [])
        
        issues = []
        
        if details.get("semantic_match", 0) < 0.7:
            issues.append("poor semantic match")
        
        if len(docs) < 3:
            issues.append("insufficient results")
        
        if details.get("recency", 0) < 0.5:
            issues.append("results too old")
        
        if details.get("cross_validation", 0) < 0.7:
            issues.append("incomplete coverage of sub-queries")
        
        return ", ".join(issues) if issues else "unknown"
    
    def _reformulate_query(self, original_query: str, low_confidence_reason: str, existing_results: int) -> str:
        """Reformulate the query using LLM to improve retrieval results."""
        try:
            prompt = f"""The original query returned low-confidence results. Reformulate it to improve retrieval.

Original Query: "{original_query}"
Issue: {low_confidence_reason}
Current Results: {existing_results} documents

Reformulation strategies:
- Expand with synonyms or related terms
- Add more specific context
- Break down into clearer components
- Use more searchable terminology

Respond in JSON format:
{{
  "reformulated_query": "improved query here",
  "strategy": "brief explanation of changes"
}}"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a query reformulation expert. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                response_format={"type": "json_object"}
            )
            
            from backend.utils.json_parser import extract_json_from_response
            content = response.choices[0].message.content
            result = extract_json_from_response(content)
            
            if not result:
                raise ValueError("Failed to parse JSON from response")
            reformulated = result.get("reformulated_query", original_query)
            
            logger.info(f"Reformulation strategy: {result.get('strategy', 'N/A')}")
            return reformulated
            
        except Exception as e:
            logger.error(f"Query reformulation error: {e}")
            return f"information about {original_query}"


def self_healing_node(state: AgentState) -> AgentState:
    """LangGraph node for self-healing."""
    agent = SelfHealingAgent()
    return agent.heal(state)
