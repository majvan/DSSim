# Copyright 2023- majvan (majvan@gmail.com)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
'''
The example is showing a code parity with asyncio
'''
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
