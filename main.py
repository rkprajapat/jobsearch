import asyncio
from services.observer import Observer


def main():
    observer = Observer()
    asyncio.run(observer.observe())


if __name__ == "__main__":
    main()

