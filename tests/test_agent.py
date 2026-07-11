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

from dssim import DSAgent, DSSimulation, AgentHistoryProbe, AgentStatsProbe, AgentActivityProbe, AgentQueueingProbe, AgentResourceProbe


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


class TestDSAgentActivityProbe(unittest.TestCase):
    def test1_time_attributed_per_activity(self):
        sim = DSSimulation()

        class Agent(DSAgent):
            def process(self):
                yield from self.hold(2)        # active/holding 2 units
                yield from self.gwait(3)        # waiting 3 units (timeout)
                yield from self.passivate()     # passive until activated at t=8
                return 'done'

        agent = Agent(sim=sim)
        probe = agent.add_activity_probe()
        self.assertIsInstance(probe, AgentActivityProbe)
        self.assertEqual(probe.name, f'{agent.name}.activity_probe')

        def kicker():
            yield from sim.gwait(8)
            agent.activate('wake')

        sim.schedule(0, kicker())
        sim.run(20)

        s = probe.stats()
        self.assertAlmostEqual(s['time_by_activity']['hold'], 2.0, places=6)
        self.assertAlmostEqual(s['time_by_activity']['gwait'], 3.0, places=6)
        self.assertAlmostEqual(s['time_by_activity']['passivate'], 3.0, places=6)
        self.assertAlmostEqual(s['pending_time'], 0.0, places=6)
        # The sum of attributed activity time equals the active lifetime (t=0..8).
        self.assertAlmostEqual(sum(s['time_by_activity'].values()), 8.0, places=6)
        self.assertEqual(s['count_by_activity'].get('activate'), 1)
        self.assertAlmostEqual(probe.time_in('passivate'), 3.0, places=6)

    def test2_time_waiting_for_specific_resource(self):
        sim = DSSimulation()
        r = sim.resource(amount=0, capacity=1)

        class Worker(DSAgent):
            def process(self):
                yield from self.gget(r, timeout=float('inf'))   # blocks until t=4

        worker = Worker(sim=sim)
        probe = worker.add_activity_probe()

        def feeder():
            yield from sim.gwait(4)
            r.put_nowait()

        sim.schedule(0, feeder())
        sim.run(20)

        s = probe.stats()
        rname = r.name
        self.assertAlmostEqual(s['time_by_resource'][rname], 4.0, places=6)
        self.assertAlmostEqual(s['time_by_activity']['gget'], 4.0, places=6)
        self.assertAlmostEqual(probe.time_waiting_for(r), 4.0, places=6)
        self.assertAlmostEqual(probe.time_waiting_for(rname), 4.0, places=6)

    def test3_immediate_acquire_costs_zero_time(self):
        sim = DSSimulation()
        r = sim.resource(amount=1, capacity=1)

        class Worker(DSAgent):
            def process(self):
                yield from self.gget(r, timeout=5)   # available immediately
                yield from self.hold(2)

        worker = Worker(sim=sim)
        probe = worker.add_activity_probe()
        sim.run(20)

        s = probe.stats()
        self.assertEqual(s['time_by_resource'].get(r.name, 0.0), 0.0)
        self.assertAlmostEqual(s['time_by_activity']['hold'], 2.0, places=6)


class TestDSAgentQueueingProbe(unittest.TestCase):
    def test1_externally_taken_agent_reports_true_queue_time(self):
        # Agent enters at t=0, a server takes it out at t=7 and activates it at t=10.
        # The queueing probe must report 7 (time in queue), even though the agent's
        # own wait ends only at t=10.
        sim = DSSimulation()
        queue = sim.queue()

        class Customer(DSAgent):
            async def process(self):
                await self.enter(queue)
                await self.wait()

        class Server(DSAgent):
            async def process(self):
                await self.sim.sleep(7)
                item = await queue.get()
                await self.sim.sleep(3)
                item.activate('done')

        customer = Customer(sim=sim)
        Server(sim=sim)
        qprobe = customer.add_queueing_probe()
        self.assertIsInstance(qprobe, AgentQueueingProbe)
        self.assertEqual(qprobe.name, f'{customer.name}.queueing_probe')
        aprobe = customer.add_activity_probe()
        sim.run(20)

        s = qprobe.stats()
        self.assertEqual(s['stay_count'], 1)
        self.assertAlmostEqual(s['stay_time_total'], 7.0, places=6)
        self.assertAlmostEqual(s['time_by_container'][queue.name], 7.0, places=6)
        self.assertAlmostEqual(qprobe.time_in_queue(queue), 7.0, places=6)
        self.assertAlmostEqual(qprobe.time_in_queue(queue.name), 7.0, places=6)
        self.assertEqual(s['currently_queued'], {})
        self.assertEqual(s['unobservable_enter_count'], 0)
        self.assertEqual(s['untracked_exit_count'], 0)
        # The activity probe keeps its own (different) semantics: wait until activated.
        self.assertAlmostEqual(aprobe.time_in('wait'), 10.0, places=6)
        # The probe unsubscribed from the queue's tx_ops after the exit.
        self.assertFalse(queue.tx_ops.has_subscribers())

    def test2_voluntary_leave_closes_the_stay(self):
        sim = DSSimulation()
        queue = sim.queue()

        class Impatient(DSAgent):
            async def process(self):
                await self.enter(queue)
                await self.wait(timeout=5)      # renege at t=5
                self.leave(queue)

        agent = Impatient(sim=sim)
        qprobe = agent.add_queueing_probe()
        sim.run(20)

        s = qprobe.stats()
        self.assertEqual(s['stay_count'], 1)
        self.assertAlmostEqual(s['stay_time_total'], 5.0, places=6)
        self.assertEqual(s['currently_queued'], {})
        self.assertEqual(len(queue), 0)

    def test3_consumer_already_waiting_records_zero_stay(self):
        # A getter blocked on the empty queue may take the agent in the same instant
        # it enters; the stay must be recorded as 0, not leak as pending forever.
        sim = DSSimulation()
        queue = sim.queue()
        taken = []

        def consumer():
            item = yield from queue.gget()
            taken.append(item)

        class Customer(DSAgent):
            async def process(self):
                await self.sim.sleep(3)
                await self.enter(queue)
                await self.wait(timeout=1)

        customer = Customer(sim=sim)
        qprobe = customer.add_queueing_probe()
        sim.schedule(0, consumer())
        sim.run(20)

        self.assertEqual(taken, [customer])
        s = qprobe.stats()
        self.assertEqual(s['stay_count'], 1)
        self.assertAlmostEqual(s['stay_time_total'], 0.0, places=6)
        self.assertEqual(s['currently_queued'], {})
        self.assertEqual(s['untracked_exit_count'], 0)
        self.assertFalse(queue.tx_ops.has_subscribers())

    def test4_still_queued_at_end_is_pending_not_counted(self):
        sim = DSSimulation()
        queue = sim.queue()

        class Customer(DSAgent):
            async def process(self):
                await self.enter(queue)
                await self.wait(timeout=2)

        customer = Customer(sim=sim)
        qprobe = customer.add_queueing_probe()
        sim.run(20)

        s = qprobe.stats()
        self.assertEqual(s['stay_count'], 0)
        self.assertEqual(s['currently_queued'], {queue.name: 1})
        self.assertEqual(len(queue), 1)


