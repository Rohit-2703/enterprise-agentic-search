"""FastAPI application for enterprise search."""
import time
import uuid
from fastapi import FastAPI, HTTPException, Depends, Form
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from datetime import datetime

from backend.schemas.models import (
    QueryRequest,
    QueryResponse,
    FeedbackRequest,
    ConversationHistory,
    CacheStats,
    HealthCheck,
    ConfidenceScore,
    Citation,
    ThreadInfo
)
from backend.database import (
    init_db,
    get_db,
    Conversation,
    UserFeedback,
    DocumentMetadata
)
from backend.agents import run_agent_workflow, run_agent_workflow_streaming
from backend.cache import redis_cache, postgres_cache
from backend.retrieval import pinecone_client, embedding_generator
from backend.utils.config import settings
from backend.utils.logger import setup_logger
from backend.utils.chunking import DocumentChunker
import json

logger = setup_logger(__name__)

app = FastAPI(
    title="Enterprise Agentic Search API",
    description="Intelligent search system with multi-agent orchestration",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    logger.info("Starting Enterprise Search API...")
    
    init_db()
    logger.info("Database initialized")
    
    if redis_cache.health_check():
        logger.info("Redis connected successfully")
    else:
        logger.warning("Redis connection failed")
    
    if pinecone_client.health_check():
        logger.info("Pinecone connected successfully")
    else:
        logger.warning("Pinecone connection failed")
    
    logger.info("API startup complete")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Enterprise Agentic Search API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health", response_model=HealthCheck)
async def health_check():
    """Health check endpoint."""
    return HealthCheck(
        status="healthy",
        redis_healthy=redis_cache.health_check(),
        postgres_healthy=True,
        pinecone_healthy=pinecone_client.health_check()
    )


@app.post("/query", response_model=QueryResponse)
async def query(
    request: QueryRequest,
    db: Session = Depends(get_db)
):
    """Process a user query (non-streaming)."""
    start_time = time.time()
    
    thread_id = request.thread_id or str(uuid.uuid4())
    
    logger.info(f"Processing query: {request.query}")
    
    try:
        if settings.enable_caching:
            cached_result = redis_cache.get_query_result(request.query)
            if cached_result:
                logger.info("Returning cached result from Redis")
                processing_time = (time.time() - start_time) * 1000
                
                return QueryResponse(
                    answer=cached_result["answer"],
                    citations=[Citation(**c) for c in cached_result.get("citations", [])],
                    confidence_score=ConfidenceScore(**cached_result["confidence_score"]),
                    thread_id=thread_id,
                    processing_time_ms=processing_time,
                    self_healing_triggered=False
                )
            
            cached_result = postgres_cache.get_query_result(request.query)
            if cached_result:
                logger.info("Returning cached result from PostgreSQL")
                processing_time = (time.time() - start_time) * 1000
                
                redis_cache.set_query_result(request.query, cached_result)
                
                return QueryResponse(
                    answer=cached_result["answer"],
                    citations=[Citation(**c) for c in cached_result.get("citations", [])],
                    confidence_score=ConfidenceScore(**cached_result["confidence_score"]),
                    thread_id=thread_id,
                    processing_time_ms=processing_time,
                    self_healing_triggered=False
                )
        
        final_state = run_agent_workflow(
            query=request.query,
            thread_id=thread_id,
            user_id=request.user_id
        )
        
        confidence_details = final_state.get("confidence_details", {})
        confidence_score = ConfidenceScore(
            overall=final_state.get("confidence_score", 0.0),
            semantic_match=confidence_details.get("semantic_match", 0.0),
            source_authority=confidence_details.get("source_authority", 0.0),
            recency=confidence_details.get("recency", 0.0),
            cross_validation=confidence_details.get("cross_validation", 0.0)
        )
        
        citations = [Citation(**c) for c in final_state.get("citations", [])]
        
        response = QueryResponse(
            answer=final_state.get("final_answer", ""),
            citations=citations,
            confidence_score=confidence_score,
            decomposed_queries=final_state.get("decomposed_queries"),
            self_healing_triggered=final_state.get("self_healing_triggered", False),
            thread_id=thread_id,
            processing_time_ms=(time.time() - start_time) * 1000
        )
        
        conversation = Conversation(
            thread_id=thread_id,
            user_id=request.user_id,
            query=request.query,
            response=final_state.get("final_answer", ""),
            confidence_score=final_state.get("confidence_score"),
            citations=final_state.get("citations"),
            decomposed_queries=final_state.get("decomposed_queries"),
            self_healing_triggered=final_state.get("self_healing_triggered", False)
        )
        db.add(conversation)
        db.commit()
        
        if settings.enable_caching and final_state.get("confidence_score", 0) >= 0.7:
            cache_data = {
                "answer": response.answer,
                "citations": [c.dict() for c in response.citations],
                "confidence_score": confidence_score.dict()
            }
            redis_cache.set_query_result(request.query, cache_data)
            postgres_cache.set_query_result(
                request.query,
                response.answer,
                [c.dict() for c in response.citations],
                response.confidence_score.overall
            )
        
        return response
        
    except Exception as e:
        logger.error(f"Query processing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/query/stream")
async def query_stream(request: QueryRequest, db: Session = Depends(get_db)):
    """Process a user query with streaming response."""
    thread_id = request.thread_id or str(uuid.uuid4())
    final_answer = ""
    final_citations = []
    final_confidence = None
    final_decomposed_queries = None
    final_self_healing = False
    
    async def generate():
        nonlocal final_answer, final_citations, final_confidence, final_decomposed_queries, final_self_healing
        try:
            for event in run_agent_workflow_streaming(
                query=request.query,
                thread_id=thread_id,
                user_id=request.user_id
            ):
                if event.get("type") == "synthesis_complete":
                    state = event.get("state", {})
                    final_answer = state.get("final_answer", "")
                    final_citations = state.get("citations", [])
                    final_confidence = state.get("confidence_score")
                    final_decomposed_queries = state.get("decomposed_queries")
                    final_self_healing = state.get("self_healing_triggered", False)
                
                yield f"data: {json.dumps(event)}\n\n"
            
            try:
                conversation = Conversation(
                    thread_id=thread_id,
                    user_id=request.user_id,
                    query=request.query,
                    response=final_answer,
                    confidence_score=final_confidence,
                    citations=final_citations,
                    decomposed_queries=final_decomposed_queries,
                    self_healing_triggered=final_self_healing
                )
                db.add(conversation)
                db.commit()
                logger.info(f"Saved conversation to database for thread {thread_id}")
            except Exception as e:
                logger.error(f"Error saving conversation to database: {e}")
                
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream"
    )


