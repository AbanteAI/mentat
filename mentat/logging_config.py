import datetime
import logging
import logging.handlers
import os

from .config_manager import mentat_dir_path


def setup_logging():
    logs_dir = "logs"
    if "PYTEST_CURRENT_TEST" in os.environ:
        logs_dir += "/test_logs"
    logs_path = mentat_dir_path / logs_dir

    logging.getLogger("openai").setLevel(logging.WARNING)
    # Breaking out of async generator when model messes up causes an error
    logging.getLogger("asyncio").setLevel(logging.CRITICAL)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    # Only log warnings and higher to console
    console_handler.setLevel(logging.WARNING)

    logs_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_path / f"mentat_{timestamp}.log"
    latest_log_file = logs_path / "latest.log"
    latest_log_file.unlink(missing_ok=True)

    file_handler = logging.FileHandler(log_file)
    file_handler_latest = logging.FileHandler(latest_log_file)
    file_handler.setFormatter(formatter)
    file_handler_latest.setFormatter(formatter)

    costs_logger = logging.getLogger("costs")
    costs_formatter = logging.Formatter("%(asctime)s\n%(message)s")
    costs_handler = logging.FileHandler(logs_path / "costs.log")
    costs_handler.setFormatter(costs_formatter)
    costs_logger.addHandler(costs_handler)
    costs_logger.setLevel(logging.INFO)
    costs_logger.propagate = False

    handlers = [console_handler, file_handler, file_handler_latest]
    logging.basicConfig(
        level=logging.DEBUG,
        handlers=handlers,
    )