class TestDSAgentResourceProbe(unittest.TestCase):
    def test1_acquire_hold_release_accounting(self):
        sim = DSSimulation()
        r = sim.resource(amount=2, capacity=10, name='tank')

        class Worker(DSAgent):
            def process(self):
                yield from self.gget_n(r, amount=2)   # take 2 at t=0
                yield from self.hold(5)
                yield from self.gput_n(r, amount=2)   # return 2 at t=5

        worker = Worker(sim=sim)
        probe = worker.add_resource_probe()
        self.assertIsInstance(probe, AgentResourceProbe)
        self.assertEqual(probe.name, f'{worker.name}.resource_probe')
        sim.run(10)

        s = probe.stats()
        rs = s['by_resource'][r.name]
        self.assertAlmostEqual(rs['acquired_total'], 2.0, places=6)
        self.assertAlmostEqual(rs['released_total'], 2.0, places=6)
        self.assertAlmostEqual(rs['balance'], 0.0, places=6)
        self.assertAlmostEqual(rs['balance_max'], 2.0, places=6)
        # Held 2 units for 5 time units -> integral 10, avg over t=0..10 -> 1.0
        self.assertAlmostEqual(rs['balance_integral'], 10.0, places=6)
        self.assertAlmostEqual(rs['avg_held'], 1.0, places=6)
        self.assertEqual(rs['get_count'], 1)
        self.assertEqual(rs['put_count'], 1)
        self.assertAlmostEqual(probe.amount_held(r), 0.0, places=6)
        self.assertAlmostEqual(probe.amount_acquired(r), 2.0, places=6)
        self.assertAlmostEqual(probe.avg_held(r), 1.0, places=6)

    def test2_blocked_get_accounts_from_acquisition_time(self):
        sim = DSSimulation()
        r = sim.resource(amount=0, capacity=1)

        class Worker(DSAgent):
            def process(self):
                yield from self.gget(r)               # blocks until t=4

        worker = Worker(sim=sim)
        probe = worker.add_resource_probe()

        def feeder():
            yield from sim.gwait(4)
            r.put_nowait()

        sim.schedule(0, feeder())
        sim.run(10)

        rs = probe.stats()['by_resource'][r.name]
        self.assertAlmostEqual(rs['acquired_total'], 1.0, places=6)
        self.assertAlmostEqual(rs['balance'], 1.0, places=6)
        # Held 1 unit from t=4 to end of observation at t=10.
        self.assertAlmostEqual(rs['balance_integral'], 6.0, places=6)

    def test3_net_producer_has_negative_balance(self):
        sim = DSSimulation()
        r = sim.resource(amount=0, capacity=10)

        class Producer(DSAgent):
            def process(self):
                yield from self.hold(1)
                self.put_n_nowait(r, 3)               # produce 3 at t=1

        producer = Producer(sim=sim)
        probe = producer.add_resource_probe()
        sim.run(10)

        rs = probe.stats()['by_resource'][r.name]
        self.assertAlmostEqual(rs['released_total'], 3.0, places=6)
        self.assertAlmostEqual(rs['balance'], -3.0, places=6)
        self.assertEqual(rs['get_count'], 0)
        self.assertEqual(rs['put_count'], 1)

    def test4_failed_get_is_counted_not_accounted(self):
        sim = DSSimulation()
        r = sim.resource(amount=0, capacity=1)

        class Worker(DSAgent):
            def process(self):
                yield from self.gget(r, timeout=3)    # times out at t=3

        worker = Worker(sim=sim)
        probe = worker.add_resource_probe()
        sim.run(10)

        rs = probe.stats()['by_resource'][r.name]
        self.assertEqual(rs['failed_get_count'], 1)
        self.assertEqual(rs['get_count'], 0)
        self.assertAlmostEqual(rs['acquired_total'], 0.0, places=6)
        self.assertAlmostEqual(rs['balance'], 0.0, places=6)
        self.assertAlmostEqual(rs['balance_integral'], 0.0, places=6)


if __name__ == '__main__':
    unittest.main()
