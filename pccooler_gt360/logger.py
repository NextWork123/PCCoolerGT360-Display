"""Structured logging with rotation for PCCooler GT360.

Replaces ad-hoc print statements with proper logging.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional


# Emoji prefixes for log levels
_EMOJI = {
    "DEBUG": "🔍",
    "INFO": "ℹ️",
    "WARNING": "⚠️",
    "ERROR": "❌",
    "CRITICAL": "🚨",
    "SUCCESS": "✅",
}


class EmojiFormatter(logging.Formatter):
    """Custom formatter that adds emoji prefixes."""
    
    def format(self, record: logging.LogRecord) -> str:
        emoji = _EMOJI.get(record.levelname, "ℹ️")
        record.emoji = emoji
        return super().format(record)


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 3,
    use_console: bool = True,
) -> logging.Logger:
    """Setup structured logging with optional rotation.
    
    Args:
        level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path for log file
        max_bytes: Maximum log file size before rotation
        backup_count: Number of backup files to keep
        use_console: Whether to output to console
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("pccooler_gt360")
    logger.setLevel(getattr(logging, level.upper()))
    
    # Clear existing handlers
    logger.handlers = []
    
    # Console handler
    if use_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_format = EmojiFormatter(
            "%(emoji)s %(message)s"
        )
        console_handler.setFormatter(console_format)
        logger.addHandler(console_handler)
    
    # File handler with rotation
    if log_file:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)
    
    return logger


def get_logger() -> logging.Logger:
    """Get the module logger.
    
    Returns the default logger if setup_logging hasn't been called.
    """
    return logging.getLogger("pccooler_gt360")


def log(level: str, message: str, *args, **kwargs) -> None:
    """Convenience function for logging.
    
    Args:
        level: Log level (debug, info, warning, error, critical, success)
        message: Log message
        *args: Format arguments
        **kwargs: Additional logging kwargs
    """
    logger = get_logger()
    
    # Map success to info level
    if level.upper() == "SUCCESS":
        level = "INFO"
    
    log_func = getattr(logger, level.lower(), logger.info)
    log_func(message, *args, **kwargs)


# Convenience functions
def debug(message: str, *args, **kwargs) -> None:
    """Log debug message."""
    log("DEBUG", message, *args, **kwargs)


def info(message: str, *args, **kwargs) -> None:
    """Log info message."""
    log("INFO", message, *args, **kwargs)


def warning(message: str, *args, **kwargs) -> None:
    """Log warning message."""
    log("WARNING", message, *args, **kwargs)


def error(message: str, *args, **kwargs) -> None:
    """Log error message."""
    log("ERROR", message, *args, **kwargs)


def critical(message: str, *args, **kwargs) -> None:
    """Log critical message."""
    log("CRITICAL", message, *args, **kwargs)


def success(message: str, *args, **kwargs) -> None:
    """Log success message."""
    logger = get_logger()
    # Use INFO level but with success emoji via custom adapter
    logger.info(f"✅ {message}", *args, **kwargs)
