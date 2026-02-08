"""Breaks complex queries into simpler sub-questions for better retrieval."""
from typing import Dict, Any
from openai import OpenAI
from backend.agents.state import AgentState
from backend.utils.config import settings
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


class QueryDecompositionAgent:
    """Decomposes complex queries into simpler sub-queries."""
    
    def __init__(self):
        """Initialize the OpenAI client for query decomposition."""
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
    
    def decompose(self, state: AgentState) -> AgentState:
        """Decompose complex query into simpler sub-queries if needed."""
        query = state.get("enhanced_query") or state["original_query"]
        is_complex = state.get("is_complex", False)
        
        if not settings.enable_query_decomposition or not is_complex:
            logger.info("Query decomposition skipped (not complex or disabled)")
            state["decomposed_queries"] = [query]
            state["processing_steps"].append("Query Decomposition: Skipped (simple query)")
            return state
        
        logger.info(f"Decomposing complex query: {query}")
        
        try:
            prompt = f"""Break down this complex query into 2-4 simpler sub-questions that, when answered together, would fully address the original query.

Original Query: "{query}"

Guidelines:
- Each sub-question should be self-contained
- Cover different aspects of the original query
- Be specific and searchable
- Maintain temporal context if present

Respond in JSON format:
{{
  "sub_queries": ["sub-question 1", "sub-question 2", ...],
  "reasoning": "brief explanation"
}}"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert at breaking down complex questions. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                response_format={"type": "json_object"}  # Force JSON response
            )
            
            from backend.utils.json_parser import extract_json_from_response
            content = response.choices[0].message.content
            decomposition = extract_json_from_response(content)
            
            if not decomposition:
                raise ValueError("Failed to parse JSON from response")
            
            sub_queries = decomposition.get("sub_queries", [query])
            if not sub_queries:
                sub_queries = [query]
            
            state["decomposed_queries"] = sub_queries
            state["processing_steps"].append(f"Query Decomposition: Created {len(sub_queries)} sub-queries")
            
            logger.info(f"Decomposed into {len(sub_queries)} sub-queries: {sub_queries}")
            
        except Exception as e:
            logger.error(f"Query decomposition error: {e}")
            state["decomposed_queries"] = [query]
            state["processing_steps"].append("Query Decomposition: Fallback to original query")
        
        return state


def query_decomposition_node(state: AgentState) -> AgentState:
    """LangGraph node for query decomposition."""
    agent = QueryDecompositionAgent()
    return agent.decompose(state)