@app.post("/feedback")
async def submit_feedback(
    feedback: FeedbackRequest,
    db: Session = Depends(get_db)
):
    """Submit user feedback."""
    try:
        user_feedback = UserFeedback(
            conversation_id=feedback.conversation_id,
            thread_id=feedback.thread_id,
            feedback_type=feedback.feedback_type,
            feedback_score=feedback.feedback_score,
            feedback_text=feedback.feedback_text
        )
        db.add(user_feedback)
        db.commit()
        
        if feedback.feedback_score:
            conversation = db.query(Conversation).filter(
                Conversation.id == feedback.conversation_id
            ).first()
            if conversation:
                postgres_cache.update_feedback(
                    conversation.query,
                    float(feedback.feedback_score)
                )
        
        return {"message": "Feedback submitted successfully"}
    except Exception as e:
        logger.error(f"Feedback submission error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/conversations/{thread_id}", response_model=List[ConversationHistory])
async def get_conversation_history(
    thread_id: str,
    db: Session = Depends(get_db)
):
    """Get conversation history for a thread."""
    try:
        conversations = db.query(Conversation).filter(
            Conversation.thread_id == thread_id
        ).order_by(Conversation.created_at.desc()).limit(50).all()
        
        return [
            ConversationHistory(
                id=conv.id,
                query=conv.query,
                response=conv.response,
                confidence_score=conv.confidence_score,
                created_at=conv.created_at
            )
            for conv in conversations
        ]
    except Exception as e:
        logger.error(f"Error fetching conversation history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/threads", response_model=List[ThreadInfo])
