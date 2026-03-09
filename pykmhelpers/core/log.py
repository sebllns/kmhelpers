import logging


class Log:
    @staticmethod
    def is_verbose(logger: logging.Logger) -> bool:
        return logger.isEnabledFor(logging.DEBUG)

    @staticmethod
    def _handle_exception(
        logger: logging.Logger, msg: str, e: Exception, verbose: bool
    ):
        if verbose:
            logger.exception(f"{e} ({type(e).__name__}) | {msg}")
        else:
            logger.error(f"{e} ({type(e).__name__}) | {msg}")

    @staticmethod
    def handle_exception(logger: logging.Logger, e: Exception, msg: str):
        Log._handle_exception(logger, msg, e, Log.is_verbose(logger))
