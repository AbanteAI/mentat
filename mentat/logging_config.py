import datetime
import logging
import logging.handlers
import os

from .config_manager import mentat_dir_path


def setup_logging():
    logs_dir = "logs"
    if "PYTEST_CURRENT_TEST" in os.environ:
        logs_dir += "/test_logs"
    logs_path = os.path.join(mentat_dir_path, logs_dir)

    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    # Only log warnings and higher to console
    console_handler.setLevel(logging.WARNING)

    os.makedirs(logs_path, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(logs_path, f"mentat_{timestamp}.log")
    latest_log_file = os.path.join(logs_path, "latest.log")
    if os.path.exists(latest_log_file):
        os.remove(latest_log_file)

    file_handler = logging.FileHandler(log_file)
    file_handler_latest = logging.FileHandler(latest_log_file)
    file_handler.setFormatter(formatter)
    file_handler_latest.setFormatter(formatter)

    costs_logger = logging.getLogger("costs")
    costs_formatter = logging.Formatter("%(asctime)s\n%(message)s")
    costs_handler = logging.FileHandler(os.path.join(logs_path, "costs.log"))
    costs_handler.setFormatter(costs_formatter)
    costs_logger.addHandler(costs_handler)
    costs_logger.setLevel(logging.INFO)
    costs_logger.propagate = False

    handlers = [console_handler, file_handler, file_handler_latest]
    logging.basicConfig(
        level=logging.DEBUG,
        handlers=handlers,
    )
