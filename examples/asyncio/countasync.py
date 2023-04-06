#!/usr/bin/env python3
# countasync.py

import dssim.parity.asyncio as asyncio

output = []
async def count():
    output.append("One")
    await asyncio.sleep(1)
    output.append("Two")
    return True

async def main():
    await asyncio.gather(count(), count(), count())
    print("Done")

if __name__ == "__main__":
    import time
    asyncio.run(main())
    assert asyncio.get_current_loop().time == 1
    assert output == ["One", "One", "One", "Two", "Two", "Two", ]
    print(f"Simulation time is {asyncio.get_current_loop().time}.")
