"""
MemoryHub Logging Configuration
"""

import logging
import sys
from pathlib import Path


def setup_logging(level=logging.INFO, log_file=None):
    """
    Configure logging for MemoryHub.

    Args:
        level: Logging level (default: INFO)
        log_file: Optional file path for log output (default: stderr only)
    """
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Get root logger for memory_hub
    logger = logging.getLogger("memory_hub")
    logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Console handler (stderr)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name):
    """
    Get a logger for a specific module.

    Args:
        name: Module name (e.g., "daemon", "backends")

    Returns:
        Logger instance
    """
    return logging.getLogger(f"memory_hub.{name}")


# Initialize default logging when module is imported
setup_logging()
