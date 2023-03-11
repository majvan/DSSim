import dssim.parity.asyncio as asyncio
import time

async def say_after(delay, what):
    await asyncio.sleep(delay)
    return f'returned {what}'


async def main():
    task1 = asyncio.create_task(
        say_after(1, 'hello'))

    task2 = asyncio.create_task(
        say_after(2, 'world'))

    print(f"started at {time.strftime('%X')}")

    # Wait until both tasks are completed (should take
    # around 2 seconds.)
    retval = await task1
    retval = await task2
    loop = asyncio.get_current_loop()
    print(loop.time)

asyncio.run(main())
assert asyncio.get_current_loop().time == 2