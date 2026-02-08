"""Conversation context node for LangGraph workflow."""
from backend.agents.state import AgentState
from backend.agents.conversation_context import conversation_context
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


def conversation_context_node(state: AgentState) -> AgentState:
    """
    Load conversation history and enhance query with context.
    
    Args:
        state: Current agent state
    
    Returns:
        Updated state with conversation context
    """
    try:
        thread_id = state.get("thread_id", "default")
        original_query = state.get("original_query", "")
        
        # Enhance query with conversation context
        context_info = conversation_context.enhance_query_with_context(
            query=original_query,
            thread_id=thread_id
        )
        
        # Update state with context
        state["conversation_history"] = context_info["history"]
        state["is_follow_up"] = context_info["is_follow_up"]
        state["enhanced_query"] = context_info["enhanced_query"]
        
        if context_info["is_follow_up"]:
            logger.info(f"Detected follow-up question for thread {thread_id}")
            logger.info(f"Enhanced query: {context_info['enhanced_query'][:200]}...")
        else:
            logger.info(f"New conversation query for thread {thread_id}")
        
        return state
        
    except Exception as e:
        logger.error(f"Error in conversation context node: {e}")
        # Continue with original query if context loading fails
        state["conversation_history"] = []
        state["is_follow_up"] = False
        state["enhanced_query"] = state.get("original_query", "")
        return state
