"""Generates final answer with citations from retrieved documents."""
from typing import List, Dict, Any, Iterator
from openai import OpenAI
from backend.agents.state import AgentState
from backend.utils.config import settings
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


class SynthesisAgent:
    """Synthesizes final answer from retrieved documents with proper citations."""
    
    def __init__(self):
        """Initialize the OpenAI client for answer synthesis."""
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
    
    def synthesize(self, state: AgentState) -> AgentState:
        """Generate final answer with citations from retrieved documents."""
        query = state["original_query"]
        docs = state.get("all_retrieved_docs", [])
        
        if not docs:
            logger.warning("No documents available for synthesis")
            state["final_answer"] = "I couldn't find any relevant information to answer your question."
            state["citations"] = []
            return state
        
        logger.info(f"Synthesizing answer from {len(docs)} documents")
        
        context = self._build_context(docs)
        answer, citations = self._generate_answer(query, context, docs)
        
        state["final_answer"] = answer
        state["citations"] = citations
        state["processing_steps"].append(
            f"Synthesis: Generated answer with {len(citations)} citations"
        )
        
        logger.info(f"Synthesis complete with {len(citations)} citations")
        return state
    
    def synthesize_streaming(self, state: AgentState) -> Iterator[str]:
        """Generate streaming answer with citations, yielding chunks as they're generated."""
        query = state["original_query"]
        docs = state.get("all_retrieved_docs", [])
        
        if not docs:
            yield "I couldn't find any relevant information to answer your question."
            state["final_answer"] = "I couldn't find any relevant information to answer your question."
            state["citations"] = []
            return
        
        logger.info(f"Streaming synthesis from {len(docs)} documents")
        
        context = self._build_context(docs)
        
        # Generate streaming answer
        full_answer = ""
        for chunk in self._generate_answer_streaming(query, context):
            full_answer += chunk
            yield chunk
        
        # Extract and format citations
        citations = self._extract_citations(docs)
        
        state["final_answer"] = full_answer
        state["citations"] = citations
    
    def _build_context(self, docs: List[Dict[str, Any]]) -> str:
        """Build context string from documents."""
        context_parts = []
        
        for idx, doc in enumerate(docs[:10], 1):
            metadata = doc.get("metadata", {})
            text = metadata.get("text", "")
            source = metadata.get("source_type", "unknown")
            title = metadata.get("title", "Untitled")
            
            context_parts.append(
                f"[{idx}] Source: {source} - {title}\n{text}\n"
            )
        
        return "\n\n".join(context_parts)
    
    def _generate_answer(
        self,
        query: str,
        context: str,
        docs: List[Dict[str, Any]]
    ) -> tuple[str, List[Dict[str, Any]]]:
        """Generate answer with citations."""
        try:
            prompt = f"""Answer the following question based ONLY on the provided context. Include inline citations using [1], [2], etc.

Question: {query}

Context:
{context}

IMPORTANT INSTRUCTIONS FOR DATABASE RESULTS:
- If the context contains database query results in the format "key: value" (e.g., "count: 15", "employee_count: 50"), extract and use those numeric values directly as the answer
- Database results from PostgreSQL often appear as "Database Record 1" with content like "count: 15" or "column_name: value" - these ARE the answers to numeric questions
- When you see database results with numeric values, present them directly (e.g., "There are 15 employees from Engineering" if you see "count: 15")
- Do NOT say "the context doesn't specify" if database results contain the answer - use the values from the database results
- For COUNT queries, the result is typically in a format like "count: X" or "employee_count: X" - extract X as the answer

Guidelines:
- Provide a comprehensive, accurate answer
- Use inline citations [1], [2] for specific claims
- Synthesize information from multiple sources when relevant
- If information is insufficient, acknowledge limitations
- Be concise but complete

Answer:"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that answers questions based on provided context. Always include citations."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            
            answer = response.choices[0].message.content
            citations = self._extract_citations(docs)
            
            return answer, citations
            
        except Exception as e:
            logger.error(f"Answer generation error: {e}")
            return "An error occurred while generating the answer.", []
    
    def _generate_answer_streaming(
        self,
        query: str,
        context: str
    ) -> Iterator[str]:
        """Generate streaming answer."""
        try:
            prompt = f"""Answer the following question based ONLY on the provided context. Include inline citations using [1], [2], etc.

Question: {query}

Context:
{context}

IMPORTANT INSTRUCTIONS FOR DATABASE RESULTS:
- If the context contains database query results in the format "key: value" (e.g., "count: 15", "employee_count: 50"), extract and use those numeric values directly as the answer
- Database results from PostgreSQL often appear as "Database Record 1" with content like "count: 15" or "column_name: value" - these ARE the answers to numeric questions
- When you see database results with numeric values, present them directly (e.g., "There are 15 employees from Engineering" if you see "count: 15")
- Do NOT say "the context doesn't specify" if database results contain the answer - use the values from the database results
- For COUNT queries, the result is typically in a format like "count: X" or "employee_count: X" - extract X as the answer

Answer:"""
            
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that answers questions based on provided context. Always include citations."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                stream=True
            )
            
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            logger.error(f"Streaming answer generation error: {e}")
            yield "An error occurred while generating the answer."
    
    def _extract_citations(
        self,
        docs: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Extract citation information from documents."""
        citations = []
        
        for idx, doc in enumerate(docs[:10], 1):
            metadata = doc.get("metadata", {})
            
            citation = {
                "index": idx,
                "source_type": metadata.get("source_type", "unknown"),
                "source_id": metadata.get("source_id", ""),
                "title": metadata.get("title", "Untitled"),
                "snippet": metadata.get("text", "")[:200] + "...",
                "confidence": round(doc.get("score", 0.0), 3),
                "url": metadata.get("url", "")
            }
            
            citations.append(citation)
        
        return citations


def synthesis_node(state: AgentState) -> AgentState:
    """LangGraph node for synthesis."""
    agent = SynthesisAgent()
    return agent.synthesize(state)
