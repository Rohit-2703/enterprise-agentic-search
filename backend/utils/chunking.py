"""Document chunking utilities with multiple strategies."""
from typing import List, Dict, Any
import re
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


class DocumentChunker:
    """Chunk documents using various strategies."""
    
    @staticmethod
    def chunk_by_tokens(
        text: str,
        max_tokens: int = 512,
        overlap_tokens: int = 50
    ) -> List[str]:
        """Chunk text by token count with overlap."""
        words = text.split()
        max_words = int(max_tokens * 0.75)
        overlap_words = int(overlap_tokens * 0.75)
        
        chunks = []
        i = 0
        
        while i < len(words):
            chunk_words = words[i:i + max_words]
            chunks.append(' '.join(chunk_words))
            i += max_words - overlap_words
        
        return chunks
    
    @staticmethod
    def chunk_by_paragraphs(
        text: str,
        max_paragraphs: int = 3,
        min_chunk_size: int = 100
    ) -> List[str]:
        """Chunk text by paragraphs."""
        paragraphs = re.split(r'\n\s*\n', text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
        
        chunks = []
        current_chunk = []
        
        for para in paragraphs:
            current_chunk.append(para)
            
            if len(current_chunk) >= max_paragraphs:
                chunk_text = '\n\n'.join(current_chunk)
                if len(chunk_text) >= min_chunk_size:
                    chunks.append(chunk_text)
                    current_chunk = []
        
        if current_chunk:
            chunk_text = '\n\n'.join(current_chunk)
            if len(chunk_text) >= min_chunk_size:
                chunks.append(chunk_text)
        
        return chunks
    
    @staticmethod
    def chunk_by_sections(
        text: str,
        section_markers: List[str] = None
    ) -> List[Dict[str, str]]:
        """Chunk text by sections (headings)."""
        if section_markers is None:
            section_markers = ['###', '##', '#']
        
        chunks = []
        current_section = ""
        current_title = "Introduction"
        
        lines = text.split('\n')
        
        for line in lines:
            is_heading = False
            for marker in section_markers:
                if line.strip().startswith(marker):
                    if current_section.strip():
                        chunks.append({
                            "title": current_title,
                            "content": current_section.strip()
                        })
                    
                    current_title = line.strip().lstrip('#').strip()
                    current_section = ""
                    is_heading = True
                    break
            
            if not is_heading:
                current_section += line + '\n'
        
        if current_section.strip():
            chunks.append({
                "title": current_title,
                "content": current_section.strip()
            })
        
        return chunks
    
    @staticmethod
    def chunk_by_semantic(
        text: str,
        max_chunk_size: int = 1000,
        overlap: int = 100
    ) -> List[str]:
        """Chunk text semantically (by sentences with overlap)."""
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        chunks = []
        current_chunk = []
        current_size = 0
        
        for sentence in sentences:
            sentence_size = len(sentence)
            
            if current_size + sentence_size > max_chunk_size and current_chunk:
                chunks.append(' '.join(current_chunk))
                
                overlap_sentences = []
                overlap_size = 0
                for s in reversed(current_chunk):
                    if overlap_size + len(s) <= overlap:
                        overlap_sentences.insert(0, s)
                        overlap_size += len(s)
                    else:
                        break
                
                current_chunk = overlap_sentences
                current_size = overlap_size
            
            current_chunk.append(sentence)
            current_size += sentence_size
        
        if current_chunk:
            chunks.append(' '.join(current_chunk))
        
        return chunks
    
    @staticmethod
    def smart_chunk(
        text: str,
        strategy: str = "auto",
        max_chunk_size: int = 1000
    ) -> List[Dict[str, Any]]:
        """Smart chunking with automatic strategy selection."""
        if strategy == "auto":
            if "##" in text or "###" in text:
                strategy = "sections"
            elif text.count('\n\n') > 5:
                strategy = "paragraphs"
            else:
                strategy = "semantic"
        
        logger.info(f"Using chunking strategy: {strategy}")
        
        chunks_data = []
        
        if strategy == "sections":
            chunks = DocumentChunker.chunk_by_sections(text)
            for i, chunk in enumerate(chunks):
                chunks_data.append({
                    "chunk_id": i,
                    "text": chunk["content"],
                    "title": chunk["title"],
                    "strategy": "sections"
                })
        
        elif strategy == "paragraphs":
            chunks = DocumentChunker.chunk_by_paragraphs(text)
            for i, chunk in enumerate(chunks):
                chunks_data.append({
                    "chunk_id": i,
                    "text": chunk,
                    "title": f"Chunk {i+1}",
                    "strategy": "paragraphs"
                })
        
        elif strategy == "tokens":
            chunks = DocumentChunker.chunk_by_tokens(text, max_tokens=max_chunk_size // 4)
            for i, chunk in enumerate(chunks):
                chunks_data.append({
                    "chunk_id": i,
                    "text": chunk,
                    "title": f"Chunk {i+1}",
                    "strategy": "tokens"
                })
        
        else:  # semantic
            chunks = DocumentChunker.chunk_by_semantic(text, max_chunk_size=max_chunk_size)
            for i, chunk in enumerate(chunks):
                chunks_data.append({
                    "chunk_id": i,
                    "text": chunk,
                    "title": f"Chunk {i+1}",
                    "strategy": "semantic"
                })
        
        logger.info(f"Created {len(chunks_data)} chunks using {strategy} strategy")
        return chunks_data
