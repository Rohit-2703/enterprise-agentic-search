"""Logging configuration for the application."""
import logging
import sys
from backend.utils.config import settings


def setup_logger(name: str) -> logging.Logger:
    """
    Setup logger with consistent formatting.
    
    Args:
        name: Logger name (typically __name__)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Set level from config
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logger.setLevel(log_level)
    
    # Avoid duplicate handlers
    if not logger.handlers:
        # Console handler
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(log_level)
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        
        logger.addHandler(handler)
    
    return logger
