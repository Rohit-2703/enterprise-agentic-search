"""Pinecone vector store client."""
import re
from typing import List, Dict, Any, Optional
from pinecone import Pinecone, ServerlessSpec
from backend.utils.config import settings
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


class PineconeClient:
    """Pinecone vector database client."""
    
    def __init__(self):
        """Initialize Pinecone client."""
        self.pc = Pinecone(api_key=settings.pinecone_api_key)
        self.index_name = settings.pinecone_index_name
        self.dimension = settings.pinecone_dimension
        self.index = None
        self._connect_to_index()
    
    def _connect_to_index(self):
        """Connect to existing Pinecone index or create if doesn't exist."""
        try:
            # Check if index exists
            existing_indexes = self.pc.list_indexes()
            index_names = [idx.name for idx in existing_indexes]
            
            if self.index_name not in index_names:
                logger.warning(f"Index '{self.index_name}' not found. Creating...")
                self.create_index()
            
            self.index = self.pc.Index(self.index_name)
            logger.info(f"Connected to Pinecone index: {self.index_name}")
        except Exception as e:
            logger.error(f"Error connecting to Pinecone index: {e}")
            raise
    
    def create_index(self):
        """Create Pinecone index."""
        try:
            self.pc.create_index(
                name=self.index_name,
                dimension=self.dimension,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region=settings.pinecone_environment.split("-")[0] + "-" + 
                           settings.pinecone_environment.split("-")[1] + "-" + 
                           settings.pinecone_environment.split("-")[2]
                )
            )
            logger.info(f"Created Pinecone index: {self.index_name}")
        except Exception as e:
            logger.error(f"Error creating Pinecone index: {e}")
            raise
    
    def upsert_documents(
        self,
        vectors: List[tuple],
        namespace: str = ""
    ) -> Dict[str, Any]:
        """Upsert document vectors to Pinecone."""
        try:
            response = self.index.upsert(
                vectors=vectors,
                namespace=namespace
            )
            logger.info(f"Upserted {len(vectors)} vectors to Pinecone")
            return response
        except Exception as e:
            logger.error(f"Error upserting to Pinecone: {e}")
            raise
    
    def query(
        self,
        vector: List[float],
        top_k: int = 10,
        filter: Optional[Dict[str, Any]] = None,
        namespace: str = "",
        include_metadata: bool = True
    ) -> Dict[str, Any]:
        """Query Pinecone for similar vectors."""
        try:
            results = self.index.query(
                vector=vector,
                top_k=top_k,
                filter=filter,
                namespace=namespace,
                include_metadata=include_metadata
            )
            logger.info(f"Retrieved {len(results.matches)} results from Pinecone")
            return results
        except Exception as e:
            logger.error(f"Error querying Pinecone: {e}")
            raise
    
    def delete(
        self,
        ids: List[str],
        namespace: str = ""
    ) -> Dict[str, Any]:
        """Delete vectors from Pinecone."""
        try:
            response = self.index.delete(
                ids=ids,
                namespace=namespace
            )
            logger.info(f"Deleted {len(ids)} vectors from Pinecone")
            return response
        except Exception as e:
            logger.error(f"Error deleting from Pinecone: {e}")
            raise
    
    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        try:
            stats = self.index.describe_index_stats()
            return {
                "total_vector_count": stats.total_vector_count,
                "dimension": stats.dimension,
                "index_fullness": stats.index_fullness
            }
        except Exception as e:
            logger.error(f"Error getting Pinecone stats: {e}")
            return {}
    
    def health_check(self) -> bool:
        """Check if Pinecone is healthy."""
        try:
            self.index.describe_index_stats()
            return True
        except Exception as e:
            logger.error(f"Pinecone health check failed: {e}")
            return False
    
    def list_all_documents(self, top_k: int = 10000) -> Dict[str, Any]:
        """List all unique documents from Pinecone by querying all vectors and grouping by document."""
        try:
            from backend.utils.config import settings
            
            dummy_vector = [0.0] * settings.pinecone_dimension
            
            results = self.index.query(
                vector=dummy_vector,
                top_k=top_k,
                include_metadata=True
            )
            
            documents = {}
            
            for match in results.matches:
                vector_id = match.id
                metadata = match.metadata or {}
                
                if "_chunk_" in vector_id:
                    doc_id = re.sub(r'_chunk_\d+$', '', vector_id)
                else:
                    doc_id = vector_id
                
                title = metadata.get("title", "Untitled")
                if " - " in title:
                    title = title.split(" - ")[0]
                
                if doc_id not in documents:
                    documents[doc_id] = {
                        "document_id": doc_id,
                        "title": title,
                        "source_type": metadata.get("source_type", "unknown"),
                        "author": metadata.get("author", "unknown"),
                        "chunk_count": 0,
                        "indexed_at": metadata.get("timestamp", ""),
                        "url": metadata.get("url", "")
                    }
                
                documents[doc_id]["chunk_count"] += 1
                
                if metadata.get("timestamp"):
                    if not documents[doc_id]["indexed_at"] or metadata["timestamp"] > documents[doc_id]["indexed_at"]:
                        documents[doc_id]["indexed_at"] = metadata["timestamp"]
                        if not documents[doc_id]["title"] or documents[doc_id]["title"] == "Untitled":
                            documents[doc_id]["title"] = title
                        documents[doc_id]["author"] = metadata.get("author", documents[doc_id]["author"])
            
            logger.info(f"Found {len(documents)} unique documents from Pinecone")
            return documents
            
        except Exception as e:
            logger.error(f"Error listing documents from Pinecone: {e}")
            return {}


pinecone_client = PineconeClient()
