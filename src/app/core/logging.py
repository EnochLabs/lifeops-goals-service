import sys

from loguru import logger

from app.config.settings import settings

_DEFAULT_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{line} - {message}"


def setup_logging() -> None:
    logger.remove()
    if settings.JSON_LOGS:
        logger.add(sys.stdout, level=settings.LOG_LEVEL, serialize=True)
    else:
        logger.add(sys.stdout, level=settings.LOG_LEVEL, format=_DEFAULT_FORMAT, colorize=True)
