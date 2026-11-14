"""Time a GZM sync of six lines into an empty store, then adding one line.

Prints the download, store and stop choices time of each step, the downloads made, and the
peak memory. It reaches the GZM portal, so run it where the network is open, for example:

    docker cp scripts/measure_sync.py <container>:/tmp/ && docker exec -w /tmp <container> \
        python3 -I /tmp/measure_sync.py /tmp/measure
"""

import asyncio
import resource
import shutil
import sys
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

import aiohttp
import gtfs_hub.hub as hub_module
from gtfs_hub import GtfsHub, LineKey
from gtfs_hub_gzm import GzmProvider

FIRST = [
    LineKey(0, "T6"),
    LineKey(3, "11"),
    LineKey(3, "600"),
    LineKey(3, "601"),
    LineKey(3, "70"),
    LineKey(3, "B"),
]
ADDED = LineKey(0, "T1")
spent: dict[str, float] = {}
downloads = 0


def timed_download(
    download: Callable[..., Awaitable[None]],
) -> Callable[..., Awaitable[None]]:
    async def wrapper(*args: object, **kwargs: object) -> None:
        global downloads  # noqa: PLW0603 - a script tally
        downloads += 1
        start = time.perf_counter()
        try:
            await download(*args, **kwargs)
        finally:
            spent["download"] += time.perf_counter() - start

    return wrapper


async def main(folder: Path) -> None:
    global downloads  # noqa: PLW0603 - a script tally
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    hub_module.async_download = timed_download(hub_module.async_download)  # type: ignore[assignment]
    async with aiohttp.ClientSession() as session:
        hub = GtfsHub(GzmProvider(), folder / "gzm.db", session)
        for label, selection in (("six lines", FIRST), ("add T1", [*FIRST, ADDED])):
            spent["download"] = 0.0
            downloads = 0
            start = time.perf_counter()
            result = await hub.async_sync(selection)
            total = time.perf_counter() - start
            start = time.perf_counter()
            await hub.async_stop_choices(selection)
            choices = time.perf_counter() - start
            print(
                f"{label}: total {total:.1f} s, download {spent['download']:.1f} s"
                f" ({downloads} files), store {total - spent['download']:.1f} s,"
                f" stop choices {choices:.2f} s, {result}",
                flush=True,
            )
    kept = folder / "gzm.db.files"
    size = sum(file.stat().st_size for file in kept.iterdir()) if kept.is_dir() else 0
    print(f"kept files {size / 2**20:.1f} MB")
    print(f"peak RSS {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.0f} MB (Linux)")


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
