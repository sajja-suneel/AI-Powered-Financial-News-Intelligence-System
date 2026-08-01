# src/utils/logger.py
import logging
import os
import sys

def get_logger(name: str) -> logging.Logger:
    """
    Configures and returns a namespaced logger instance.
    Logs to stdout and optionally to a log file in logs/app.log.
    """
    logger = logging.getLogger(name)
    
    # Avoid adding duplicate handlers if logger is already initialized
    if logger.hasHandlers():
        return logger

    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    logger.setLevel(log_level)

    # Formatter definition: [YYYY-MM-DD HH:MM:SS] [LEVEL] [LOGGER_NAME]: Message
    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console Handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File Handler (logs/app.log)
    log_dir = os.getenv("LOG_DIR", "logs")
    try:
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.FileHandler(os.path.join(log_dir, "app.log"), encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception:
        # Gracefully handle file permission issues if any
        pass

    return logger
