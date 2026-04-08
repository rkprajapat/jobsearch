import asyncio
import sys
from configs import (
    CLUSTERING_EXPLICIT_STOPWORDS,
    CLUSTERING_K,
    CLUSTERING_VERSIONED_OUTPUT,
)
from services.observer import Observer
from services.jd_clustering import JDClusteringService
from services.jd_extractor import run_jd_extractor


async def run_pipeline() -> None:
    observer = Observer()
    await observer.observe()
    await run_jd_extractor()


def main():
    if "--cluster-jd" in sys.argv or "--cluster" in sys.argv:
        service = JDClusteringService(
            k=CLUSTERING_K,
            write_versioned_output=CLUSTERING_VERSIONED_OUTPUT,
            explicit_stopwords=CLUSTERING_EXPLICIT_STOPWORDS,
        )
        saved_files = service.run_and_save()
        print(f"Cluster output written to: {saved_files['latest']}")
        if "versioned" in saved_files:
            print(f"Versioned cluster output written to: {saved_files['versioned']}")
        return

    if "--extract-jd" in sys.argv:
        asyncio.run(run_jd_extractor())
        return

    asyncio.run(run_pipeline())


if __name__ == "__main__":
    main()

