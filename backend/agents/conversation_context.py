"""Manages conversation history and context for follow-up questions."""
from typing import List, Dict, Any, Optional
from backend.database import get_db_session, Conversation
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


class ConversationContext:
    """Manages conversation history and context for follow-up questions."""
    
    def __init__(self):
        """Initialize the conversation context manager."""
        pass
    
    def get_conversation_history(self, thread_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get recent conversation history for a thread from the database."""
        try:
            db = get_db_session()
            try:
                conversations = db.query(Conversation).filter(
                    Conversation.thread_id == thread_id
                ).order_by(Conversation.created_at.desc()).limit(limit).all()
                
                history = []
                for conv in reversed(conversations):
                    history.append({
                        "query": conv.query,
                        "response": conv.response,
                        "confidence_score": conv.confidence_score,
                        "created_at": conv.created_at.isoformat() if conv.created_at else None
                    })
                
                logger.info(f"Retrieved {len(history)} previous messages for thread {thread_id}")
                return history
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error retrieving conversation history: {e}")
            return []
    
    def is_follow_up_question(self, query: str, history: List[Dict[str, Any]]) -> bool:
        """Determine if query is a follow-up question based on indicators and history."""
        if not history:
            return False
        
        follow_up_indicators = [
            "what about", "how about", "and", "also", "tell me more",
            "what else", "another", "similar", "related", "follow up",
            "more details", "explain", "clarify", "elaborate",
            "it", "that", "this", "they", "them", "those"
        ]
        
        query_lower = query.lower()
        
        # Check for explicit follow-up indicators
        if any(indicator in query_lower for indicator in follow_up_indicators):
            return True
        
        # Check if query is very short (likely referring to previous context)
        if len(query.split()) <= 3:
            return True
        
        # Check if query uses pronouns (likely referring to previous context)
        pronouns = ["it", "that", "this", "they", "them", "those", "he", "she", "his", "her"]
        if any(pronoun in query_lower.split() for pronoun in pronouns):
            return True
        
        return False
    
    def _resolve_references_and_rewrite(
        self,
        query: str,
        history: List[Dict[str, Any]]
    ) -> str:
        """Enhance query by resolving references from conversation context."""
        if not history:
            return query
        
        context_summary = []
        for i, msg in enumerate(history[-3:], 1):
            context_summary.append(f"Q{i}: {msg['query']}")
            context_summary.append(f"A{i}: {msg['response'][:300]}...")
        
        context_text = "\n".join(context_summary)
        
        from openai import OpenAI
        from backend.utils.config import settings
        from backend.utils.json_parser import extract_json_from_response
        
        client = OpenAI(api_key=settings.openai_api_key)
        
        prompt = f"""You are a query enhancement assistant. Your task is to rewrite the user's query by resolving any references to previous conversation context.

Current Query: "{query}"

Previous Conversation Context:
{context_text}

Your task:
1. Identify any references in the current query (e.g., "this file", "that document", "it", "they", "for San Francisco", "from there", etc.)
2. Look in the previous conversation context to find what these references refer to
3. Rewrite the query to be explicit and self-contained, replacing references with actual entities

Examples:
- "Give the content of this file" + context mentions "Preleaded stories 1 - Romeo and Juliet.pdf" → "Give the content of the file Preleaded stories 1 - Romeo and Juliet.pdf"
- "give for San Francisco" + context mentions "list all employees" → "list all employees from San Francisco"
- "What about that?" + context mentions "Q4 financial results" → "What about Q4 financial results?"

Rules:
- Only rewrite if there are clear references that can be resolved from context
- Keep the query natural and clear
- Don't add unnecessary information
- If no references can be resolved, return the original query unchanged

Respond in JSON format:
{{
  "enhanced_query": "the rewritten query with references resolved",
  "references_resolved": ["list of references that were resolved"],
  "reasoning": "brief explanation of what was changed"
}}"""
        
        try:
            response = client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": "You are a query enhancement expert. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            result = extract_json_from_response(content)
            
            if result and "enhanced_query" in result:
                enhanced = result["enhanced_query"].strip()
                references = result.get("references_resolved", [])
                reasoning = result.get("reasoning", "")
                
                if enhanced and enhanced != query:
                    logger.info(f"Query enhanced: '{query}' → '{enhanced}'")
                    if references:
                        logger.info(f"Resolved references: {references}")
                    if reasoning:
                        logger.info(f"Reasoning: {reasoning}")
                    return enhanced
                else:
                    logger.info("No references to resolve, using original query")
                    return query
            else:
                logger.warning("Failed to extract enhanced query from LLM response")
                return query
                
        except Exception as e:
            logger.error(f"Error enhancing query with context: {e}")
            return query
    
    def enhance_query_with_context(
        self,
        query: str,
        thread_id: str
    ) -> Dict[str, Any]:
        """Enhance query with conversation context by resolving references."""
        history = self.get_conversation_history(thread_id, limit=5)
        is_follow_up = self.is_follow_up_question(query, history)
        
        if is_follow_up and history:
            enhanced_query = self._resolve_references_and_rewrite(query, history)
            logger.info(f"Enhanced follow-up question with resolved references (thread: {thread_id})")
            return {
                "original_query": query,
                "enhanced_query": enhanced_query,
                "is_follow_up": True,
                "history": history
            }
        else:
            return {
                "original_query": query,
                "enhanced_query": query,
                "is_follow_up": False,
                "history": history
            }


conversation_context = ConversationContext()
