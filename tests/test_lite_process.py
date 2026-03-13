# Copyright 2026- majvan (majvan@gmail.com)
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
Tests for DSLiteProcess.
'''
import unittest

from dssim import DSSimulation, LiteLayer2, DSLiteProcess
from dssim.pubsub.base import DSAbortException


class TestDSLiteProcess(unittest.TestCase):
    def test1_generator_lifecycle(self):
        sim = DSSimulation(layer2=LiteLayer2)
        log = []

        def proc():
            log.append(('start', sim.time))
            event = yield from sim.gwait(2)
            log.append(('event', event, sim.time))
            return 'done'

        p = DSLiteProcess(proc(), sim=sim).schedule(0)
        sim.schedule_event(1, 'x', p)
        sim.run(10)

        self.assertTrue(p.started())
        self.assertTrue(p.finished())
        self.assertEqual(p.value, 'done')
        self.assertIsNone(p.exc)
        self.assertEqual(log, [('start', 0), ('event', 'x', 1)])

    def test2_abort_before_start(self):
        sim = DSSimulation(layer2=LiteLayer2)

        def proc():
            yield from sim.gwait(1)
            return 'done'

        p = DSLiteProcess(proc(), sim=sim).schedule(5)
        p.abort()
        sim.run(10)

        self.assertFalse(p.started())
        self.assertTrue(p.finished())
        self.assertIsInstance(p.exc, DSAbortException)

    def test3_abort_while_waiting(self):
        sim = DSSimulation(layer2=LiteLayer2)
        seen = []

        def proc():
            try:
                yield from sim.gwait(10)
            except DSAbortException:
                seen.append('aborted')
                return 'aborted'
            return 'unexpected'

        p = DSLiteProcess(proc(), sim=sim).schedule(0)

        def aborter():
            yield from sim.gwait(1)
            p.abort()

        sim.schedule(0, aborter())
        sim.run(10)

        self.assertTrue(p.finished())
        self.assertEqual(p.value, 'aborted')
        self.assertEqual(seen, ['aborted'])

    def test4_sim_schedule_keeps_generator(self):
        sim = DSSimulation(layer2=LiteLayer2)
        ran = []

        def proc():
            ran.append(sim.time)
            yield from sim.gwait(1)
            ran.append(sim.time)

        gen = proc()
        scheduled = sim.schedule(0, gen)
        self.assertIs(scheduled, gen)
        sim.run(10)
        self.assertEqual(ran, [0, 1])

    def test5_sim_schedule_keeps_coroutine(self):
        sim = DSSimulation(layer2=LiteLayer2)
        ran = []

        async def proc():
            ran.append(sim.time)
            await sim.wait(1)
            ran.append(sim.time)

        coro = proc()
        scheduled = sim.schedule(0, coro)
        self.assertIs(scheduled, coro)
        sim.run(10)
        self.assertEqual(ran, [0, 1])

    def test6_sim_process_factory(self):
        sim = DSSimulation(layer2=LiteLayer2)

        def proc():
            yield from sim.gwait(1)
            return 'ok'

        p = sim.process(proc())
        self.assertIsInstance(p, DSLiteProcess)
        p.schedule(0)
        sim.run(10)
        self.assertTrue(p.finished())
        self.assertEqual(p.value, 'ok')


if __name__ == '__main__':
    unittest.main()
