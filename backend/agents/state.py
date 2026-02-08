"""Agent state definition for LangGraph workflow."""
from typing import TypedDict, List, Dict, Any, Optional


class AgentState(TypedDict):
    """State object passed between agents in the LangGraph workflow."""
    
    # Input
    original_query: str
    thread_id: str
    user_id: str
    
    # Conversation Context
    conversation_history: Optional[List[Dict[str, Any]]]  # Previous messages in thread
    is_follow_up: Optional[bool]  # Whether this is a follow-up question
    enhanced_query: Optional[str]  # Query enhanced with conversation context
    
    # Query Analysis
    query_intent: Optional[str]
    extracted_entities: Optional[List[str]]
    is_complex: Optional[bool]
    corrected_query: Optional[str]  # Auto-corrected query if typos detected
    typo_correction_message: Optional[str]  # Message about typo correction
    
    # Query Decomposition
    decomposed_queries: Optional[List[str]]
    
    # Routing
    source_routing: Optional[Dict[str, List[str]]]  # query -> sources
    
    # Retrieval
    retrieved_docs: Optional[Dict[str, List[Dict[str, Any]]]]  # query -> docs
    all_retrieved_docs: Optional[List[Dict[str, Any]]]  # Deduplicated
    
    # Confidence Scoring
    confidence_score: Optional[float]
    confidence_details: Optional[Dict[str, float]]
    
    # Self-Healing
    self_healing_triggered: bool
    retry_count: int
    reformulated_query: Optional[str]
    
    # Synthesis
    final_answer: Optional[str]
    citations: Optional[List[Dict[str, Any]]]
    
    # Metadata
    error: Optional[str]
    processing_steps: List[str]