async def list_all_threads(
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List all conversation threads."""
    try:
        from sqlalchemy import func
        
        threads_query = db.query(
            Conversation.thread_id,
            Conversation.user_id,
            func.max(Conversation.created_at).label('last_message_at'),
            func.count(Conversation.id).label('message_count')
        ).group_by(
            Conversation.thread_id,
            Conversation.user_id
        ).order_by(
            func.max(Conversation.created_at).desc()
        ).limit(limit).all()
        
        thread_info_list = []
        for thread_id, user_id, last_message_at, message_count in threads_query:
            last_conv = db.query(Conversation).filter(
                Conversation.thread_id == thread_id
            ).order_by(Conversation.created_at.desc()).first()
            
            thread_info_list.append(ThreadInfo(
                thread_id=thread_id,
                user_id=user_id,
                last_message_at=last_message_at,
                message_count=message_count,
                last_query=last_conv.query if last_conv else None
            ))
        
        return thread_info_list
    except Exception as e:
        logger.error(f"Error listing threads: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/cache/stats", response_model=CacheStats)
async def get_cache_stats():
    """Get cache statistics."""
    return CacheStats(
        redis_stats=redis_cache.get_stats(),
        postgres_stats=postgres_cache.get_stats()
    )


@app.post("/cache/clear")
async def clear_cache():
    """Clear all caches."""
    try:
        redis_cache.clear_all()
        return {"message": "Cache cleared successfully"}
    except Exception as e:
        logger.error(f"Cache clear error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/documents/upload")
async def upload_document(
    text: str = Form(...),
    title: str = Form(...),
    source_type: str = Form("custom_upload"),
    chunking_strategy: str = Form("auto"),
    max_chunk_size: int = Form(1000),
    db: Session = Depends(get_db)
):
    """Upload and index a document to Pinecone."""
    try:
        if not text:
            raise HTTPException(status_code=400, detail="Text content must be provided")
        
        text_content = text
        logger.info(f"Received text content ({len(text_content)} chars)")
        
        chunker = DocumentChunker()
        chunks = chunker.smart_chunk(
            text=text_content,
            strategy=chunking_strategy,
            max_chunk_size=max_chunk_size
        )
        
        logger.info(f"Created {len(chunks)} chunks using {chunking_strategy} strategy")
        
        import hashlib
        doc_id = hashlib.md5(text_content.encode()).hexdigest()
        
        vectors = []
        for chunk in chunks:
            try:
                embedding = embedding_generator.generate(chunk["text"], use_cache=False)
                
                metadata = {
                    "source_type": source_type,
                    "source_id": f"{doc_id}_chunk_{chunk['chunk_id']}",
                    "title": f"{title} - {chunk['title']}",
                    "text": chunk["text"][:1000],
                    "timestamp": datetime.now().isoformat(),
                    "author": "user_upload",
                    "url": "",
                    "chunk_id": chunk["chunk_id"],
                    "total_chunks": len(chunks),
                    "chunking_strategy": chunk["strategy"]
                }
                
                vector_id = f"{doc_id}_chunk_{chunk['chunk_id']}"
                vectors.append((vector_id, embedding, metadata))
                
            except Exception as e:
                logger.error(f"Error processing chunk {chunk['chunk_id']}: {e}")
                continue
        
        if vectors:
            batch_size = 100
            for i in range(0, len(vectors), batch_size):
                batch = vectors[i:i + batch_size]
                pinecone_client.upsert_documents(batch)
                logger.info(f"Uploaded batch {i//batch_size + 1}/{(len(vectors)-1)//batch_size + 1}")
        
        doc_metadata = DocumentMetadata(
            document_id=doc_id,
            source_type=source_type,
            source_id=doc_id,
            title=title,
            url="",
            author="user_upload",
            created_date=datetime.now(),
            chunk_count=len(chunks)
        )
        db.add(doc_metadata)
        db.commit()
        
        logger.info(f"Successfully uploaded document: {title} ({len(chunks)} chunks)")
        
        return {
            "message": "Document uploaded successfully",
            "document_id": doc_id,
            "title": title,
            "chunks_created": len(chunks),
            "chunks_indexed": len(vectors),
            "chunking_strategy": chunking_strategy
        }
        
    except Exception as e:
        logger.error(f"Document upload error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/documents/list")
async def list_uploaded_documents(
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List documents from Pinecone."""
    try:
        pinecone_docs = pinecone_client.list_all_documents(top_k=10000)
        
        documents_list = list(pinecone_docs.values())
        
        documents_list.sort(
            key=lambda x: x.get("indexed_at", ""),
            reverse=True
        )
        
        limited_docs = documents_list[:limit]
        
        formatted_docs = []
        for doc in limited_docs:
            formatted_docs.append({
                "document_id": doc["document_id"],
                "title": doc["title"],
                "source_type": doc["source_type"],
                "author": doc["author"],
                "chunk_count": doc["chunk_count"],
                "indexed_at": doc["indexed_at"] if doc["indexed_at"] else datetime.now().isoformat()
            })
        
        return {
            "documents": formatted_docs,
            "total": len(documents_list)
        }
    except Exception as e:
        logger.error(f"Error listing documents from Pinecone: {e}")
        try:
            total_count = db.query(func.count(DocumentMetadata.id)).scalar()
            docs = db.query(DocumentMetadata).order_by(
                DocumentMetadata.indexed_at.desc()
            ).limit(limit).all()
            
            return {
                "documents": [
                    {
                        "document_id": doc.document_id,
                        "title": doc.title,
                        "source_type": doc.source_type,
                        "author": doc.author,
                        "chunk_count": doc.chunk_count,
                        "indexed_at": doc.indexed_at.isoformat()
                    }
                    for doc in docs
                ],
                "total": total_count
            }
        except Exception as fallback_error:
            logger.error(f"Fallback to PostgreSQL also failed: {fallback_error}")
            raise HTTPException(status_code=500, detail=str(e))


@app.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    db: Session = Depends(get_db)
):
    """Delete a document from Pinecone and database."""
    try:
        doc = db.query(DocumentMetadata).filter(
            DocumentMetadata.document_id == document_id
        ).first()
        
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        
        chunk_ids = [f"{document_id}_chunk_{i}" for i in range(doc.chunk_count)]
        
        try:
            batch_size = 1000
            for i in range(0, len(chunk_ids), batch_size):
                batch = chunk_ids[i:i + batch_size]
                try:
                    pinecone_client.delete(batch)
                    logger.info(f"Deleted batch {i//batch_size + 1} of chunks from Pinecone")
                except Exception as batch_error:
                    logger.warning(f"Error deleting batch {i//batch_size + 1}: {batch_error}")
        except Exception as e:
            logger.error(f"Error deleting chunks from Pinecone: {e}")
        
        db.delete(doc)
        db.commit()
        
        logger.info(f"Deleted document: {document_id}")
        
        return {
            "message": "Document deleted successfully",
            "document_id": document_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)
