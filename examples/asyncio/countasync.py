#!/usr/bin/env python3
# countasync.py

import dssim.parity.asyncio as asyncio

async def count():
    print("One")
    await asyncio.sleep(1)
    print("Two")
    return True

async def main():
    await asyncio.gather(count(), count(), count())
    print("Done")

if __name__ == "__main__":
    import time
    s = time.perf_counter()
    asyncio.run(main())
    elapsed = time.perf_counter() - s
    print(f"{__file__} executed in {elapsed:0.2f} seconds. Simulation time is {asyncio.get_current_loop().time}.")
