import json
import sys
from pathlib import Path
from urllib.parse import urlparse

_PROJECT_DATA = Path(__file__).parent.parent / "project_data"


def load_source_doms() -> dict[str, dict]:
    doms_path = _PROJECT_DATA / "source_doms.json"
    try:
        with open(doms_path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"source_doms.json not found at {doms_path}. Exiting.")
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"source_doms.json is invalid JSON: {exc}. Exiting.")
        sys.exit(1)


def domain_key(url: str) -> str:
    host = urlparse(url).hostname or ""
    return host.removeprefix("www.")
