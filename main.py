import asyncio
import sys
from services.observer import Observer
from services.jd_extractor import run_jd_extractor


def main():
    if "--extract-jd" in sys.argv:
        asyncio.run(run_jd_extractor())
        return

    observer = Observer()
    asyncio.run(observer.observe())


if __name__ == "__main__":
    main()

