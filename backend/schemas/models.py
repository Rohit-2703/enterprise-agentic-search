"""Pydantic schemas for API request/response models."""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class QueryRequest(BaseModel):
    """User query request."""
    query: str = Field(..., description="User query text")
    thread_id: Optional[str] = Field(None, description="Conversation thread ID")
    user_id: Optional[str] = Field("default_user", description="User identifier")


class Citation(BaseModel):
    """Citation information."""
    source_type: str = Field(..., description="Source type (slack, google_docs, etc.)")
    source_id: str = Field(..., description="Source document ID")
    title: str = Field(..., description="Document title")
    snippet: str = Field(..., description="Relevant text snippet")
    confidence: float = Field(..., description="Citation confidence score")
    url: Optional[str] = Field(None, description="Source URL")


class ConfidenceScore(BaseModel):
    """Detailed confidence scoring."""
    overall: float = Field(..., description="Overall confidence score (0-1)")
    semantic_match: float = Field(..., description="Semantic similarity score")
    source_authority: float = Field(..., description="Source authority score")
    recency: float = Field(..., description="Recency score")
    cross_validation: float = Field(..., description="Cross-validation score")


class QueryResponse(BaseModel):
    """Query response with answer and metadata."""
    answer: str = Field(..., description="Generated answer")
    citations: List[Citation] = Field(default_factory=list, description="Source citations")
    confidence_score: ConfidenceScore = Field(..., description="Confidence metrics")
    decomposed_queries: Optional[List[str]] = Field(None, description="Sub-queries if decomposed")
    self_healing_triggered: bool = Field(False, description="Whether self-healing was triggered")
    thread_id: str = Field(..., description="Conversation thread ID")
    processing_time_ms: float = Field(..., description="Processing time in milliseconds")


class FeedbackRequest(BaseModel):
    """User feedback on a response."""
    conversation_id: int = Field(..., description="Conversation ID")
    thread_id: str = Field(..., description="Thread ID")
    feedback_type: str = Field(..., description="Feedback type: helpful, not_helpful")
    feedback_score: Optional[int] = Field(None, description="Rating 1-5")
    feedback_text: Optional[str] = Field(None, description="Optional feedback text")


class ConversationHistory(BaseModel):
    """Conversation history item."""
    id: int
    query: str
    response: str
    confidence_score: Optional[float]
    created_at: datetime


class CacheStats(BaseModel):
    """Cache statistics."""
    redis_stats: Dict[str, Any] = Field(default_factory=dict)
    postgres_stats: Dict[str, Any] = Field(default_factory=dict)


class HealthCheck(BaseModel):
    """Health check response."""
    status: str = Field(..., description="Service status")
    redis_healthy: bool = Field(..., description="Redis health status")
    postgres_healthy: bool = Field(..., description="PostgreSQL health status")
    pinecone_healthy: bool = Field(..., description="Pinecone health status")


class ThreadInfo(BaseModel):
    """Thread information."""
    thread_id: str = Field(..., description="Thread ID")
    user_id: str = Field(..., description="User ID")
    last_message_at: datetime = Field(..., description="Last message timestamp")
    message_count: int = Field(..., description="Number of messages in thread")
    last_query: Optional[str] = Field(None, description="Last query in thread")
