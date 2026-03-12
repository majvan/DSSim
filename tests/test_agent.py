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
Tests for DSAgent.
'''
import unittest

from dssim import DSAgent, DSProcessComponent, DSSimulation


class TestDSAgentLifecycle(unittest.TestCase):
    def test1_signal_wakes_agent_process(self):
        sim = DSSimulation()
        log = []

        class Agent(DSAgent):
            def process(self):
                log.append(('start', sim.time))
                event = yield from self.gwait()
                log.append(('event', event, sim.time))
                return 'done'

        agent = Agent(sim=sim)

        def kicker():
            yield from sim.gwait(2)
            agent.signal('ping')

        sim.schedule(0, kicker())
        sim.run(10)

        self.assertEqual(log, [('start', 0), ('event', 'ping', 2)])
        self.assertTrue(agent._scheduled_process.finished())
        self.assertEqual(agent._scheduled_process.value, 'done')

    def test2_process_component_alias(self):
        self.assertIs(DSProcessComponent, DSAgent)


class TestDSAgentContainerHelpers(unittest.TestCase):
    def test1_enter_and_gpop(self):
        sim = DSSimulation()
        c = sim.container(capacity=2)
        got = []

        class Producer(DSAgent):
            def process(self):
                self.enter_nowait(c)
                yield from self.genter(c)

        class Consumer(DSAgent):
            def process(self):
                a = yield from self.gpop(c)
                b = yield from self.gpop(c)
                got.append((a, b))

        producer = Producer(sim=sim)
        Consumer(sim=sim)
        sim.run(10)

        self.assertEqual(len(got), 1)
        self.assertIs(got[0][0], producer)
        self.assertIs(got[0][1], producer)
        self.assertEqual(len(c), 0)


class TestDSAgentResourceHelpers(unittest.TestCase):
    def test1_gget_put_nowait(self):
        sim = DSSimulation()
        r = sim.resource(amount=0, capacity=2)
        log = []

        class Worker(DSAgent):
            def process(self):
                got = yield from self.gget(r, timeout=5)
                log.append(('got', got, sim.time))
                self.put_nowait(r)
                log.append(('put', r.amount, sim.time))

        Worker(sim=sim)

        def feeder():
            yield from sim.gwait(3)
            r.put_nowait()

        sim.schedule(0, feeder())
        sim.run(10)

        self.assertEqual(log, [('got', 1, 3), ('put', 1, 3)])


if __name__ == '__main__':
    unittest.main()
