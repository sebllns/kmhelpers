import logging


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
        logger: logging.Logger, msg: str, e: Exception, verbose: bool
    ):
        if verbose:
            logger.exception(f"{Log.format_exception(e)} | {msg}")
        else:
            logger.error(f"{Log.format_exception(e)} | {msg}")

    @staticmethod
    def handle_exception(logger: logging.Logger, e: Exception, msg: str):
        Log._handle_exception(logger, msg, e, Log.is_verbose(logger))
