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
async def count():
    output.append("One")
    await asyncio.sleep(1)
    output.append("Two")
    return True

async def main():
    await asyncio.gather(count(), count(), count())
    print("Done")

if __name__ == "__main__":
    import time
    asyncio.run(main())
    assert asyncio.get_current_loop().time == 1
    assert output == ["One", "One", "One", "Two", "Two", "Two", ]
    print(f"Simulation time is {asyncio.get_current_loop().time}.")
