"""The watchdog without the web panel (install mode "api"): the same rules the panel uses
(panel/health.py), run as the unit speech-spark-watch. Restarts a hung ASR / TTS service or engine,
at most 3 times per unit and hour, and does nothing while an update runs."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "panel"))
import health  # noqa: E402
import update  # noqa: E402


async def main():
    print("watchdog: watching the ASR and TTS services every", health.WATCH_EVERY, "s", flush=True)
    while True:
        await asyncio.sleep(health.WATCH_EVERY)
        try:
            await health.watch_once(update.update_running)
        except Exception as e:
            print("watchdog:", type(e).__name__, e, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
