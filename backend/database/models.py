"""SQLAlchemy database models."""
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, JSON, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime

Base = declarative_base()


class Conversation(Base):
    """Store conversation history."""
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(String(255), index=True, nullable=False)
    user_id = Column(String(255), index=True, default="default_user")
    query = Column(Text, nullable=False)
    response = Column(Text, nullable=False)
    confidence_score = Column(Float, nullable=True)
    citations = Column(JSON, nullable=True)
    decomposed_queries = Column(JSON, nullable=True)
    self_healing_triggered = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<Conversation(id={self.id}, thread_id={self.thread_id})>"


class QueryCache(Base):
    """Cache query results for faster retrieval."""
    __tablename__ = "query_cache"
    
    id = Column(Integer, primary_key=True, index=True)
    query_text = Column(Text, nullable=False)
    query_embedding_hash = Column(String(64), index=True, unique=True, nullable=False)
    answer = Column(Text, nullable=False)
    citations = Column(JSON, nullable=True)
    confidence_score = Column(Float, nullable=True)
    hit_count = Column(Integer, default=1)
    avg_feedback_score = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self):
        return f"<QueryCache(id={self.id}, hash={self.query_embedding_hash})>"


class UserFeedback(Base):
    """Store user feedback for continuous learning."""
    __tablename__ = "user_feedback"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, index=True, nullable=False)
    thread_id = Column(String(255), index=True, nullable=False)
    feedback_type = Column(String(50), nullable=False)  # helpful, not_helpful
    feedback_score = Column(Integer, nullable=True)  # 1-5 rating
    feedback_text = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<UserFeedback(id={self.id}, type={self.feedback_type})>"


class DocumentMetadata(Base):
    """Store metadata about ingested documents."""
    __tablename__ = "document_metadata"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(String(255), unique=True, index=True, nullable=False)
    source_type = Column(String(50), index=True, nullable=False)  # slack, google_docs, etc.
    source_id = Column(String(255), nullable=False)
    title = Column(String(500), nullable=True)
    url = Column(String(1000), nullable=True)
    author = Column(String(255), nullable=True)
    created_date = Column(DateTime(timezone=True), nullable=True)
    updated_date = Column(DateTime(timezone=True), nullable=True)
    access_control = Column(JSON, nullable=True)  # roles/users who can access
    chunk_count = Column(Integer, default=0)
    indexed_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<DocumentMetadata(id={self.id}, source={self.source_type})>"
