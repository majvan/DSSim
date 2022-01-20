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
