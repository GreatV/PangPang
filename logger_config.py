"""
Centralized Logging Configuration Module
Provides unified logging configuration for the entire project
"""

from loguru import logger
import sys

# Remove default handlers
logger.remove()

# Add file log handler - all logs are written to a single file
logger.add(
    "pangpang.log",
    rotation="10 MB",  # Automatically rotate when log file reaches 10MB
    compression="zip",  # Compress old log files
    retention="30 days",  # Keep logs for 30 days
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} - {name}:{function}:{line} - {level} - {message}",
    encoding="utf-8",
)

# Add console log handler
logger.add(
    sys.stdout,
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} - {name}:{function}:{line} - {level} - {message}",
)

# Other optional configurations
# If you need to record logs separately by module, uncomment the following code
# logger.add("paper_pipeline.log", filter=lambda record: record["name"] == "paper_pipeline", rotation="10 MB", level="INFO")
# logger.add("ranking.log", filter=lambda record: record["name"] == "ranking", rotation="10 MB", level="INFO")
# logger.add("papers_with_code.log", filter=lambda record: record["name"] == "papers_with_code", rotation="10 MB", level="INFO")
# logger.add("summarize_paper.log", filter=lambda record: record["name"] == "summarize_paper", rotation="10 MB", level="INFO")


def get_logger(name):
    """
    Get a logger with a specific name
    This allows log messages to include the module name

    :param name: Usually the module name, like __name__
    :return: A configured logger
    """
    # In loguru, this is just to track which module emitted the log
    # The returned instance is still the same logger
    return logger.bind(name=name)
