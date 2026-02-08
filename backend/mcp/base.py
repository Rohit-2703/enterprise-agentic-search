"""Base MCP client class for real-time data retrieval from various sources."""
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


class MCPClient(ABC):
    """Base class for MCP (Model Context Protocol) clients providing real-time data access."""
    
    @abstractmethod
    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search for documents/files in the data source."""
        pass
    
    @abstractmethod
    def get_source_type(self) -> str:
        """Return the source type identifier."""
        pass
    
    def format_result(self, content: str, title: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Format MCP result in standard format with content, title, and metadata."""
        from datetime import datetime
        
        return {
            "id": metadata.get("id", f"{self.get_source_type()}_{hash(content)}"),
            "source_type": self.get_source_type(),
            "title": title,
            "content": content,
            "metadata": {
                "source_type": self.get_source_type(),
                "title": title,
                "text": content[:1000],  # Truncate for metadata
                "timestamp": metadata.get("timestamp", datetime.now().isoformat()),
                "author": metadata.get("author", "unknown"),
                "url": metadata.get("url", ""),
                "path": metadata.get("path", ""),
                "is_real_time": True  # Flag to indicate MCP data
            }
        }
