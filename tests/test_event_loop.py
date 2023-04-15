# Copyright 2020 NXP Semiconductors
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
Tests for event loop (asyncio)
'''
import unittest
from dssim.parity.asyncio import DSAsyncSimulation

async def process(sim):
    await sim.wait(1)

class TestEventLoop(unittest.TestCase):
    ''' Test the time queue class behavior '''

    def test0_loop(self):
        sim = DSAsyncSimulation()
        p = process(sim)
        sim.schedule(0, p)
        sim.run_forever()
        self.assertEqual(sim.time, float('inf'))

        sim = DSAsyncSimulation()
        p = process(sim)
        sim.schedule_event(10, 'test')
        sim.run_until_complete(p)
        self.assertEqual(sim.time, 1)
