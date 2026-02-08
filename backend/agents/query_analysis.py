"""Query Analysis Agent - Analyzes and normalizes user queries."""
from typing import Dict, Any, Optional
from openai import OpenAI
from backend.agents.state import AgentState
from backend.utils.config import settings
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


class QueryAnalysisAgent:
    """Analyzes user queries to extract intent and entities."""
    
    def __init__(self):
        """Initialize OpenAI client."""
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
    
    def _detect_and_correct_typos(self, query: str) -> tuple[str, Optional[str]]:
        """Detect and correct typos, spelling errors, and grammar issues in the query."""
        try:
            prompt = f"""Analyze this query for typos, spelling errors, and grammar issues.
If you find any errors, provide the corrected version. If the query is correct, return the same query.

Query: "{query}"

Respond in JSON format:
{{
  "has_errors": true/false,
  "corrected_query": "corrected version here (same as original if no errors)",
  "errors_found": ["typo", "spelling", "grammar"] (empty array if none),
  "confidence": 0.0-1.0 (confidence in correction)
}}"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert at detecting and correcting typos, spelling errors, and grammar issues. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            from backend.utils.json_parser import extract_json_from_response
            content = response.choices[0].message.content
            result = extract_json_from_response(content)
            
            if not result:
                return query, None
            
            has_errors = result.get("has_errors", False)
            corrected = result.get("corrected_query", query)
            confidence = result.get("confidence", 0.0)
            
            if has_errors and confidence > 0.7 and corrected.lower().strip() != query.lower().strip():
                message = f"Did you mean: \"{corrected}\"? Querying for this..."
                logger.info(f"Typo detected and corrected: '{query}' -> '{corrected}'")
                return corrected, message
            
            return query, None
            
        except Exception as e:
            logger.error(f"Typo detection error: {e}")
            return query, None
    
    def analyze(self, state: AgentState) -> AgentState:
        """Analyze the user query."""
        query = state.get("enhanced_query") or state.get("original_query", "")
        logger.info(f"Analyzing query: {query}")
        
        # Detect and correct typos first
        corrected_query, correction_message = self._detect_and_correct_typos(query)
        
        if correction_message:
            # Update query to use corrected version
            state["corrected_query"] = corrected_query
            state["typo_correction_message"] = correction_message
            state["processing_steps"].append(f"Typo Correction: {correction_message}")
            query = corrected_query
            if state.get("enhanced_query"):
                state["enhanced_query"] = corrected_query
        
        try:
            # Analyze query using GPT-4o
            prompt = f"""Analyze this user query and provide:
1. Intent (information_retrieval, comparison, temporal_analysis, troubleshooting, etc.)
2. Key entities mentioned (products, people, dates, technical terms, etc.)
3. Complexity assessment (simple or complex)

Query: "{query}"

Respond in JSON format:
{{
  "intent": "intent_type",
  "entities": ["entity1", "entity2"],
  "is_complex": true/false,
  "reasoning": "brief explanation"
}}"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a query analysis expert. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            
            # Parse response
            from backend.utils.json_parser import extract_json_from_response
            content = response.choices[0].message.content
            analysis = extract_json_from_response(content)
            
            if not analysis:
                raise ValueError("Failed to parse JSON from response")
            
            # Update state
            state["query_intent"] = analysis.get("intent", "information_retrieval")
            state["extracted_entities"] = analysis.get("entities", [])
            state["is_complex"] = analysis.get("is_complex", False)
            state["processing_steps"].append(f"Query Analysis: {analysis.get('reasoning', 'Completed')}")
            
            logger.info(f"Query analysis complete - Intent: {state['query_intent']}, Complex: {state['is_complex']}")
            
        except Exception as e:
            logger.error(f"Query analysis error: {e}")
            # Fallback to simple analysis
            state["query_intent"] = "information_retrieval"
            state["extracted_entities"] = []
            state["is_complex"] = len(query.split()) > 15  # Simple heuristic
            state["processing_steps"].append(f"Query Analysis: Fallback used due to error")
        
        return state


# Agent function for LangGraph
def query_analysis_node(state: AgentState) -> AgentState:
    """LangGraph node for query analysis."""
    agent = QueryAnalysisAgent()
    return agent.analyze(state)
