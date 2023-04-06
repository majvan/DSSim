import dssim.parity.asyncio as asyncio

output = []
async def cancel_me():
    output.append('cancel_me(): before sleep')

    try:
        # Wait for 1 hour
        await asyncio.sleep(3600)
    except asyncio.CancelledError:
        output.append('cancel_me(): cancel sleep')
        raise
    finally:
        output.append('cancel_me(): after sleep')

async def main():
    # Create a "cancel_me" Task
    task = asyncio.create_task(cancel_me())

    # Wait for 1 second
    await asyncio.sleep(1)

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        output.append('main(): cancel_me is cancelled now')

asyncio.run(main())
assert output == [
    'cancel_me(): before sleep',
    'cancel_me(): cancel sleep',
    'cancel_me(): after sleep',
    'main(): cancel_me is cancelled now',
    ]
assert asyncio.get_current_loop().time == 1
