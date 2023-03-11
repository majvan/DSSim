#!/usr/bin/env python3
# chained.py

import dssim.parity.asyncio as asyncio
import random
import time

async def part1(n: int) -> str:
    i = random.randint(0, 10)
    print(f"part1({n}) sleeping for {i} seconds.")
    await asyncio.sleep(i)
    result = f"result{n}-1"
    print(f"Returning part1({n}) == {result}.")
    return result

async def part2(n: int, arg: str) -> str:
    i = random.randint(0, 10)
    print(f"part2{n, arg} sleeping for {i} seconds.")
    await asyncio.sleep(i)
    result = f"result{n}-2 derived from {arg}"
    print(f"Returning part2{n, arg} == {result}.")
    return result

async def chain(n: int) -> None:
    start = time.perf_counter()
    p1 = await part1(n)
    p2 = await part2(n, p1)
    end = time.perf_counter() - start
    print(f"-->Chained result{n} => {p2} (took {end:0.2f} seconds).")
    return (n, p2)

async def main(*args):
    retval = await asyncio.gather(*(chain(n) for n in args))
    return retval

if __name__ == "__main__":
    import sys
    random.seed(444)
    args = [1, 2, 3] if len(sys.argv) == 1 else map(int, sys.argv[1:])
    start = time.perf_counter()
    result = asyncio.run(main(*args))
    elapsed = time.perf_counter() - start
    assert result == [
        (1, 'result1-2 derived from result1-1'),
        (2, 'result2-2 derived from result2-1'),
        (3, 'result3-2 derived from result3-1'),
    ]
    print(f"{__file__} executed in {elapsed:0.2f} seconds. Simulation time is {asyncio.get_current_loop().time}.")
