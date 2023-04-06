import dssim.parity.asyncio as asyncio

output = []
async def set_after(fut, delay, value):
    # Sleep for *delay* seconds.
    await asyncio.sleep(delay)

    # Set *value* as a result of *fut* Future.
    fut.set_result(value)

async def main():
    # Get the current event loop.
    loop = asyncio.get_running_loop()

    # Create a new Future object.
    fut = loop.create_future()
    fut.add_done_callback(lambda cb: output.append('Future done!'))

    # Run "set_after()" coroutine in a parallel Task.
    # We are using the low-level "loop.create_task()" API here because
    # we already have a reference to the event loop at hand.
    # Otherwise we could have just used "asyncio.create_task()".
    loop.create_task(
        set_after(fut, 1, '... world'))

    output.append('hello ...')

    # Wait until *fut* has a result (1 second) and print it.
    output.append(await fut)

asyncio.run(main())
assert output == [
    "hello ...",
    "Future done!",
    '... world',
    ]
assert asyncio.get_current_loop().time == 1
