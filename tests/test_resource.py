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
Tests for Resource, Mutex, and ResourceMixin components.
'''
import unittest
from dssim import DSSimulation
from dssim.pubsub.components.resource import Resource, PriorityResource, DSResourcePreempted, Mutex, ResourceMixin


# ---------------------------------------------------------------------------
# SimResourceMixin factories
# ---------------------------------------------------------------------------

class TestSimResourceMixin(unittest.TestCase):

    def test1_resource_factory_returns_resource_instance(self):
        sim = DSSimulation()
        r = sim.resource(amount=2, capacity=3)
        self.assertIsInstance(r, Resource)
        self.assertIs(r.sim, sim)
        self.assertEqual(r.amount, 2)
        self.assertEqual(r.capacity, 3)

    def test2_priority_resource_factory_returns_priority_resource_instance(self):
        sim = DSSimulation()
        r = sim.priority_resource(amount=1, capacity=4)
        self.assertIsInstance(r, PriorityResource)
        self.assertIs(r.sim, sim)
        self.assertEqual(r.amount, 1)
        self.assertEqual(r.capacity, 4)

    def test3_factories_wrong_sim_raise(self):
        sim1 = DSSimulation()
        sim2 = DSSimulation()
        with self.assertRaises(ValueError):
            sim1.resource(sim=sim2)
        with self.assertRaises(ValueError):
            sim1.priority_resource(sim=sim2)


# ---------------------------------------------------------------------------
# Nowait variants (no simulation required)
# ---------------------------------------------------------------------------

class TestResourceNowait(unittest.TestCase):

    def setUp(self):
        self.sim = DSSimulation()
        self.r = Resource(amount=5, capacity=10, sim=self.sim)

    # ---- get_nowait / get_n_nowait -----------------------------------------

    def test1_get_nowait_takes_one(self):
        result = self.r.get_nowait()
        self.assertEqual(result, 1)
        self.assertEqual(self.r.amount, 4)

    def test2_get_nowait_fails_when_empty(self):
        r = Resource(amount=0, capacity=5, sim=self.sim)
        result = r.get_nowait()
        self.assertEqual(result, 0)
        self.assertEqual(r.amount, 0)

    def test3_get_n_nowait_takes_n(self):
        result = self.r.get_n_nowait(3)
        self.assertEqual(result, 3)
        self.assertEqual(self.r.amount, 2)

    def test4_get_n_nowait_fails_when_insufficient(self):
        result = self.r.get_n_nowait(6)
        self.assertEqual(result, 0)
        self.assertEqual(self.r.amount, 5)

    def test5_get_n_nowait_default_amount_is_one(self):
        result = self.r.get_n_nowait()
        self.assertEqual(result, 1)
        self.assertEqual(self.r.amount, 4)

    def test6_get_n_nowait_exact_available(self):
        result = self.r.get_n_nowait(5)
        self.assertEqual(result, 5)
        self.assertEqual(self.r.amount, 0)

    # ---- put_nowait / put_n_nowait -----------------------------------------

    def test7_put_nowait_adds_one(self):
        result = self.r.put_nowait()
        self.assertEqual(result, 1)
        self.assertEqual(self.r.amount, 6)

    def test8_put_nowait_fails_when_full(self):
        r = Resource(amount=10, capacity=10, sim=self.sim)
        result = r.put_nowait()
        self.assertEqual(result, 0)
        self.assertEqual(r.amount, 10)

    def test9_put_n_nowait_adds_n(self):
        result = self.r.put_n_nowait(3)
        self.assertEqual(result, 3)
        self.assertEqual(self.r.amount, 8)

    def test10_put_n_nowait_fails_when_would_exceed_capacity(self):
        result = self.r.put_n_nowait(6)
        self.assertEqual(result, 0)
        self.assertEqual(self.r.amount, 5)

    def test11_put_n_nowait_fills_exactly(self):
        result = self.r.put_n_nowait(5)
        self.assertEqual(result, 5)
        self.assertEqual(self.r.amount, 10)

    # ---- init validation ---------------------------------------------------

    def test12_init_amount_exceeds_capacity_raises(self):
        with self.assertRaises(ValueError):
            Resource(amount=10, capacity=5, sim=self.sim)

    def test13_infinite_capacity_default(self):
        r = Resource(sim=self.sim)
        self.assertEqual(r.amount, 0)
        self.assertEqual(r.capacity, float('inf'))

    def test14_put_n_nowait_large_amount_infinite_capacity(self):
        r = Resource(amount=0, sim=self.sim)
        result = r.put_n_nowait(1_000_000)
        self.assertEqual(result, 1_000_000)
        self.assertEqual(r.amount, 1_000_000)


# ---------------------------------------------------------------------------
# Blocking get — generator variants
# ---------------------------------------------------------------------------

class TestResourceGget(unittest.TestCase):

    def setUp(self):
        self.sim = DSSimulation()

    def _make(self, amount=0, capacity=float('inf')):
        return Resource(amount=amount, capacity=capacity, sim=self.sim)

    def test1_gget_takes_one_immediately(self):
        r = self._make(amount=3)
        results = []

        def consumer():
            result = yield from r.gget()
            results.append(result)

        self.sim.schedule(0, consumer())
        self.sim.run(5)
        self.assertEqual(results, [1])
        self.assertEqual(r.amount, 2)

    def test2_gget_blocks_until_available(self):
        r = self._make(amount=0)
        results = []

        def consumer():
            result = yield from r.gget()
            results.append(('got', self.sim.time, result))

        def producer():
            yield from self.sim.gwait(5)
            r.put_n_nowait(1)

        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(results, [('got', 5, 1)])
        self.assertEqual(r.amount, 0)

    def test3_gget_timeout(self):
        r = self._make(amount=0)
        results = []

        def consumer():
            result = yield from r.gget(timeout=3)
            results.append(result)

        self.sim.schedule(0, consumer())
        self.sim.run(10)
        self.assertEqual(results, [0])

    def test4_gget_n_takes_n_immediately(self):
        r = self._make(amount=5)
        results = []

        def consumer():
            result = yield from r.gget_n(amount=3)
            results.append(result)

        self.sim.schedule(0, consumer())
        self.sim.run(5)
        self.assertEqual(results, [3])
        self.assertEqual(r.amount, 2)

    def test5_gget_n_blocks_until_enough_available(self):
        r = self._make(amount=2)
        results = []

        def consumer():
            result = yield from r.gget_n(amount=5)
            results.append(('got', self.sim.time, result))

        def producer():
            yield from self.sim.gwait(4)
            r.put_n_nowait(3)   # now 5 available

        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(results, [('got', 4, 5)])
        self.assertEqual(r.amount, 0)

    def test6_gget_n_timeout(self):
        r = self._make(amount=1)
        results = []

        def consumer():
            result = yield from r.gget_n(timeout=3, amount=5)
            results.append(result)

        self.sim.schedule(0, consumer())
        self.sim.run(10)
        self.assertEqual(results, [0])
        self.assertEqual(r.amount, 1)  # unchanged

    def test7_gget_n_default_amount_is_one(self):
        r = self._make(amount=3)
        results = []

        def consumer():
            result = yield from r.gget_n()
            results.append(result)

        self.sim.schedule(0, consumer())
        self.sim.run(5)
        self.assertEqual(results, [1])
        self.assertEqual(r.amount, 2)

    def test8_multiple_gget_consumers_serialized(self):
        r = self._make(amount=0)
        order = []

        def consumer(name):
            result = yield from r.gget()
            order.append((name, self.sim.time))

        def producer():
            yield from self.sim.gwait(5)
            r.put_nowait()
            r.put_nowait()
            r.put_nowait()

        self.sim.schedule(0, consumer('c1'))
        self.sim.schedule(0, consumer('c2'))
        self.sim.schedule(0, consumer('c3'))
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(len(order), 3)
        for _, t in order:
            self.assertEqual(t, 5)


# ---------------------------------------------------------------------------
# PriorityResource waiter ordering
# ---------------------------------------------------------------------------

class TestPriorityResource(unittest.TestCase):

    def setUp(self):
        self.sim = DSSimulation()

    def _make(self, amount=0, capacity=float('inf')):
        return PriorityResource(amount=amount, capacity=capacity, sim=self.sim)

    def test1_gget_serves_higher_priority_first(self):
        r = self._make(amount=0, capacity=3)
        order = []

        def consumer(name, prio):
            result = yield from r.gget(priority=prio)
            order.append((name, result, self.sim.time))

        def producer():
            yield from self.sim.gwait(5)
            r.put_n_nowait(3)

        self.sim.schedule(0, consumer('low', 10))
        self.sim.schedule(0, consumer('high', 1))
        self.sim.schedule(0, consumer('mid', 5))
        self.sim.schedule(0, producer())
        self.sim.run(20)

        self.assertEqual([item[0] for item in order], ['high', 'mid', 'low'])
        self.assertTrue(all(item[1] == 1 for item in order))
        self.assertTrue(all(item[2] == 5 for item in order))

    def test2_equal_priority_keeps_fifo(self):
        r = self._make(amount=0, capacity=2)
        order = []

        def consumer(name):
            result = yield from r.gget(priority=3)
            order.append((name, result, self.sim.time))

        def producer():
            yield from self.sim.gwait(5)
            r.put_n_nowait(2)

        self.sim.schedule(0, consumer('c1'))
        self.sim.schedule(0, consumer('c2'))
        self.sim.schedule(0, producer())
        self.sim.run(20)

        self.assertEqual([item[0] for item in order], ['c1', 'c2'])
        self.assertTrue(all(item[1] == 1 for item in order))
        self.assertTrue(all(item[2] == 5 for item in order))

    def test3_preemptive_interrupts_lower_priority_holder(self):
        r = self._make(amount=1, capacity=1)
        log = []

        def low():
            got = yield from r.gget(priority=5, preempt=True)
            self.assertEqual(got, 1)
            log.append(('low_start', self.sim.time))
            try:
                yield from self.sim.gwait(10)
                log.append(('low_no_preempt', self.sim.time))
                r.put_nowait()
            except DSResourcePreempted as exc:
                log.append(('low_preempted', self.sim.time, exc.amount))
                got2 = yield from r.gget(priority=5, preempt=False)
                self.assertEqual(got2, 1)
                log.append(('low_resumed', self.sim.time))
                yield from self.sim.gwait(2)
                r.put_nowait()
                log.append(('low_done', self.sim.time))

        def high():
            yield from self.sim.gwait(3)
            got = yield from r.gget(priority=1, preempt=True)
            self.assertEqual(got, 1)
            log.append(('high_start', self.sim.time))
            yield from self.sim.gwait(2)
            r.put_nowait()
            log.append(('high_done', self.sim.time))

        self.sim.schedule(0, low())
        self.sim.schedule(0, high())
        self.sim.run(20)

        self.assertEqual(log, [
            ('low_start', 0),
            ('high_start', 3),
            ('low_preempted', 3, 1),
            ('high_done', 5),
            ('low_resumed', 5),
            ('low_done', 7),
        ])
        self.assertEqual(r.amount, 1)

    def test4_preempt_false_waits_without_interrupt(self):
        r = self._make(amount=1, capacity=1)
        log = []

        def low():
            got = yield from r.gget(priority=5, preempt=True)
            self.assertEqual(got, 1)
            log.append(('low_start', self.sim.time))
            yield from self.sim.gwait(4)
            r.put_nowait()
            log.append(('low_done', self.sim.time))

        def high():
            yield from self.sim.gwait(1)
            got = yield from r.gget(priority=1, preempt=False)
            self.assertEqual(got, 1)
            log.append(('high_start', self.sim.time))
            r.put_nowait()
            log.append(('high_done', self.sim.time))

        self.sim.schedule(0, low())
        self.sim.schedule(0, high())
        self.sim.run(20)

        self.assertEqual(log, [
            ('low_start', 0),
            ('low_done', 4),
            ('high_start', 4),
            ('high_done', 4),
        ])
        self.assertEqual(r.amount, 1)

    def test5_hold_context_autoreleases_on_normal_exit(self):
        r = self._make(amount=1, capacity=1)
        log = []

        def worker():
            with r.autorelease():
                got = yield from r.gget(priority=2)
                self.assertEqual(got, 1)
                log.append(('start', self.sim.time, r.amount))
                yield from self.sim.gwait(3)
                log.append(('end_scope', self.sim.time, r.amount))
            log.append(('after_scope', self.sim.time, r.amount))

        self.sim.schedule(0, worker())
        self.sim.run(20)
        self.assertEqual(log, [
            ('start', 0, 0),
            ('end_scope', 3, 0),
            ('after_scope', 3, 1),
        ])
        self.assertEqual(r.amount, 1)

    def test6_hold_context_autorelease_after_preemption(self):
        r = self._make(amount=1, capacity=1)
        log = []

        def low():
            with r.autorelease():
                got = yield from r.gget(priority=5, preempt=True)
                self.assertEqual(got, 1)
                log.append(('low_start', self.sim.time))
                try:
                    yield from self.sim.gwait(10)
                except DSResourcePreempted:
                    log.append(('low_preempted', self.sim.time))
            log.append(('low_after_scope', self.sim.time, r.amount))

        def high():
            yield from self.sim.gwait(3)
            with r.autorelease():
                got = yield from r.gget(priority=1, preempt=True)
                self.assertEqual(got, 1)
                log.append(('high_start', self.sim.time))
                yield from self.sim.gwait(2)
            log.append(('high_after_scope', self.sim.time, r.amount))

        self.sim.schedule(0, low())
        self.sim.schedule(0, high())
        self.sim.run(20)

        self.assertEqual(log, [
            ('low_start', 0),
            ('high_start', 3),
            ('low_preempted', 3),
            ('low_after_scope', 3, 0),
            ('high_after_scope', 5, 1),
        ])
        self.assertEqual(r.amount, 1)

    def test7_nested_resource_specific_preempted_catches(self):
        r0 = self._make(amount=1, capacity=1)
        r1 = self._make(amount=1, capacity=1)
        log = []

        self.assertIsNot(r0.Preempted, r1.Preempted)
        self.assertTrue(issubclass(r0.Preempted, DSResourcePreempted))
        self.assertTrue(issubclass(r1.Preempted, DSResourcePreempted))

        def nested_owner():
            try:
                with r0.autorelease():
                    got0 = yield from r0.gget(priority=5, preempt=True)
                    self.assertEqual(got0, 1)
                    try:
                        with r1.autorelease():
                            got1 = yield from r1.gget(priority=10, preempt=True)
                            self.assertEqual(got1, 1)
                            yield from self.sim.gwait(20)
                    except r1.Preempted:
                        log.append(('r1_preempted', self.sim.time))
                        yield from self.sim.gwait(20)
            except r0.Preempted:
                log.append(('r0_preempted', self.sim.time))

        def preempt_r1():
            yield from self.sim.gwait(3)
            with r1.autorelease():
                got = yield from r1.gget(priority=1, preempt=True)
                self.assertEqual(got, 1)
                yield from self.sim.gwait(1)

        def preempt_r0():
            yield from self.sim.gwait(6)
            with r0.autorelease():
                got = yield from r0.gget(priority=1, preempt=True)
                self.assertEqual(got, 1)
                yield from self.sim.gwait(1)

        self.sim.schedule(0, nested_owner())
        self.sim.schedule(0, preempt_r1())
        self.sim.schedule(0, preempt_r0())
        self.sim.run(20)

        self.assertEqual(log, [
            ('r1_preempted', 3),
            ('r0_preempted', 6),
        ])


# ---------------------------------------------------------------------------
# Resource take_cond condition helper
# ---------------------------------------------------------------------------

class TestResourceTakeCond(unittest.TestCase):

    def setUp(self):
        self.sim = DSSimulation()

    def test1_take_cond_acquires_on_nempty_signal(self):
        r = Resource(amount=0, capacity=1, sim=self.sim)
        out = []

        def consumer():
            cond = r.take_cond()
            with self.sim.consume(r.tx_nempty):
                got = yield from self.sim.gwait(10, cond=cond)
            out.append((self.sim.time, got))

        def producer():
            yield from self.sim.gwait(4)
            r.put_nowait()

        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)

        self.assertEqual(out, [(4, 1)])
        self.assertEqual(r.amount, 0)

    def test2_take_cond_check_and_gwait_precheck(self):
        r = Resource(amount=2, capacity=2, sim=self.sim)
        out = []

        def consumer():
            cond = r.take_cond(amount=2)
            got = yield from self.sim.check_and_gwait(10, cond=cond)
            out.append((self.sim.time, got))

        self.sim.schedule(0, consumer())
        self.sim.run(5)

        self.assertEqual(out, [(0, 2)])
        self.assertEqual(r.amount, 0)

    def test3_take_cond_composes_with_two_resources_via_dscircuit_without_consume(self):
        r0 = Resource(amount=0, capacity=1, sim=self.sim)
        r1 = Resource(amount=0, capacity=1, sim=self.sim)
        out = []

        def consumer():
            f0 = self.sim.filter(r0.take_cond())
            f1 = self.sim.filter(r1.take_cond())
            got = yield from (f0 & f1).check_and_gwait(20)
            out.append((self.sim.time, got))

        def producer():
            yield from self.sim.gwait(3)
            r0.put_nowait()
            yield from self.sim.gwait(2)
            r1.put_nowait()

        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(30)

        self.assertEqual(out[0][0], 5)
        self.assertEqual(set(out[0][1].values()), {r0.tx_nempty, r1.tx_nempty})
        self.assertEqual(r0.amount, 0)
        self.assertEqual(r1.amount, 0)

    def test4_priority_take_cond_supports_preempt(self):
        r = PriorityResource(amount=1, capacity=1, preemptive=True, sim=self.sim)
        out = []

        def low():
            got = yield from r.gget(priority=5, preempt=True)
            self.assertEqual(got, 1)
            out.append(('low_start', self.sim.time))
            try:
                yield from self.sim.gwait(10)
            except DSResourcePreempted:
                out.append(('low_preempted', self.sim.time))

        def high():
            yield from self.sim.gwait(3)
            cond = r.take_cond(priority=1, preempt=True)
            with self.sim.consume(r.tx_nempty):
                got = yield from self.sim.check_and_gwait(5, cond=cond)
            out.append(('high_got', self.sim.time, got))
            r.put_nowait()

        self.sim.schedule(0, low())
        self.sim.schedule(0, high())
        self.sim.run(20)

        self.assertEqual(out, [
            ('low_start', 0),
            ('high_got', 3, 1),
            ('low_preempted', 3),
        ])
        self.assertEqual(r.amount, 1)

    def test5_take_cond_composes_with_two_resources_async_without_consume(self):
        r0 = Resource(amount=0, capacity=1, sim=self.sim)
        r1 = Resource(amount=0, capacity=1, sim=self.sim)
        out = []
        filters = {}

        async def consumer():
            filters['f0'] = self.sim.filter(r0.take_cond())
            filters['f1'] = self.sim.filter(r1.take_cond())
            got = await (filters['f0'] | filters['f1']).check_and_wait(20)
            out.append((self.sim.time, got))

        async def producer():
            await self.sim.wait(4)
            r1.put_nowait()

        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(30)

        self.assertEqual(out, [(4, {filters['f1']: r1.tx_nempty})])
        self.assertEqual(r0.amount, 0)
        self.assertEqual(r1.amount, 0)


# ---------------------------------------------------------------------------
# Blocking get — async variants
# ---------------------------------------------------------------------------

class TestResourceAsyncGet(unittest.TestCase):

    def setUp(self):
        self.sim = DSSimulation()

    def _make(self, amount=0, capacity=float('inf')):
        return Resource(amount=amount, capacity=capacity, sim=self.sim)

    def test1_get_takes_one_immediately(self):
        r = self._make(amount=3)
        results = []

        async def consumer():
            result = await r.get()
            results.append(result)

        self.sim.schedule(0, consumer())
        self.sim.run(5)
        self.assertEqual(results, [1])
        self.assertEqual(r.amount, 2)

    def test2_get_blocks_until_available(self):
        r = self._make(amount=0)
        results = []

        async def consumer():
            result = await r.get()
            results.append(('got', self.sim.time, result))

        async def producer():
            await self.sim.wait(5)
            r.put_n_nowait(1)

        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(results, [('got', 5, 1)])

    def test3_get_timeout(self):
        r = self._make(amount=0)
        results = []

        async def consumer():
            result = await r.get(timeout=3)
            results.append(result)

        self.sim.schedule(0, consumer())
        self.sim.run(10)
        self.assertEqual(results, [0])

    def test4_get_n_takes_n_immediately(self):
        r = self._make(amount=5)
        results = []

        async def consumer():
            result = await r.get_n(amount=4)
            results.append(result)

        self.sim.schedule(0, consumer())
        self.sim.run(5)
        self.assertEqual(results, [4])
        self.assertEqual(r.amount, 1)

    def test5_get_n_blocks_until_enough(self):
        r = self._make(amount=2)
        results = []

        async def consumer():
            result = await r.get_n(amount=5)
            results.append(('got', self.sim.time, result))

        async def producer():
            await self.sim.wait(4)
            r.put_n_nowait(3)

        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(results, [('got', 4, 5)])

    def test6_get_n_timeout(self):
        r = self._make(amount=1)
        results = []

        async def consumer():
            result = await r.get_n(timeout=3, amount=5)
            results.append(result)

        self.sim.schedule(0, consumer())
        self.sim.run(10)
        self.assertEqual(results, [0])


# ---------------------------------------------------------------------------
# Blocking put — generator variants
# ---------------------------------------------------------------------------

class TestResourceGput(unittest.TestCase):

    def setUp(self):
        self.sim = DSSimulation()

    def _make(self, amount=0, capacity=10):
        return Resource(amount=amount, capacity=capacity, sim=self.sim)

    def test1_gput_adds_one_immediately(self):
        r = self._make(amount=5)
        results = []

        def producer():
            result = yield from r.gput()
            results.append(result)

        self.sim.schedule(0, producer())
        self.sim.run(5)
        self.assertEqual(results, [1])
        self.assertEqual(r.amount, 6)

    def test2_gput_blocks_when_full(self):
        r = self._make(amount=10, capacity=10)
        results = []

        def producer():
            result = yield from r.gput()
            results.append(('put', self.sim.time, result))

        def consumer():
            yield from self.sim.gwait(5)
            r.get_nowait()   # free space

        self.sim.schedule(0, producer())
        self.sim.schedule(0, consumer())
        self.sim.run(20)
        self.assertEqual(results, [('put', 5, 1)])
        self.assertEqual(r.amount, 10)

    def test3_gput_timeout(self):
        r = self._make(amount=10, capacity=10)
        results = []

        def producer():
            result = yield from r.gput(timeout=3)
            results.append(result)

        self.sim.schedule(0, producer())
        self.sim.run(10)
        self.assertEqual(results, [0])
        self.assertEqual(r.amount, 10)

    def test4_gput_n_adds_n_immediately(self):
        r = self._make(amount=3)
        results = []

        def producer():
            result = yield from r.gput_n(amount=4)
            results.append(result)

        self.sim.schedule(0, producer())
        self.sim.run(5)
        self.assertEqual(results, [4])
        self.assertEqual(r.amount, 7)

    def test5_gput_n_blocks_until_space(self):
        r = self._make(amount=8, capacity=10)
        results = []

        def producer():
            result = yield from r.gput_n(amount=5)  # needs 5 free slots, only 2 available
            results.append(('put', self.sim.time, result))

        def consumer():
            yield from self.sim.gwait(4)
            r.get_n_nowait(3)   # free 3 more slots (5 total free)

        self.sim.schedule(0, producer())
        self.sim.schedule(0, consumer())
        self.sim.run(20)
        self.assertEqual(results, [('put', 4, 5)])
        self.assertEqual(r.amount, 10)

    def test6_gput_n_timeout(self):
        r = self._make(amount=9, capacity=10)
        results = []

        def producer():
            result = yield from r.gput_n(timeout=3, amount=5)
            results.append(result)

        self.sim.schedule(0, producer())
        self.sim.run(10)
        self.assertEqual(results, [0])
        self.assertEqual(r.amount, 9)


# ---------------------------------------------------------------------------
# Blocking put — async variants
# ---------------------------------------------------------------------------

class TestResourceAsyncPut(unittest.TestCase):

    def setUp(self):
        self.sim = DSSimulation()

    def _make(self, amount=0, capacity=10):
        return Resource(amount=amount, capacity=capacity, sim=self.sim)

    def test1_put_adds_one_immediately(self):
        r = self._make(amount=5)
        results = []

        async def producer():
            result = await r.put()
            results.append(result)

        self.sim.schedule(0, producer())
        self.sim.run(5)
        self.assertEqual(results, [1])
        self.assertEqual(r.amount, 6)

    def test2_put_blocks_when_full(self):
        r = self._make(amount=10, capacity=10)
        results = []

        async def producer():
            result = await r.put()
            results.append(('put', self.sim.time, result))

        async def consumer():
            await self.sim.wait(5)
            r.get_nowait()

        self.sim.schedule(0, producer())
        self.sim.schedule(0, consumer())
        self.sim.run(20)
        self.assertEqual(results, [('put', 5, 1)])

    def test3_put_timeout(self):
        r = self._make(amount=10, capacity=10)
        results = []

        async def producer():
            result = await r.put(timeout=3)
            results.append(result)

        self.sim.schedule(0, producer())
        self.sim.run(10)
        self.assertEqual(results, [0])

    def test4_put_n_adds_n_immediately(self):
        r = self._make(amount=3)
        results = []

        async def producer():
            result = await r.put_n(amount=4)
            results.append(result)

        self.sim.schedule(0, producer())
        self.sim.run(5)
        self.assertEqual(results, [4])
        self.assertEqual(r.amount, 7)

    def test5_put_n_blocks_until_space(self):
        r = self._make(amount=8, capacity=10)
        results = []

        async def producer():
            result = await r.put_n(amount=5)
            results.append(('put', self.sim.time, result))

        async def consumer():
            await self.sim.wait(4)
            r.get_n_nowait(3)

        self.sim.schedule(0, producer())
        self.sim.schedule(0, consumer())
        self.sim.run(20)
        self.assertEqual(results, [('put', 4, 5)])

    def test6_put_n_timeout(self):
        r = self._make(amount=9, capacity=10)
        results = []

        async def producer():
            result = await r.put_n(timeout=3, amount=5)
            results.append(result)

        self.sim.schedule(0, producer())
        self.sim.run(10)
        self.assertEqual(results, [0])


# ---------------------------------------------------------------------------
# Interplay: get and put wake each other
# ---------------------------------------------------------------------------

class TestResourceInterplay(unittest.TestCase):

    def setUp(self):
        self.sim = DSSimulation()

    def test1_gget_woken_by_gput(self):
        r = Resource(amount=0, capacity=10, sim=self.sim)
        log = []

        def consumer():
            result = yield from r.gget_n(amount=3)
            log.append(('got', self.sim.time, result))

        def producer():
            yield from self.sim.gwait(5)
            yield from r.gput_n(amount=3)
            log.append(('put', self.sim.time))

        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(log[0], ('put', 5))
        self.assertEqual(log[1], ('got', 5, 3))

    def test2_gput_woken_by_gget(self):
        r = Resource(amount=10, capacity=10, sim=self.sim)
        log = []

        def producer():
            result = yield from r.gput_n(amount=5)
            log.append(('put', self.sim.time, result))

        def consumer():
            yield from self.sim.gwait(5)
            yield from r.gget_n(amount=5)
            log.append(('got', self.sim.time))

        self.sim.schedule(0, producer())
        self.sim.schedule(0, consumer())
        self.sim.run(20)
        self.assertEqual(log[0], ('got', 5))
        self.assertEqual(log[1], ('put', 5, 5))

    def test3_get_and_get_n_independent(self):
        '''get (1 unit) and get_n (N units) can coexist; each gets only what it asked for.'''
        r = Resource(amount=0, capacity=10, sim=self.sim)
        log = []

        def single():
            result = yield from r.gget()
            log.append(('single', self.sim.time, result))

        def multi():
            result = yield from r.gget_n(amount=3)
            log.append(('multi', self.sim.time, result))

        def producer():
            yield from self.sim.gwait(5)
            r.put_n_nowait(4)

        self.sim.schedule(0, single())
        self.sim.schedule(0, multi())
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(len(log), 2)
        totals = sum(entry[2] for entry in log)
        self.assertEqual(totals, 4)
        self.assertEqual(r.amount, 0)

    def test4_gget_waits_on_tx_nempty(self):
        r = Resource(amount=0, capacity=1, sim=self.sim)
        seen = {}

        def consumer():
            result = yield from r.gget(timeout=10)
            seen['result'] = result

        def probe_and_produce():
            # Let consumer subscribe and block.
            yield from self.sim.gwait(0)
            seen['nempty_sub'] = r.tx_nempty.has_subscribers()
            seen['nfull_sub'] = r.tx_nfull.has_subscribers()
            r.put_nowait()

        self.sim.schedule(0, consumer())
        self.sim.schedule(0, probe_and_produce())
        self.sim.run(20)

        self.assertTrue(seen.get('nempty_sub', False))
        self.assertFalse(seen.get('nfull_sub', True))
        self.assertEqual(seen.get('result'), 1)

    def test5_gput_waits_on_tx_nfull(self):
        r = Resource(amount=1, capacity=1, sim=self.sim)
        seen = {}

        def producer():
            result = yield from r.gput(timeout=10)
            seen['result'] = result

        def probe_and_consume():
            # Let producer subscribe and block.
            yield from self.sim.gwait(0)
            seen['nempty_sub'] = r.tx_nempty.has_subscribers()
            seen['nfull_sub'] = r.tx_nfull.has_subscribers()
            r.get_nowait()

        self.sim.schedule(0, producer())
        self.sim.schedule(0, probe_and_consume())
        self.sim.run(20)

        self.assertFalse(seen.get('nempty_sub', True))
        self.assertTrue(seen.get('nfull_sub', False))
        self.assertEqual(seen.get('result'), 1)


# ---------------------------------------------------------------------------
# Mutex
# ---------------------------------------------------------------------------

class TestMutex(unittest.TestCase):

    def setUp(self):
        self.sim = DSSimulation()

    def _make(self):
        return Mutex(sim=self.sim)

    def test1_initial_state_unlocked(self):
        m = self._make()
        self.assertFalse(m.locked())
        self.assertEqual(m.amount, 1)

    def test2_lock_and_release(self):
        m = self._make()
        results = []

        async def process():
            retval = await m.lock()
            results.append(('locked', retval))
            await self.sim.wait(5)
            m.release()
            results.append(('released', self.sim.time))

        self.sim.schedule(0, process())
        self.sim.run(10)
        self.assertEqual(results[0], ('locked', 1))
        self.assertEqual(results[1], ('released', 5))
        self.assertFalse(m.locked())

    def test3_second_lock_blocks(self):
        m = self._make()
        log = []

        async def first():
            await m.lock()
            log.append(('first locked', self.sim.time))
            await self.sim.wait(5)
            m.release()

        async def second():
            await self.sim.wait(1)
            await m.lock()
            log.append(('second locked', self.sim.time))

        self.sim.schedule(0, first())
        self.sim.schedule(0, second())
        self.sim.run(20)
        self.assertEqual(log[0], ('first locked', 0))
        self.assertEqual(log[1], ('second locked', 5))

    def test4_lock_timeout(self):
        m = self._make()
        results = []

        async def holder():
            await m.lock()
            await self.sim.wait(10)
            m.release()

        async def waiter():
            await self.sim.wait(1)
            retval = await m.lock(timeout=3)
            results.append(retval)

        self.sim.schedule(0, holder())
        self.sim.schedule(0, waiter())
        self.sim.run(20)
        self.assertEqual(results, [0])  # timed out

    def test5_release_when_not_locked_is_noop(self):
        m = self._make()
        self.assertFalse(m.locked())
        m.release()   # should not raise or change state
        self.assertFalse(m.locked())

    def test6_open_returns_context_wrapper(self):
        m = self._make()
        cm = m.open(5)
        self.assertIsNot(cm, m)
        self.assertTrue(hasattr(cm, '__aenter__'))
        self.assertTrue(hasattr(cm, '__aexit__'))

    def test7_async_with_open_acquires_and_releases(self):
        m = self._make()
        log = []

        async def worker():
            async with m.open(10) as event:
                log.append(('entered', self.sim.time, event, m.locked()))
                await self.sim.wait(3)
                log.append(('inside', self.sim.time, m.locked()))
            log.append(('after', self.sim.time, m.locked()))

        self.sim.schedule(0, worker())
        self.sim.run(20)
        self.assertEqual(log, [
            ('entered', 0, 1, True),
            ('inside', 3, True),
            ('after', 3, False),
        ])


# ---------------------------------------------------------------------------
# ResourceStatsProbe
# ---------------------------------------------------------------------------

class TestResourceStatsProbe(unittest.TestCase):

    def setUp(self):
        self.sim = DSSimulation()

    def test0_stats_probe_name(self):
        r = Resource(amount=0, capacity=2, name='r0', sim=self.sim)
        probe = r.add_stats_probe()
        self.assertEqual(probe.name, 'r0.stats_probe')
        probe2 = r.add_stats_probe(name='ops')
        self.assertEqual(probe2.name, 'r0.ops')

    def test1_stats_probe_counts(self):
        r = Resource(amount=0, capacity=1, sim=self.sim)
        probe = r.add_stats_probe()

        def actor():
            r.put_nowait()
            yield from self.sim.gwait(1)
            r.put_n_nowait(2)  # full -> fail (no nempty signal)
            yield from self.sim.gwait(1)
            r.get_nowait()

        self.sim.schedule(0, actor())
        self.sim.run(10)

        stats = probe.stats()
        self.assertEqual(stats['put_count'], 1)
        self.assertEqual(stats['get_count'], 1)
        self.assertEqual(stats['max_amount'], 1.0)
        self.assertEqual(stats['min_amount'], 0.0)
        self.assertEqual(stats['current_amount'], 0.0)

    def test2_stats_probe_time_weighted_amount(self):
        r = Resource(amount=0, capacity=2, sim=self.sim)
        probe = r.add_stats_probe()

        def actor():
            r.put_nowait()      # t=0, amount=1
            yield from self.sim.gwait(3)
            r.put_nowait()      # t=3, amount=2
            yield from self.sim.gwait(2)
            r.get_nowait()      # t=5, amount=1
            yield from self.sim.gwait(5)
            r.get_nowait()      # t=10, amount=0

        self.sim.schedule(0, actor())
        self.sim.run(10)

        stats = probe.get_statistics()
        self.assertEqual(stats['duration'], 10)
        self.assertAlmostEqual(stats['time_avg_amount'], 1.2, places=6)
        self.assertAlmostEqual(stats['time_nonempty_ratio'], 1.0, places=6)
        self.assertAlmostEqual(stats['time_full_ratio'], 0.2, places=6)
        self.assertEqual(stats['max_amount'], 2.0)
        self.assertEqual(stats['min_amount'], 0.0)

    def test3_stats_probe_reset(self):
        r = Resource(amount=0, capacity=2, sim=self.sim)
        probe = r.add_stats_probe()
        r.put_nowait()
        self.sim.run(5)
        before_reset = probe.stats()
        self.assertAlmostEqual(before_reset['time_avg_amount'], 1.0, places=6)

        probe.reset()
        r.get_nowait()
        self.sim.run(10)
        after_reset = probe.stats()
        self.assertEqual(after_reset['duration'], 5)
        self.assertAlmostEqual(after_reset['time_avg_amount'], 0.0, places=6)
        self.assertEqual(after_reset['put_count'], 0)
        self.assertEqual(after_reset['get_count'], 1)


# ---------------------------------------------------------------------------
# ResourceMixin
# ---------------------------------------------------------------------------

class TestResourceMixin(unittest.TestCase):
    '''ResourceMixin delegates to the underlying Resource methods.
    Tested using plain ResourceMixin() instances with standalone generators
    and coroutines to avoid DSAgent singleton name collisions.
    '''

    def setUp(self):
        self.sim = DSSimulation()

    def _make_resource(self, amount=5, capacity=10):
        return Resource(amount=amount, capacity=capacity, sim=self.sim)

    def test1_gget_takes_one(self):
        r = self._make_resource(amount=3)
        mixin = ResourceMixin()
        results = []

        def consumer():
            result = yield from mixin.gget(r)
            results.append(result)

        self.sim.schedule(0, consumer())
        self.sim.run(5)
        self.assertEqual(results, [1])
        self.assertEqual(r.amount, 2)

    def test2_gget_n_takes_n(self):
        r = self._make_resource(amount=5)
        mixin = ResourceMixin()
        results = []

        def consumer():
            result = yield from mixin.gget_n(r, amount=3)
            results.append(result)

        self.sim.schedule(0, consumer())
        self.sim.run(5)
        self.assertEqual(results, [3])
        self.assertEqual(r.amount, 2)

    def test3_gput_adds_one(self):
        r = self._make_resource(amount=5)
        mixin = ResourceMixin()
        results = []

        def producer():
            result = yield from mixin.gput(r)
            results.append(result)

        self.sim.schedule(0, producer())
        self.sim.run(5)
        self.assertEqual(results, [1])
        self.assertEqual(r.amount, 6)

    def test4_gput_n_adds_n(self):
        r = self._make_resource(amount=2)
        mixin = ResourceMixin()
        results = []

        def producer():
            result = yield from mixin.gput_n(r, amount=4)
            results.append(result)

        self.sim.schedule(0, producer())
        self.sim.run(5)
        self.assertEqual(results, [4])
        self.assertEqual(r.amount, 6)

    def test5_put_nowait_adds_one(self):
        r = self._make_resource(amount=5)
        mixin = ResourceMixin()
        mixin.put_nowait(r)
        self.assertEqual(r.amount, 6)

    def test6_put_n_nowait_adds_n(self):
        r = self._make_resource(amount=2)
        mixin = ResourceMixin()
        mixin.put_n_nowait(r, 3)
        self.assertEqual(r.amount, 5)

    def test7_async_get(self):
        r = self._make_resource(amount=3)
        mixin = ResourceMixin()
        results = []

        async def consumer():
            result = await mixin.get(r)
            results.append(result)

        self.sim.schedule(0, consumer())
        self.sim.run(5)
        self.assertEqual(results, [1])
        self.assertEqual(r.amount, 2)

    def test8_async_get_n(self):
        r = self._make_resource(amount=5)
        mixin = ResourceMixin()
        results = []

        async def consumer():
            result = await mixin.get_n(r, amount=3)
            results.append(result)

        self.sim.schedule(0, consumer())
        self.sim.run(5)
        self.assertEqual(results, [3])
        self.assertEqual(r.amount, 2)

    def test9_async_put(self):
        r = self._make_resource(amount=5)
        mixin = ResourceMixin()
        results = []

        async def producer():
            result = await mixin.put(r)
            results.append(result)

        self.sim.schedule(0, producer())
        self.sim.run(5)
        self.assertEqual(results, [1])
        self.assertEqual(r.amount, 6)

    def test10_async_put_n(self):
        r = self._make_resource(amount=2)
        mixin = ResourceMixin()
        results = []

        async def producer():
            result = await mixin.put_n(r, amount=4)
            results.append(result)

        self.sim.schedule(0, producer())
        self.sim.run(5)
        self.assertEqual(results, [4])
        self.assertEqual(r.amount, 6)


if __name__ == '__main__':
    unittest.main()
