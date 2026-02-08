"""Initialize database and load enterprise knowledge base."""
import sys
import os
from datetime import datetime
from sqlalchemy.exc import IntegrityError

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)
sys.path.append(os.path.dirname(os.path.abspath(__file__)))  # Add scripts directory to path

from backend.retrieval import pinecone_client, embedding_generator
from backend.database import init_db, get_db_session, DocumentMetadata
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


def main():
    """Initialize database and load enterprise knowledge base."""
    logger.info("=== Starting Data Initialization ===")
    
    logger.info("Initializing database...")
    try:
        init_db()
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    
    # Seed PostgreSQL with test data (employees, sales, etc.)
    logger.info("Seeding PostgreSQL with test data...")
    try:
        from seed_postgresql import main as seed_postgresql
        seed_postgresql()
        logger.info("PostgreSQL seeding completed successfully")
    except Exception as e:
        logger.error(f"Failed to seed PostgreSQL: {e}")
        raise
    
    logger.info("Loading enterprise knowledge base...")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    kb_path = os.path.join(project_root, "data", "enterprise_knowledge_base.txt")
    
    logger.info(f"Looking for knowledge base at: {kb_path}")
    logger.info(f"Current working directory: {os.getcwd()}")
    
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
        
        db = get_db_session()
        try:
            # Try to get existing record first
            existing_metadata = db.query(DocumentMetadata).filter(
                DocumentMetadata.document_id == "enterprise_kb"
            ).first()
            
            if existing_metadata:
                # Update existing record
                existing_metadata.chunk_count = len(kb_chunks)
                existing_metadata.updated_date = datetime.now()
                db.commit()
                logger.info("Successfully updated knowledge base metadata in database")
            else:
                # Create new record
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
                logger.info("Successfully saved knowledge base metadata to database")
        except IntegrityError as e:
            db.rollback()
            # Record already exists, update it
            logger.info("Record already exists, updating...")
            try:
                existing = db.query(DocumentMetadata).filter(
                    DocumentMetadata.document_id == "enterprise_kb"
                ).first()
                if existing:
                    existing.chunk_count = len(kb_chunks)
                    existing.updated_date = datetime.now()
                    db.commit()
                    logger.info("Successfully updated existing knowledge base metadata")
                else:
                    logger.warning("Could not find existing record, but unique constraint was violated")
            except Exception as update_error:
                logger.error(f"Error updating existing record: {update_error}")
                db.rollback()
                raise
        except Exception as e:
            logger.error(f"Error saving to database: {e}")
            db.rollback()
            raise
        finally:
            db.close()
    else:
        logger.warning(f"Knowledge base file not found at {kb_path}")
        logger.info("No knowledge base to index. You can add documents via the upload interface.")
    
    logger.info("=== Data Initialization Complete ===")
    if kb_chunks:
        logger.info(f"Total documents indexed: {len(kb_chunks)} knowledge base chunks")
    else:
        logger.info("No documents indexed. Database initialized successfully.")
    
    try:
        stats = pinecone_client.get_stats()
        logger.info(f"Pinecone stats: {stats}")
    except Exception as e:
        logger.warning(f"Could not get Pinecone stats: {e}")
    
    db = get_db_session()
    try:
        from sqlalchemy import inspect
        inspector = inspect(db.bind)
        tables = inspector.get_table_names()
        logger.info(f"Database tables created: {', '.join(tables)}")
        
        doc_count = db.query(DocumentMetadata).count()
        logger.info(f"DocumentMetadata records in database: {doc_count}")
    except Exception as e:
        logger.warning(f"Could not verify database state: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
