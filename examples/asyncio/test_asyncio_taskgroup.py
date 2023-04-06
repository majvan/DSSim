import dssim.parity.asyncio as asyncio
import time

output = []
async def say_after(delay, what):
    await asyncio.sleep(delay)
    output.append(what)
    return f'returned {what}'


async def main():
    async with asyncio.TaskGroup() as tg:
        task1 = tg.create_task(
            say_after(1, 'hello'))

        task2 = tg.create_task(
            say_after(2, 'world'))

    # The await is implicit when the context manager exits.
    loop = asyncio.get_current_loop()
    print(loop.time)

asyncio.run(main())
assert output == ['hello', 'world', ]
assert asyncio.get_current_loop().time == 2