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
from io import StringIO

from dssim import DSAgent, DSProcessComponent, DSSimulation, AgentHistoryProbe, AgentStatsProbe


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


class TestDSAgentSalabimStyleHelpers(unittest.TestCase):
    def test1_hold_maps_to_gsleep(self):
        sim = DSSimulation()
        log = []

        class Agent(DSAgent):
            def process(self):
                log.append(('before', sim.time))
                yield from self.hold(3)
                log.append(('after', sim.time))

        Agent(sim=sim)
        sim.run(10)
        self.assertEqual(log, [('before', 0), ('after', 3)])

    def test2_passivate_waits_until_activate_event(self):
        sim = DSSimulation()
        log = []

        class Agent(DSAgent):
            def process(self):
                log.append(('start', sim.time))
                event = yield from self.passivate()
                log.append(('event', event, sim.time))

        agent = Agent(sim=sim)

        def kicker():
            yield from sim.gwait(2)
            agent.activate('wake')

        sim.schedule(0, kicker())
        sim.run(10)
        self.assertEqual(log, [('start', 0), ('event', 'wake', 2)])

    def test3_activate_default_event_is_true(self):
        sim = DSSimulation()
        log = []

        class Agent(DSAgent):
            def process(self):
                event = yield from self.passivate()
                log.append((event, sim.time))

        agent = Agent(sim=sim)

        def kicker():
            yield from sim.gwait(1)
            agent.activate()

        sim.schedule(0, kicker())
        sim.run(10)
        self.assertEqual(log, [(True, 1)])

    def test4_tx_changed_emits_compact_agent_timeline(self):
        sim = DSSimulation()
        transitions = []

        class Agent(DSAgent):
            def process(self):
                yield from self.hold(1)
                event = yield from self.passivate()
                return event

        agent = Agent(sim=sim)
        agent.tx_changed.add_subscriber(
            sim.callback(lambda event: transitions.append((sim.time, event['change_type'], event['state'], event['reason']))),
            agent.tx_changed.Phase.PRE,
        )

        def kicker():
            yield from sim.gwait(2)
            agent.activate('wake')

        sim.schedule(0, kicker())
        sim.run(10)

        self.assertEqual(
            transitions,
            [
                (0, 'state', 'running', 'process_start'),
                (1, 'action', 'running', 'hold'),
                (2, 'action', 'running', 'activate'),
                (2, 'action', 'running', 'passivate'),
                (2, 'state', 'finished', 'process_finish'),
            ],
        )
        self.assertEqual(agent.state, 'finished')


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

    def test2_tx_changed_emits_container_action_events(self):
        sim = DSSimulation()
        c = sim.container(capacity=2)
        actions = []

        class Agent(DSAgent):
            def process(self):
                self.enter_nowait(c)
                _ = self.pop_nowait(c)
                self.enter_nowait(c)
                self.leave(c)

        agent = Agent(sim=sim)
        agent.tx_changed.add_subscriber(
            sim.callback(lambda event: actions.append((event['change_type'], event['reason'], event.get('details', {}).get('success')))),
            agent.tx_changed.Phase.PRE,
        )
        sim.run(10)

        action_events = [(reason, success) for change_type, reason, success in actions if change_type == 'action']
        self.assertEqual(
            action_events,
            [
                ('enter_nowait', True),
                ('pop_nowait', True),
                ('enter_nowait', True),
                ('leave', True),
            ],
        )


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

    def test2_tx_changed_emits_resource_action_events(self):
        sim = DSSimulation()
        r = sim.resource(amount=0, capacity=2)
        actions = []

        class Worker(DSAgent):
            def process(self):
                _ = yield from self.gget(r, timeout=5)
                self.put_nowait(r)

        worker = Worker(sim=sim)
        worker.tx_changed.add_subscriber(
            sim.callback(lambda event: actions.append((event['change_type'], event['reason'], event.get('details', {}).get('success')))),
            worker.tx_changed.Phase.PRE,
        )

        def feeder():
            yield from sim.gwait(2)
            r.put_nowait()

        sim.schedule(0, feeder())
        sim.run(10)

        action_events = [(reason, success) for change_type, reason, success in actions if change_type == 'action']
        self.assertEqual(
            action_events,
            [
                ('gget', True),
                ('put_nowait', True),
            ],
        )


class TestDSAgentHistoryProbe(unittest.TestCase):
    def test1_add_history_probe_and_capture_events(self):
        sim = DSSimulation()

        class Agent(DSAgent):
            def process(self):
                yield from self.hold(1)
                self.activate('wake')
                yield from self.passivate()
                return 'done'

        agent = Agent(sim=sim)
        probe = agent.add_history_probe()
        self.assertIsInstance(probe, AgentHistoryProbe)
        self.assertEqual(probe.name, f'{agent.name}.history_probe')

        sim.run(10)
        history = probe.history()
        reasons = [event.get('reason') for event in history]
        self.assertIn('process_start', reasons)
        self.assertIn('hold', reasons)
        self.assertIn('activate', reasons)
        self.assertIn('passivate', reasons)
        self.assertIn('process_finish', reasons)

    def test2_format_and_dump_history(self):
        sim = DSSimulation()

        class Agent(DSAgent):
            def process(self):
                yield from self.hold(1)
                return 'done'

        agent = Agent(sim=sim)
        probe = agent.add_history_probe(max_events=10)
        sim.run(10)

        text = probe.format_history()
        self.assertIn('Agent history:', text)
        self.assertIn('process_start', text)
        self.assertIn('hold', text)
        self.assertIn('process_finish', text)

        buf = StringIO()
        dumped = probe.dump_history(file=buf)
        self.assertEqual(dumped, text)
        self.assertEqual(buf.getvalue(), text + '\n')


class TestDSAgentStatsProbe(unittest.TestCase):
    def test1_add_stats_probe_name(self):
        sim = DSSimulation()

        class Agent(DSAgent):
            def process(self):
                yield from self.hold(1)
                return 'done'

        agent = Agent(name='a0', sim=sim)
        probe = agent.add_stats_probe()
        self.assertIsInstance(probe, AgentStatsProbe)
        self.assertEqual(probe.name, 'a0.stats_probe')
        probe2 = agent.add_stats_probe(name='ops')
        self.assertEqual(probe2.name, 'a0.ops')

    def test2_stats_probe_counts_and_state_time(self):
        sim = DSSimulation()

        class Agent(DSAgent):
            def process(self):
                yield from self.hold(1)
                self.activate('wake')
                yield from self.passivate()
                return 'done'

        agent = Agent(sim=sim)
        probe = agent.add_stats_probe()
        sim.run(10)

        stats = probe.stats()
        self.assertEqual(stats['event_count'], 5)
        self.assertEqual(stats['state_event_count'], 2)
        self.assertEqual(stats['action_event_count'], 3)
        self.assertEqual(stats['current_state'], 'finished')
        self.assertEqual(stats['reason_counts'].get('process_start', 0), 1)
        self.assertEqual(stats['reason_counts'].get('hold', 0), 1)
        self.assertEqual(stats['reason_counts'].get('activate', 0), 1)
        self.assertEqual(stats['reason_counts'].get('passivate', 0), 1)
        self.assertEqual(stats['reason_counts'].get('process_finish', 0), 1)
        self.assertAlmostEqual(stats['duration'], 10.0, places=6)
        self.assertAlmostEqual(stats['state_time'].get('running', 0.0), 1.0, places=6)
        self.assertAlmostEqual(stats['state_time'].get('finished', 0.0), 9.0, places=6)


if __name__ == '__main__':
    unittest.main()
