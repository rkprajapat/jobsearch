import asyncio
from datetime import datetime, timedelta, timezone
import json
import sys
from pathlib import Path
from configs import (
    CLUSTERING_EXPLICIT_STOPWORDS,
    CLUSTERING_MIN_CLUSTER_SIZE,
    CLUSTERING_VERSIONED_OUTPUT,
)
from services.observer import Observer
from services.jd_clustering import JDClusteringService
from services.jd_extractor import run_jd_extractor
from services.opportunities_report import ClusterPDFReportService

_PROJECT_DATA = Path(__file__).parent / "project_data"
_CLUSTERS_FILE = _PROJECT_DATA / "clusters.json"
_CLUSTER_REPORT_FILE = _PROJECT_DATA / "clusters_report.pdf"
_FRESHNESS_WINDOW_DAYS = 30


def _is_recently_generated(generated_at: datetime) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(days=_FRESHNESS_WINDOW_DAYS)
    return generated_at >= cutoff


def _read_clusters_generated_at(clusters_file: Path) -> datetime | None:
    if not clusters_file.exists():
        return None

    try:
        with open(clusters_file, "r", encoding="utf-8") as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError):
        return None

    generated_at_raw = payload.get("generated_at") if isinstance(payload, dict) else None
    if not isinstance(generated_at_raw, str):
        return None

    try:
        parsed = datetime.fromisoformat(generated_at_raw)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def _is_recently_updated_file(file_path: Path) -> bool:
    if not file_path.exists():
        return False

    modified_at = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
    return _is_recently_generated(modified_at)


def _run_clustering() -> str | None:
    service = JDClusteringService(
        write_versioned_output=CLUSTERING_VERSIONED_OUTPUT,
        explicit_stopwords=CLUSTERING_EXPLICIT_STOPWORDS,
        min_cluster_size=CLUSTERING_MIN_CLUSTER_SIZE,
    )
    saved_files = service.run_and_save()
    print(f"Cluster output written to: {saved_files['latest']}")
    if "versioned" in saved_files:
        print(f"Versioned cluster output written to: {saved_files['versioned']}")
    return saved_files["latest"]


def _run_cluster_report(clusters_file: Path | None = None) -> None:
    report_service = ClusterPDFReportService()
    try:
        report_path = report_service.generate_pdf_report(clusters_file=clusters_file)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"Unable to generate cluster PDF report: {exc}")
        return

    print(f"Cluster PDF report written to: {report_path}")


def _run_post_extraction_tasks(force: bool = False) -> None:
    latest_clusters_file: str | None = None

    last_cluster_generated_at = _read_clusters_generated_at(_CLUSTERS_FILE)
    should_skip_clustering = (
        not force
        and last_cluster_generated_at is not None
        and _is_recently_generated(last_cluster_generated_at)
    )
    if should_skip_clustering:
        print("Skipping JD clustering (last run is within 30 days).")
    else:
        latest_clusters_file = _run_clustering()

    should_skip_report = not force and _is_recently_updated_file(_CLUSTER_REPORT_FILE)
    if should_skip_report:
        print("Skipping cluster report generation (last report is within 30 days).")
        return

    clusters_file = Path(latest_clusters_file) if latest_clusters_file else None
    _run_cluster_report(clusters_file=clusters_file)


async def run_pipeline(only_jd: bool = False, cluster: bool = False) -> None:
    if not only_jd:
        observer = Observer()
        await observer.observe()
    await run_jd_extractor()
    _run_post_extraction_tasks(force=cluster)


def main():
    should_cluster = "--cluster" in sys.argv
    job_description_arg = "--jd-only" in sys.argv
    asyncio.run(run_pipeline(only_jd=job_description_arg, cluster=should_cluster))


if __name__ == "__main__":
    main()

