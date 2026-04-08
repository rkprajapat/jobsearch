import json
from pathlib import Path
import sys
from typing import Sequence
from dotenv import load_dotenv
import os

# Load variables from the .env file
load_dotenv()

cwd = Path(__file__).parent.absolute()

__data__ = {}
try:
    with open(cwd.joinpath("inputs.json"), "r") as f:
        __data__ = json.load(f)
except FileNotFoundError:
    print("inputs.json not found. Please make sure it exists in the project_data directory.")
    sys.exit(1)

except json.JSONDecodeError:
    print("Error decoding inputs.json. Please ensure it is a valid JSON file.")
    sys.exit(1)

SKILLS : Sequence[str] = __data__.get("skills", [])
SCOPE: Sequence[str] = __data__.get("scope", [])
PREFERRED_LOCATIONS : Sequence[str] = __data__.get("preferred_locations", [])
SOURCES : Sequence[str] = __data__.get("sources", [])
JOBS_PER_SOURCE : int = __data__.get("jobs_per_source", 10)
MAX_PAGES: int = __data__.get("max_pages", 5)
HEADLESS: bool = __data__.get("headless", True)
LOGIN_WAIT_SECONDS: int = __data__.get("login_wait_seconds", 15)

CLUSTERING_CONFIG: dict = __data__.get("clustering", {})
CLUSTERING_VERSIONED_OUTPUT: bool = CLUSTERING_CONFIG.get("write_versioned_output", True)
_CLUSTERING_MIN_CLUSTER_SIZE_RAW = CLUSTERING_CONFIG.get("min_cluster_size")
CLUSTERING_MIN_CLUSTER_SIZE: int | None = (
    int(_CLUSTERING_MIN_CLUSTER_SIZE_RAW)
    if _CLUSTERING_MIN_CLUSTER_SIZE_RAW is not None
    else None
)
CLUSTERING_EXPLICIT_STOPWORDS: Sequence[str] = __data__.get("stopwords", [])

# credentials
LINKEDIN_CREDENTIALS: dict = {
    "email": os.getenv("LINKEDIN_EMAIL"),
    "password": os.getenv("LINKEDIN_PASSWORD")
}
if not LINKEDIN_CREDENTIALS["email"] or not LINKEDIN_CREDENTIALS["password"]:
    print("LinkedIn credentials not found. Please set them as environment variables.")
    print("Expected variables: LINKEDIN_EMAIL and LINKEDIN_PASSWORD")
    sys.exit(1)

# DIRECTORY PATH TO READ/WRITE DATA FILES
PROJECT_DATA_DIR: Path = Path(os.getenv("DATA_DIR_PATH")).resolve()
if not PROJECT_DATA_DIR:
    print(f"Data directory not found at {PROJECT_DATA_DIR}. Set it as an environment variable DATA_DIR_PATH.")
    sys.exit(1)

if not PROJECT_DATA_DIR.exists():
    PROJECT_DATA_DIR.mkdir(parents=True, exist_ok=True)

# LinkedIn DOM XPaths and Selectors file
DOMS_FILE_PATH = cwd.joinpath("li_doms.json")

if __name__ == "__main__":
    print(__data__)