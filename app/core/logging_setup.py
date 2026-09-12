import logging
import sys

def setup_logging(debug: bool = False):
    """Initialize application logging configuration."""
    level = logging.DEBUG if debug else logging.INFO
    
    # Define log format
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Configure root logger
    logging.basicConfig(
        level=level,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Log startup message
    logger = logging.getLogger("nova")
    logger.info("Logging initialized (Level: %s)", "DEBUG" if debug else "INFO")
