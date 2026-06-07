import logging
import os
from logging.handlers import RotatingFileHandler
from app.config import settings

LOG_FILE = os.path.join(settings.data_dir, "morphsheet.log")
os.makedirs(settings.data_dir, exist_ok=True)

logger = logging.getLogger("morphsheet")
logger.setLevel(logging.DEBUG)

fmt = logging.Formatter(
    "%(asctime)s | %(levelname)-7s | %(name)-15s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# File handler (rotating: max 5MB × 3 files)
fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
fh.setLevel(logging.DEBUG)
fh.setFormatter(fmt)
logger.addHandler(fh)

# Console handler
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(fmt)
logger.addHandler(ch)


def get_logger(name: str) -> logging.Logger:
    return logger.getChild(name)
