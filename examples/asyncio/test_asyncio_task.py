import dssim.parity.asyncio as asyncio
import time

output = []
async def say_after(delay, what):
    await asyncio.sleep(delay)
    output.append(what)
    return f'returned {what}'


async def main():
    task1 = asyncio.create_task(
        say_after(1, 'hello'))

    task2 = asyncio.create_task(
        say_after(2, 'world'))

    # Wait until both tasks are completed (should take
    # around 2 seconds.)
    retval = await task1
    retval = await task2
    loop = asyncio.get_current_loop()
    print(loop.time)

asyncio.run(main())
assert output == ['hello', 'world', ]
assert asyncio.get_current_loop().time == 2