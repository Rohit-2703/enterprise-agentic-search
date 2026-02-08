"""Initialize database and load enterprise knowledge base."""
import sys
import os
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.retrieval import pinecone_client, embedding_generator
from backend.database import init_db, get_db_session, DocumentMetadata
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


def main():
    """Initialize database and load enterprise knowledge base."""
    logger.info("=== Starting Data Initialization ===")
    
    logger.info("Initializing database...")
    init_db()
    
    logger.info("Loading enterprise knowledge base...")
    kb_path = "data/enterprise_knowledge_base.txt"
    kb_chunks = None
    
    if os.path.exists(kb_path):
        from backend.utils.chunking import DocumentChunker
        
        with open(kb_path, 'r', encoding='utf-8') as f:
            kb_text = f.read()
        
        logger.info(f"Loaded knowledge base: {len(kb_text)} characters")
        
        chunker = DocumentChunker()
        kb_chunks = chunker.smart_chunk(kb_text, strategy="sections", max_chunk_size=1500)
        
        logger.info(f"Created {len(kb_chunks)} chunks from knowledge base")
        
        kb_vectors = []
        for chunk_data in kb_chunks:
            chunk_id = f"kb_{chunk_data['chunk_id']}"
            embedding = embedding_generator.generate(chunk_data['text'], use_cache=False)
            
            metadata = {
                "source_type": "wiki",
                "source_id": chunk_id,
                "title": chunk_data['title'],
                "text": chunk_data['text'][:1000],
                "timestamp": datetime.now().isoformat(),
                "author": "system",
                "url": "",
                "access_control": "all"
            }
            
            kb_vectors.append((chunk_id, embedding, metadata))
        
        batch_size = 100
        for i in range(0, len(kb_vectors), batch_size):
            batch = kb_vectors[i:i + batch_size]
            pinecone_client.upsert_documents(batch)
            logger.info(f"Uploaded KB batch {i//batch_size + 1}/{(len(kb_vectors)-1)//batch_size + 1}")
        
        logger.info(f"Indexed {len(kb_vectors)} knowledge base chunks to Pinecone")
        
        with get_db_session() as db:
            kb_metadata = DocumentMetadata(
                document_id="enterprise_kb",
                source_type="wiki",
                source_id="enterprise_kb",
                title="Enterprise Knowledge Base",
                url="",
                author="system",
                created_date=datetime.now(),
                chunk_count=len(kb_chunks)
            )
            db.add(kb_metadata)
            db.commit()
    else:
        logger.warning(f"Knowledge base file not found at {kb_path}")
        logger.info("No knowledge base to index. You can add documents via the upload interface.")
    
    logger.info("=== Data Initialization Complete ===")
    if kb_chunks:
        logger.info(f"Total documents indexed: {len(kb_chunks)} knowledge base chunks")
    else:
        logger.info("No documents indexed. Database initialized successfully.")
    
    stats = pinecone_client.get_stats()
    logger.info(f"Pinecone stats: {stats}")


if __name__ == "__main__":
    main()
