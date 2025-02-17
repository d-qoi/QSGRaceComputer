import logging

from qsgrc.config import config

logging.basicConfig(
    format="%(asctime)s -- %(name)s -- %(levelname)s: %(message)s",
    level=logging._nameToLevel.get(config.log_level.upper(), logging.WARNING),
)


def get_logger(name, handler:logging.Handler|None = None) -> logging.Logger:
    logger = logging.getLogger(name)

    if handler:
        logger.addHandler(handler)

    logger.setLevel(config.log_level.upper())

    return logger
