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
Tests for two-phase (guard + commit) circuit evaluation over side-effecting
queue conditions: exactly-one semantics for OR, all-or-nothing for AND,
selector-based OR arbitration (overflow chain / round robin) and reservation
hygiene.
'''
import unittest

from dssim import DSSimulation, DSQueue, DSPutRouter, DSGetRouter, DSResource, DSPriorityResource


class TestTwoPhaseOr(unittest.TestCase):
    '''An OR of putter/getter policies commits exactly one branch.'''

    def setUp(self):
        self.sim = DSSimulation()

    def test1_or_put_precheck_commits_exactly_one(self):
        q0 = DSQueue(capacity=1, sim=self.sim, name='q0')
        q1 = DSQueue(capacity=1, sim=self.sim, name='q1')
        f0 = self.sim.filter(q0.policy_for_put('x'))
        f1 = self.sim.filter(q1.policy_for_put('x'))
        done = {}

        def putter():
            done['payload'] = yield from (f0 | f1).check_and_gwait(10)
            done['time'] = self.sim.time

        self.sim.schedule(0, putter())
        self.sim.run(20)

        self.assertEqual(done['time'], 0)
        self.assertEqual(list(q0), ['x'])
        self.assertEqual(len(q1), 0)
        self.assertEqual(done['payload'], {f0: ('x',)})

    def test2_or_put_deferred_commits_exactly_one(self):
        # Both queues full; both free a slot at the same simulation instant.
        q0 = DSQueue(capacity=1, sim=self.sim, name='q0')
        q1 = DSQueue(capacity=1, sim=self.sim, name='q1')
        q0.put_nowait('blocker0')
        q1.put_nowait('blocker1')
        f0 = self.sim.filter(q0.policy_for_put('x'))
        f1 = self.sim.filter(q1.policy_for_put('x'))
        done = {}

        def putter():
            done['payload'] = yield from (f0 | f1).check_and_gwait(10)
            done['time'] = self.sim.time

        def drainer():
            yield from self.sim.gwait(1)
            q0.get_nowait()
            q1.get_nowait()

        self.sim.schedule(0, putter())
        self.sim.schedule(0, drainer())
        self.sim.run(20)

        self.assertEqual(done['time'], 1)
        self.assertEqual(len(q0) + len(q1), 1)
        self.assertEqual(list(q0) + list(q1), ['x'])
        self.assertEqual(q0._reserved_in, 0)
        self.assertEqual(q1._reserved_in, 0)

    def test3_or_get_precheck_consumes_exactly_one(self):
        q0 = DSQueue(sim=self.sim, name='q0')
        q1 = DSQueue(sim=self.sim, name='q1')
        q0.put_nowait('a')
        q1.put_nowait('b')
        f0 = self.sim.filter(q0.policy_for_get())
        f1 = self.sim.filter(q1.policy_for_get())
        done = {}

        def getter():
            done['payload'] = yield from (f0 | f1).check_and_gwait(10)

        self.sim.schedule(0, getter())
        self.sim.run(20)

        self.assertEqual(done['payload'], {f0: 'a'})
        self.assertEqual(len(q0), 0)
        self.assertEqual(list(q1), ['b'])  # untouched - the losing branch must not dequeue

    def test4_or_put_timeout_releases_reservations(self):
        q0 = DSQueue(capacity=1, sim=self.sim, name='q0')
        q1 = DSQueue(capacity=1, sim=self.sim, name='q1')
        q0.put_nowait('blocker0')
        q1.put_nowait('blocker1')
        f0 = self.sim.filter(q0.policy_for_put('x'))
        f1 = self.sim.filter(q1.policy_for_put('x'))
        done = {}

        def putter():
            done['payload'] = yield from (f0 | f1).check_and_gwait(5)
            done['time'] = self.sim.time

        self.sim.schedule(0, putter())
        self.sim.run(20)

        # Circuit waits return an empty payload map on timeout (framework-wide behavior).
        self.assertEqual(done['payload'], {})
        self.assertEqual(done['time'], 5)
        self.assertEqual(q0._reserved_in, 0)
        self.assertEqual(q1._reserved_in, 0)
        # Queues stay fully usable after the timed-out attempt.
        self.assertEqual(q0.get_nowait(), 'blocker0')
        self.assertEqual(q0.put_nowait('y'), ('y',))

    def test5_or_pure_branch_fires_without_committing_puts(self):
        q0 = DSQueue(capacity=1, sim=self.sim, name='q0')
        q0.put_nowait('blocker')
        gate_ep = self.sim.publisher(name='gate_ep')
        f_put = self.sim.filter(q0.policy_for_put('x'))
        f_gate = self.sim.filter(lambda e: e == 'go', eps={gate_ep: {'tier': gate_ep.Phase.CONSUME, 'params': {}}})
        done = {}

        def waiter():
            done['payload'] = yield from (f_put | f_gate).check_and_gwait(10)
            done['time'] = self.sim.time

        def opener():
            yield from self.sim.gwait(1)
            gate_ep.signal('go')

        self.sim.schedule(0, waiter())
        self.sim.schedule(0, opener())
        self.sim.run(20)

        self.assertEqual(done['time'], 1)
        self.assertEqual(done['payload'], {f_gate: 'go'})
        self.assertEqual(list(q0), ['blocker'])  # no put happened
        self.assertEqual(q0._reserved_in, 0)


class TestTwoPhaseAnd(unittest.TestCase):
    '''An AND over side-effecting conditions is all-or-nothing.'''

    def setUp(self):
        self.sim = DSSimulation()

    def test1_and_put_no_partial_commit(self):
        qa = DSQueue(capacity=1, sim=self.sim, name='qa')
        qb = DSQueue(capacity=1, sim=self.sim, name='qb')
        qb.put_nowait('blocker')
        f_a = self.sim.filter(qa.policy_for_put('x'))
        f_b = self.sim.filter(qb.policy_for_put('y'))
        done = {}
        midstate = {}

        def putter():
            done['payload'] = yield from (f_a & f_b).check_and_gwait(10)
            done['time'] = self.sim.time

        def checker():
            yield from self.sim.gwait(1)
            # qb is still blocked: nothing may have leaked into qa.
            midstate['qa'] = list(qa)

        def drainer():
            yield from self.sim.gwait(2)
            qb.get_nowait()

        self.sim.schedule(0, putter())
        self.sim.schedule(0, checker())
        self.sim.schedule(0, drainer())
        self.sim.run(20)

        self.assertEqual(midstate['qa'], [])
        self.assertEqual(done['time'], 2)
        self.assertEqual(list(qa), ['x'])
        self.assertEqual(list(qb), ['y'])
        self.assertEqual(done['payload'], {f_a: ('x',), f_b: ('y',)})

    def test2_and_put_same_queue_shared_capacity(self):
        # Two puts into one queue must see each other's claims: with capacity 1
        # the AND can never fire; with capacity 2 it fires with both items.
        q1 = DSQueue(capacity=1, sim=self.sim, name='q1')
        f_x = self.sim.filter(q1.policy_for_put('x'))
        f_y = self.sim.filter(q1.policy_for_put('y'))
        done = {}

        def putter():
            done['payload'] = yield from (f_x & f_y).check_and_gwait(5)

        self.sim.schedule(0, putter())
        self.sim.run(20)

        self.assertEqual(done['payload'], {})  # timeout - empty payload map
        self.assertEqual(len(q1), 0)  # neither put leaked
        self.assertEqual(q1._reserved_in, 0)

        q2 = DSQueue(capacity=2, sim=self.sim, name='q2')
        g_x = self.sim.filter(q2.policy_for_put('x'))
        g_y = self.sim.filter(q2.policy_for_put('y'))

        def putter2():
            done['payload2'] = yield from (g_x & g_y).check_and_gwait(5)

        self.sim.schedule(0, putter2())
        self.sim.run(40)

        self.assertEqual(done['payload2'], {g_x: ('x',), g_y: ('y',)})
        self.assertEqual(list(q2), ['x', 'y'])
        self.assertEqual(q2._reserved_in, 0)

    def test3_and_get_same_queue_positional_claims(self):
        # Two gets from one queue claim consecutive head items.
        q = DSQueue(sim=self.sim, name='q')
        q.put_nowait('first')
        q.put_nowait('second')
        q.put_nowait('third')
        f_1 = self.sim.filter(q.policy_for_get())
        f_2 = self.sim.filter(q.policy_for_get())
        done = {}

        def getter():
            done['payload'] = yield from (f_1 & f_2).check_and_gwait(5)

        self.sim.schedule(0, getter())
        self.sim.run(20)

        self.assertEqual(done['payload'], {f_1: 'first', f_2: 'second'})
        self.assertEqual(list(q), ['third'])
        self.assertEqual(q._reserved_out, 0)

    def test4_rendezvous_get_put_atomic_transfer(self):
        # Move an item from qa to qb only when qb has room - never hold it in limbo.
        qa = DSQueue(sim=self.sim, name='qa')
        qb = DSQueue(capacity=1, sim=self.sim, name='qb')
        qb.put_nowait('blocker')
        f_get = self.sim.filter(qa.policy_for_get())
        f_put = self.sim.filter(qb.policy_for_put('moved'))
        done = {}
        midstate = {}

        def mover():
            done['payload'] = yield from (f_get & f_put).check_and_gwait(10)
            done['time'] = self.sim.time

        def producer():
            yield from self.sim.gwait(2)
            qa.put_nowait('payload')

        def checker():
            yield from self.sim.gwait(3)
            # qb still blocked: the item must not have been taken out of qa.
            midstate['qa'] = list(qa)

        def drainer():
            yield from self.sim.gwait(4)
            qb.get_nowait()

        self.sim.schedule(0, mover())
        self.sim.schedule(0, producer())
        self.sim.schedule(0, checker())
        self.sim.schedule(0, drainer())
        self.sim.run(20)

        self.assertEqual(midstate['qa'], ['payload'])
        self.assertEqual(done['time'], 4)
        self.assertEqual(len(qa), 0)
        self.assertEqual(list(qb), ['moved'])
        self.assertEqual(done['payload'], {f_get: 'payload', f_put: ('moved',)})


class TestTwoPhaseSelectors(unittest.TestCase):
    '''OR-branch arbitration: ordered = overflow chain, round_robin = fair spread.'''

    def setUp(self):
        self.sim = DSSimulation()

    def test1_ordered_selector_overflow_chain(self):
        q0 = DSQueue(capacity=2, sim=self.sim, name='q0')
        q1 = DSQueue(sim=self.sim, name='q1')
        f0 = self.sim.filter(q0.policy_for_put('x'))
        f1 = self.sim.filter(q1.policy_for_put('x'))
        route = f0 | f1

        def putter():
            for _ in range(4):
                yield from route.check_and_gwait(1)
                route.reset()

        self.sim.schedule(0, putter())
        self.sim.run(20)

        self.assertEqual(list(q0), ['x', 'x'])  # fill the first...
        self.assertEqual(list(q1), ['x', 'x'])  # ...then spill to the next

    def test2_round_robin_selector_distributes(self):
        queues = [DSQueue(sim=self.sim, name=f'q{i}') for i in range(3)]
        filters = [self.sim.filter(q.policy_for_put('x')) for q in queues]
        route = (filters[0] | filters[1] | filters[2]).set_selector('round_robin')

        def putter():
            for _ in range(6):
                yield from route.check_and_gwait(1)
                route.reset()

        self.sim.schedule(0, putter())
        self.sim.run(20)

        self.assertEqual([len(q) for q in queues], [2, 2, 2])

    def test3_round_robin_skips_full_queue(self):
        q0 = DSQueue(capacity=1, sim=self.sim, name='q0')
        q1 = DSQueue(capacity=1, sim=self.sim, name='q1')
        q2 = DSQueue(sim=self.sim, name='q2')
        q1.put_nowait('blocker')
        f0 = self.sim.filter(q0.policy_for_put('x'))
        f1 = self.sim.filter(q1.policy_for_put('x'))
        f2 = self.sim.filter(q2.policy_for_put('x'))
        route = (f0 | f1 | f2).set_selector('round_robin')

        def putter():
            for _ in range(3):
                yield from route.check_and_gwait(1)
                route.reset()

        self.sim.schedule(0, putter())
        self.sim.run(20)

        # Round 1 -> q0; round 2 starts at q1 (full) -> q2; round 3 starts at q0 (full) -> q2.
        self.assertEqual(list(q0), ['x'])
        self.assertEqual(list(q1), ['blocker'])
        self.assertEqual(list(q2), ['x', 'x'])

    def test4_round_robin_loop_with_load_rebinding(self):
        # The static-router loop: one circuit reused across iterations, items
        # rebound per attempt via _PutCond.load(), cursor giving round robin.
        queues = [DSQueue(sim=self.sim, name=f'q{i}') for i in range(2)]
        policies = [q.policy_for_put('placeholder') for q in queues]
        filters = [self.sim.filter(p) for p in policies]
        route = (filters[0] | filters[1]).set_selector('round_robin')

        def putter():
            for item in ('a', 'b', 'c', 'd'):
                for policy in policies:
                    policy['cond'].load(item)
                yield from route.check_and_gwait(1)
                route.reset()

        self.sim.schedule(0, putter())
        self.sim.run(20)

        self.assertEqual(list(queues[0]), ['a', 'c'])
        self.assertEqual(list(queues[1]), ['b', 'd'])

    def test5_selector_validation(self):
        q0 = DSQueue(sim=self.sim, name='q0')
        q1 = DSQueue(sim=self.sim, name='q1')
        route = self.sim.filter(q0.policy_for_put('x')) | self.sim.filter(q1.policy_for_put('x'))
        with self.assertRaises(ValueError):
            route.set_selector('random')


class TestTwoPhaseStandalone(unittest.TestCase):
    '''Outside a circuit the conditions keep single-phase (guard+commit) behavior.'''

    def setUp(self):
        self.sim = DSSimulation()

    def test1_standalone_put_filter_unchanged(self):
        q = DSQueue(capacity=1, sim=self.sim, name='q')
        q.put_nowait('blocker')
        done = {}

        def putter():
            f = self.sim.filter(q.policy_for_put('x'))
            done['payload'] = yield from f.check_and_gwait(10)
            done['time'] = self.sim.time

        def drainer():
            yield from self.sim.gwait(2)
            q.get_nowait()

        self.sim.schedule(0, putter())
        self.sim.schedule(0, drainer())
        self.sim.run(20)

        self.assertEqual(done['time'], 2)
        self.assertEqual(list(q), ['x'])
        self.assertEqual(q._reserved_in, 0)


class TestRouters(unittest.TestCase):
    '''DSPutRouter / DSGetRouter facade: one call per item over a static circuit.'''

    def setUp(self):
        self.sim = DSSimulation()

    def test1_put_router_round_robin(self):
        queues = [DSQueue(sim=self.sim, name=f'q{i}') for i in range(3)]
        router = DSPutRouter(*queues, selector='round_robin', sim=self.sim)
        targets = []

        def producer():
            for i in range(6):
                target = yield from router.gput(1, f'job{i}')
                targets.append(target)

        self.sim.schedule(0, producer())
        self.sim.run(20)

        self.assertEqual(targets, [queues[0], queues[1], queues[2]] * 2)
        self.assertEqual([list(q) for q in queues],
                         [['job0', 'job3'], ['job1', 'job4'], ['job2', 'job5']])
        self.assertIs(router.target, queues[2])

    def test2_put_router_ordered_overflow_chain(self):
        q0 = DSQueue(capacity=2, sim=self.sim, name='q0')
        q1 = DSQueue(sim=self.sim, name='q1')
        router = DSPutRouter(q0, q1, sim=self.sim)

        def producer():
            for i in range(4):
                yield from router.gput(1, f'job{i}')

        self.sim.schedule(0, producer())
        self.sim.run(20)

        self.assertEqual(list(q0), ['job0', 'job1'])
        self.assertEqual(list(q1), ['job2', 'job3'])

    def test3_put_router_blocks_with_backpressure_and_times_out(self):
        q = DSQueue(capacity=1, sim=self.sim, name='q')
        q.put_nowait('blocker')
        router = DSPutRouter(q, sim=self.sim)
        done = {}

        def producer():
            done['first'] = yield from router.gput(5, 'x')     # times out
            done['first_time'] = self.sim.time
            done['second'] = yield from router.gput(10, 'y')   # blocks, then lands
            done['second_time'] = self.sim.time

        def drainer():
            yield from self.sim.gwait(8)
            q.get_nowait()

        self.sim.schedule(0, producer())
        self.sim.schedule(0, drainer())
        self.sim.run(30)

        self.assertIsNone(done['first'])
        self.assertEqual(done['first_time'], 5)
        self.assertIs(done['second'], q)
        self.assertEqual(done['second_time'], 8)
        self.assertEqual(list(q), ['y'])
        self.assertEqual(q._reserved_in, 0)

    def test4_get_router_takes_from_first_ready_queue(self):
        q0 = DSQueue(sim=self.sim, name='q0')
        q1 = DSQueue(sim=self.sim, name='q1')
        q1.put_nowait('early')
        router = DSGetRouter(q0, q1, sim=self.sim)
        got = []

        def consumer():
            for _ in range(2):
                item = yield from router.gget(10)
                got.append((self.sim.time, item, router.source))

        def producer():
            yield from self.sim.gwait(3)
            q0.put_nowait('late')

        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)

        self.assertEqual(got, [(0, 'early', q1), (3, 'late', q0)])
        self.assertEqual(len(q0) + len(q1), 0)

    def test5_router_requires_channels(self):
        with self.assertRaises(ValueError):
            DSPutRouter(sim=self.sim)


class TestResourceTwoPhase(unittest.TestCase):
    '''Plain resources compose into two-phase circuits and route like queues.'''

    def setUp(self):
        self.sim = DSSimulation()

    def test1_get_router_takes_from_first_nonempty_pool(self):
        pool_a = DSResource(amount=0, sim=self.sim, name='pool_a')
        pool_b = DSResource(amount=5, sim=self.sim, name='pool_b')
        router = DSGetRouter(pool_a, pool_b, amount=2, sim=self.sim)
        done = {}

        def taker():
            done['got'] = yield from router.gget(10)
            done['source'] = router.source

        self.sim.schedule(0, taker())
        self.sim.run(20)

        self.assertEqual(done['got'], 2)
        self.assertIs(done['source'], pool_b)
        self.assertEqual(pool_a.amount, 0)   # losing branch untouched
        self.assertEqual(pool_b.amount, 3)
        self.assertEqual(pool_b._reserved_out, 0)

    def test2_put_router_backpressure_on_capacity(self):
        pool_a = DSResource(amount=2, capacity=2, sim=self.sim, name='pool_a')
        pool_b = DSResource(amount=2, capacity=2, sim=self.sim, name='pool_b')
        router = DSPutRouter(pool_a, pool_b, sim=self.sim)
        done = {}

        def depositor():
            done['target'] = yield from router.gput(10, 2)   # deposit 2 units
            done['time'] = self.sim.time

        def drainer():
            yield from self.sim.gwait(3)
            pool_b.get_n_nowait(2)

        self.sim.schedule(0, depositor())
        self.sim.schedule(0, drainer())
        self.sim.run(20)

        self.assertIs(done['target'], pool_b)
        self.assertEqual(done['time'], 3)
        self.assertEqual((pool_a.amount, pool_b.amount), (2, 2))
        self.assertEqual(pool_b._reserved_in, 0)

    def test3_cross_kind_rendezvous_pool_and_queue(self):
        # Take 2 units from the pool AND enqueue a job - atomically, or neither.
        pool = DSResource(amount=1, sim=self.sim, name='pool')
        q = DSQueue(sim=self.sim, name='q')
        f_fuel = self.sim.filter(pool.policy_for_get(amount=2))
        f_job = self.sim.filter(q.policy_for_put('job'))
        done = {}
        midstate = {}

        def launcher():
            done['payload'] = yield from (f_fuel & f_job).check_and_gwait(10)
            done['time'] = self.sim.time

        def checker():
            yield from self.sim.gwait(1)
            # only 1 unit available: nothing may have been taken or enqueued
            midstate['state'] = (pool.amount, len(q))

        def refueler():
            yield from self.sim.gwait(2)
            pool.put_n_nowait(1)

        self.sim.schedule(0, launcher())
        self.sim.schedule(0, checker())
        self.sim.schedule(0, refueler())
        self.sim.run(20)

        self.assertEqual(midstate['state'], (1, 0))
        self.assertEqual(done['time'], 2)
        self.assertEqual(pool.amount, 0)
        self.assertEqual(list(q), ['job'])
        self.assertEqual(done['payload'], {f_fuel: 2, f_job: ('job',)})

    def test4_and_same_pool_shared_claims(self):
        # Two takes from one pool must see each other's claims: 4 units cannot
        # serve 3+3, and nothing leaks while the AND cannot fire.
        pool = DSResource(amount=4, sim=self.sim, name='pool')
        f_1 = self.sim.filter(pool.policy_for_get(amount=3))
        f_2 = self.sim.filter(pool.policy_for_get(amount=3))
        done = {}

        def taker():
            done['payload'] = yield from (f_1 & f_2).check_and_gwait(5)

        self.sim.schedule(0, taker())
        self.sim.run(20)

        self.assertEqual(done['payload'], {})  # timeout - empty payload map
        self.assertEqual(pool.amount, 4)       # nothing leaked
        self.assertEqual(pool._reserved_out, 0)

    def test5_mixed_channel_kinds_rejected(self):
        q = DSQueue(sim=self.sim, name='q')
        pool = DSResource(amount=1, sim=self.sim, name='pool')
        with self.assertRaises(ValueError):
            DSGetRouter(q, pool, sim=self.sim)

    def test6_one_pass_priority_resource_rejected(self):
        # Priority/preemptive acquisition is inherently effectful - its policy
        # stays one-pass, and the router must refuse it rather than mis-route.
        pool_a = DSPriorityResource(amount=1, sim=self.sim, name='prio_a')
        pool_b = DSPriorityResource(amount=1, sim=self.sim, name='prio_b')
        with self.assertRaises(ValueError):
            DSGetRouter(pool_a, pool_b, sim=self.sim)


if __name__ == '__main__':
    unittest.main()
