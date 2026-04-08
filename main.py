import asyncio
import sys
from services.observer import Observer
from services.jd_extractor import run_jd_extractor


async def run_pipeline() -> None:
    observer = Observer()
    await observer.observe()
    await run_jd_extractor()


def main():
    if "--extract-jd" in sys.argv:
        asyncio.run(run_jd_extractor())
        return

    asyncio.run(run_pipeline())


if __name__ == "__main__":
    main()

