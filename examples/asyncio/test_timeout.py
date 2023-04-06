import dssim.parity.asyncio as asyncio

async def main():
    # Create a new Future object.
    loop = asyncio.get_running_loop()
    value = ''
    async with asyncio.timeout(5) as cm1:
        value += '[0,cm1-5]'
        await asyncio.sleep(2)
        value += '[2,cm1-5]'
        async with asyncio.timeout(5) as cm2:
            value += '[2,cm1-5,cm2-7]'
            await asyncio.sleep(1)
            cm1.reschedule(2)
            value += '[3,cm1-5,cm2-7]'
            await asyncio.sleep(1)
            cm2.reschedule(2)
            value += '[4,cm1-5,cm2-6]'
            await asyncio.sleep(3)
            value += '[7,cm1-5,cm2-6]'
        value += '[6,cm1-5,cm2-6]'
        await asyncio.sleep(10)
        value += '[16,cm1-5,cm2-6]'
    value += '[5,cm1-5,cm2-6]'
    await asyncio.sleep(10)
    assert not cm2.expired()
    assert cm1.expired()
    assert loop.time == 15
    assert value == '[0,cm1-5][2,cm1-5][2,cm1-5,cm2-7][3,cm1-5,cm2-7][4,cm1-5,cm2-6][5,cm1-5,cm2-6]'
    print('Done.')

asyncio.run(main())
assert asyncio.get_current_loop().time == 15
