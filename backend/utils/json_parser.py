"""Safely parse JSON from LLM responses, handling markdown code blocks and edge cases."""
import json
import re
from typing import Any, Optional
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


def extract_json_from_response(content: Optional[str]) -> Optional[dict]:
    """Safely extract and parse JSON from LLM response, handling markdown code blocks, empty content, and invalid JSON."""
    if not content:
        logger.warning("None content received from LLM")
        return None
    
    if not content.strip():
        logger.warning("Empty content received from LLM")
        return None
    
    original_content = content
    content = content.strip()
    
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
    if json_match:
        content = json_match.group(1).strip()
        logger.debug("Extracted JSON from markdown code block")
    
    if not content.startswith('{'):
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            content = json_match.group(0).strip()
            logger.debug("Extracted JSON object from content")
    
    try:
        parsed = json.loads(content)
        logger.debug("Successfully parsed JSON from response")
        return parsed
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON from content: {e}")
        logger.error(f"Original content (first 500 chars): {original_content[:500]}")
        logger.error(f"Attempted to parse (first 500 chars): {content[:500]}")
        return None
