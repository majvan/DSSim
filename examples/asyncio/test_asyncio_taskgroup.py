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