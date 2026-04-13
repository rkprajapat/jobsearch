import json
import sys
from urllib.parse import urlparse

from configs import DOMS_FILE_PATH

doms_path = DOMS_FILE_PATH


def load_source_doms() -> dict[str, dict]:
    try:
        with open(doms_path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"DOMs file not found at {doms_path}. Exiting.")
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"DOMs file is invalid JSON: {exc}. Exiting.")
        sys.exit(1)


def domain_key(url: str) -> str:
    host = urlparse(url).hostname or ""
    return host.removeprefix("www.")
