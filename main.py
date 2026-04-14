from configs import PROJECT_DATA_DIR
from ui.main import start_web_ui
from utils import configure_logging, get_logger, set_correlation_id

configure_logging(log_dir=PROJECT_DATA_DIR / "logs")
logger = get_logger(__name__)


def main():
    set_correlation_id()
    start_web_ui()


if __name__ in {"__main__", "__mp_main__"}:
    main()
