import logging
import traceback


class Log:

    log_file: str | None = None

    @staticmethod
    def is_verbose(logger: logging.Logger) -> bool:
        return logger.isEnabledFor(logging.DEBUG)

    @staticmethod
    def format_exception(e: Exception) -> str:
        return f"{e} ({type(e).__name__})"

    @staticmethod
    def _handle_exception(
        logger: logging.Logger, msg: str, e: Exception, verbose: bool, level: int
    ):
        if verbose and level == logging.ERROR:
            logger.exception(f"{Log.format_exception(e)} | {msg}")
        else:
            logger.log(level, f"{Log.format_exception(e)} | {msg}")

    @staticmethod
    def handle_exception(
        logger: logging.Logger, e: Exception, msg: str, level: int = logging.ERROR
    ):
        Log._handle_exception(logger, msg, e, Log.is_verbose(logger), level)

    @staticmethod
    def print_trace(e: Exception):
        traceback.print_exception(type(e), e, e.__traceback__)

    @staticmethod
    def step(logger: logging.Logger, title: str, width: int = 60):
        """Log a visually separated step header."""
        logger.info("\n\n")
        logger.info("=" * width)
        logger.info(title)
        logger.info("=" * width)
