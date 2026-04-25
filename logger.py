import logging
import json
import os
import subprocess
from datetime import datetime
from typing import Optional


class CommitFilter(logging.Filter):
    def __init__(self, commit: str):
        super().__init__()
        self.commit = commit

    def filter(self, record):
        record.commit = self.commit
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "commit": getattr(record, "commit", "unknown"),
        }

        if hasattr(record, "url"):
            log_data["url"] = record.url
        if hasattr(record, "html"):
            log_data["html"] = record.html
        if record.exc_info:
            log_data["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def get_commit_hash() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5
        ).stdout.strip() or "unknown"
    except Exception:
        return os.getenv("SCRAPER_COMMIT", "unknown")


def setup_logging(log_dir: str = "logs", debug: bool = False) -> logging.Logger:
    os.makedirs(log_dir, exist_ok=True)
    commit = get_commit_hash()

    logger = logging.getLogger("scraper")
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.handlers.clear()

    commit_filter = CommitFilter(commit)

    info_handler = logging.FileHandler(f"{log_dir}/scraper_info.log")
    info_handler.setLevel(logging.INFO)
    info_handler.addFilter(commit_filter)
    info_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    info_handler.setFormatter(info_formatter)
    logger.addHandler(info_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(info_formatter)
    logger.addHandler(console_handler)

    debug_handler = logging.FileHandler(f"{log_dir}/scraper_debug.log")
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.addFilter(commit_filter)
    debug_handler.setFormatter(JsonFormatter())
    logger.addHandler(debug_handler)

    return logger


logger = setup_logging(debug=os.getenv("DEBUG", "false").lower() == "true")