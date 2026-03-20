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
Tests for DSQueue component.
'''
import unittest
from dssim import DSSimulation, DSQueue
from dssim.base_components import DSBaseOrder, DSLifoOrder, DSKeyOrder

# ---------------------------------------------------------------------------
# SimQueueMixin factory
# ---------------------------------------------------------------------------

class TestSimQueueMixin(unittest.TestCase):

    def test1_queue_factory_returns_queue_instance(self):
        sim = DSSimulation()
        q = sim.queue(capacity=3)
        self.assertIsInstance(q, DSQueue)
        self.assertIs(q.sim, sim)
        self.assertEqual(q.capacity, 3)

    def test2_queue_factory_wrong_sim_raises(self):
        sim1 = DSSimulation()
        sim2 = DSSimulation()
        with self.assertRaises(ValueError):
            sim1.queue(sim=sim2)


# ---------------------------------------------------------------------------
# DSQueue component tests (requires DSSimulation)
# ---------------------------------------------------------------------------

class TestQueue(unittest.TestCase):

    def setUp(self):
        self.sim = DSSimulation()

    # ---- put_nowait / get_nowait -------------------------------------------

    def test1_put_nowait_and_get_nowait_basic(self):
        q = DSQueue(sim=self.sim)
        result = q.put_nowait('item')
        self.assertIsNotNone(result)
        self.assertEqual(len(q), 1)
        items = q.get_n_nowait()
        self.assertEqual(items, ['item'])
        self.assertEqual(len(q), 0)

    def test2_put_nowait_multiple(self):
        q = DSQueue(sim=self.sim)
        q.put_nowait('a', 'b', 'c')
        self.assertEqual(len(q), 3)
        self.assertEqual(q.get_n_nowait(), ['a'])
        self.assertEqual(q.get_n_nowait(), ['b'])
        self.assertEqual(q.get_n_nowait(), ['c'])

    def test3_put_nowait_full_returns_none(self):
        q = DSQueue(capacity=2, sim=self.sim)
        q.put_nowait('a', 'b')
        result = q.put_nowait('c')
        self.assertIsNone(result)
        self.assertEqual(len(q), 2)

    def test4_get_nowait_empty_returns_none(self):
        q = DSQueue(sim=self.sim)
        result = q.get_n_nowait()
        self.assertIsNone(result)

    def test5_get_nowait_amount(self):
        q = DSQueue(sim=self.sim)
        q.put_nowait('a', 'b', 'c')
        items = q.get_n_nowait(amount=2)
        self.assertEqual(items, ['a', 'b'])
        self.assertEqual(len(q), 1)

    def test6_get_nowait_cond_head(self):
        q = DSQueue(sim=self.sim)
        q.put_nowait('skip')
        result = q.get_n_nowait(cond=lambda e: e != 'skip')
        self.assertIsNone(result)   # head doesn't pass cond
        result = q.get_n_nowait(cond=lambda e: e == 'skip')
        self.assertEqual(result, ['skip'])

    # ---- fifo ordering -----------------------------------------------------

    def test7_fifo_order(self):
        q = DSQueue(sim=self.sim)
        for i in range(5):
            q.put_nowait(i)
        for i in range(5):
            self.assertEqual(q.get_n_nowait(), [i])

    # ---- capacity ----------------------------------------------------------

    def test8_infinite_capacity_default(self):
        q = DSQueue(sim=self.sim)
        for i in range(1000):
            self.assertIsNotNone(q.put_nowait(i))
        self.assertEqual(len(q), 1000)

    def test9_capacity_enforced(self):
        q = DSQueue(capacity=3, sim=self.sim)
        self.assertIsNotNone(q.put_nowait(1))
        self.assertIsNotNone(q.put_nowait(2))
        self.assertIsNotNone(q.put_nowait(3))
        self.assertIsNone(q.put_nowait(4))

    # ---- sequence protocol -------------------------------------------------

    def test10_getitem_setitem(self):
        q = DSQueue(sim=self.sim)
        q.put_nowait('x')
        self.assertEqual(q[0], 'x')
        q[0] = 'y'
        self.assertEqual(q[0], 'y')

    def test11_iter(self):
        q = DSQueue(sim=self.sim)
        q.put_nowait('a', 'b', 'c')
        self.assertEqual(list(q), ['a', 'b', 'c'])

    def test12_contains(self):
        q = DSQueue(sim=self.sim)
        q.put_nowait('needle')
        self.assertIn('needle', q)
        self.assertNotIn('haystack', q)

    # ---- pop ---------------------------------------------------------------

    def test13_pop_head(self):
        q = DSQueue(sim=self.sim)
        q.put_nowait('a', 'b', 'c')
        self.assertEqual(q.pop(0), 'a')
        self.assertEqual(list(q), ['b', 'c'])

    def test14_pop_middle(self):
        q = DSQueue(sim=self.sim)
        q.put_nowait('a', 'b', 'c')
        self.assertEqual(q.pop(1), 'b')
        self.assertEqual(list(q), ['a', 'c'])

    def test15_pop_out_of_range(self):
        q = DSQueue(sim=self.sim)
        q.put_nowait('a')
        self.assertIsNone(q.pop(5))
        self.assertIs(q.pop(5, 'default'), 'default')

    # ---- remove ------------------------------------------------------------

    def test16_remove_exact_item(self):
        q = DSQueue(sim=self.sim)
        obj = object()
        q.put_nowait(obj)
        q.put_nowait('other')
        q.remove(obj)
        self.assertNotIn(obj, q)
        self.assertEqual(len(q), 1)

    def test17_remove_callable_cond(self):
        q = DSQueue(sim=self.sim)
        q.put_nowait(1, 2, 3, 4)
        q.remove(lambda e: e % 2 == 0)
        self.assertEqual(list(q), [1, 3])

    def test18_remove_no_match_is_noop(self):
        q = DSQueue(sim=self.sim)
        q.put_nowait('a', 'b')
        q.remove('z')
        self.assertEqual(len(q), 2)

    # ---- blocking get / put via simulation ---------------------------------

    def test19_gget_blocks_until_item_available(self):
        '''getter waits for item; producer adds it at t=5.'''
        results = []

        def consumer():
            items = yield from q.gget_n()
            results.append(('got', self.sim.time, items))

        def producer():
            yield from self.sim.gwait(5)
            q.put_nowait('hello')

        q = DSQueue(sim=self.sim)
        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], ('got', 5, ['hello']))

    def test20_gput_blocks_until_space_available(self):
        '''putter waits for space; consumer gets at t=5.'''
        results = []

        def producer():
            q.put_nowait('first')  # fill the queue
            retval = yield from q.gput(float('inf'), 'second')
            results.append(('put', self.sim.time, retval))

        def consumer():
            yield from self.sim.gwait(5)
            items = q.get_n_nowait()  # free up space
            results.append(('got', self.sim.time, items))

        q = DSQueue(capacity=1, sim=self.sim)
        self.sim.schedule(0, producer())
        self.sim.schedule(0, consumer())
        self.sim.run(20)
        self.assertEqual(results[0], ('got', 5, ['first']))
        self.assertEqual(results[1][0], 'put')
        self.assertEqual(results[1][1], 5)

    def test21_gget_with_cond(self):
        '''getter only wakes when head item satisfies cond.'''
        results = []

        def consumer():
            items = yield from q.gget_n(cond=lambda e: e == 'wanted')
            results.append(items)

        def producer():
            yield from self.sim.gwait(2)
            q.put_nowait('skip')   # doesn't satisfy cond for this consumer
            yield from self.sim.gwait(2)
            q.put_nowait('wanted')

        q = DSQueue(sim=self.sim)
        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)
        # Consumer should have gotten 'wanted' (it was the head when cond passed)
        # but 'skip' would be at head at t=2... so consumer stays blocked until
        # 'wanted' arrives at t=4 and skip is now head... actually with FIFO,
        # 'skip' is still at head at t=4. So consumer gets 'skip' only if cond
        # passes for 'skip'. Since cond checks head item, consumer stays blocked.
        # At t=4, 'wanted' is added but 'skip' is still head. Consumer still
        # blocked. This shows the FIFO-with-cond semantics.
        self.assertEqual(results, [])  # cond never passes for head='skip'

    def test22_gget_timeout(self):
        '''getter times out when no item arrives in time.'''
        results = []

        def consumer():
            items = yield from q.gget_n(timeout=3)
            results.append(items)

        q = DSQueue(sim=self.sim)
        self.sim.schedule(0, consumer())
        self.sim.run(10)
        self.assertEqual(results, [None])

    def test23_gput_timeout(self):
        '''putter times out when no space becomes available in time.'''
        results = []

        def producer():
            q.put_nowait('first')
            retval = yield from q.gput(3, 'second')
            results.append(retval)

        q = DSQueue(capacity=1, sim=self.sim)
        self.sim.schedule(0, producer())
        self.sim.run(10)
        self.assertEqual(results, [None])

    def test24_multiple_consumers_fifo_wakeup(self):
        '''multiple waiting consumers get items in order.'''
        order = []

        def consumer(name):
            yield from q.gget_n()
            order.append((name, self.sim.time))

        def producer():
            yield from self.sim.gwait(5)
            q.put_nowait('i1')
            q.put_nowait('i2')
            q.put_nowait('i3')

        q = DSQueue(sim=self.sim)
        self.sim.schedule(0, consumer('c1'))
        self.sim.schedule(0, consumer('c2'))
        self.sim.schedule(0, consumer('c3'))
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(len(order), 3)
        # all wake at t=5
        for name, t in order:
            self.assertEqual(t, 5)

    # ---- gwait / wait / check_and_gwait / check_and_wait on DSQueue ----------

    def test25_queue_gwait_membership(self):
        '''gwait wakes when condition passes after a change.'''
        results = []

        obj = object()

        def watcher():
            event = yield from q.gwait(cond=lambda e: obj not in q)
            results.append(('removed', self.sim.time))

        def actor():
            q.put_nowait(obj)
            yield from self.sim.gwait(3)
            q.remove(obj)

        q = DSQueue(sim=self.sim)
        self.sim.schedule(0, actor())
        self.sim.schedule(0, watcher())
        self.sim.run(10)
        self.assertEqual(results, [('removed', 3)])

    def test26_queue_gwait_woken_by_put_nowait(self):
        '''put_nowait fires tx_changed, waking gwait.'''
        results = []

        def watcher():
            yield from q.gwait(cond=lambda e: len(q) > 0)
            results.append(self.sim.time)

        def actor():
            yield from self.sim.gwait(4)
            q.put_nowait('wake')

        q = DSQueue(sim=self.sim)
        self.sim.schedule(0, watcher())
        self.sim.schedule(0, actor())
        self.sim.run(10)
        self.assertEqual(results, [4])

    def test27_queue_gwait_woken_by_get_nowait(self):
        '''get_nowait fires tx_changed, waking gwait.'''
        results = []

        def watcher():
            q.put_nowait('item')
            yield from q.gwait(cond=lambda e: len(q) == 0)
            results.append(self.sim.time)

        def actor():
            yield from self.sim.gwait(3)
            q.get_n_nowait()

        q = DSQueue(sim=self.sim)
        self.sim.schedule(0, watcher())
        self.sim.schedule(0, actor())
        self.sim.run(10)
        self.assertEqual(results, [3])

    # ---- async (coroutine) variants ----------------------------------------

    def test28_async_get_and_put(self):
        results = []

        async def consumer():
            items = await q.get_n()
            results.append(('got', self.sim.time, items))

        async def producer():
            await self.sim.wait(4)
            q.put_nowait('async_item')

        q = DSQueue(sim=self.sim)
        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(results, [('got', 4, ['async_item'])])


# ---------------------------------------------------------------------------
# DSQueue condition helpers
# ---------------------------------------------------------------------------

class TestQueueCondHelpers(unittest.TestCase):

    def setUp(self):
        self.sim = DSSimulation()

    def test1_get_cond_acquires_on_nempty_signal(self):
        q = DSQueue(sim=self.sim)
        out = []
        seen = []

        def consumer():
            cond = q.get_cond()
            got = yield from cond.gwait(10)
            out.append((self.sim.time, got))

        def watcher():
            yield from self.sim.gwait(1)
            seen.append(q.tx_nempty.has_subscribers())

        def producer():
            yield from self.sim.gwait(4)
            q.put_nowait('hello')

        self.sim.schedule(0, consumer())
        self.sim.schedule(0, watcher())
        self.sim.schedule(0, producer())
        self.sim.run(20)

        self.assertEqual(out, [(4, 'hello')])
        self.assertEqual(seen, [True])
        self.assertEqual(len(q), 0)

    def test2_get_cond_check_and_gwait_precheck(self):
        q = DSQueue(sim=self.sim)
        q.put_nowait('a', 'b')
        out = []

        def consumer():
            cond = q.get_cond(amount=2)
            got = yield from self.sim.check_and_gwait(10, cond=cond)
            out.append((self.sim.time, got))

        self.sim.schedule(0, consumer())
        self.sim.run(5)

        self.assertEqual(out, [(0, ['a', 'b'])])
        self.assertEqual(len(q), 0)

    def test3_get_cond_composes_with_two_queues_via_dscircuit_without_consume(self):
        q0 = DSQueue(sim=self.sim)
        q1 = DSQueue(sim=self.sim)
        out = []

        def consumer():
            f0 = self.sim.filter(q0.get_cond())
            f1 = self.sim.filter(q1.get_cond())
            got = yield from (f0 & f1).check_and_gwait(20)
            out.append((self.sim.time, got))

        def producer():
            yield from self.sim.gwait(3)
            q0.put_nowait('x')
            yield from self.sim.gwait(2)
            q1.put_nowait('y')

        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(30)

        self.assertEqual(out[0][0], 5)
        self.assertEqual(set(out[0][1].values()), {q0.tx_nempty, q1.tx_nempty})
        self.assertEqual(len(q0), 0)
        self.assertEqual(len(q1), 0)

    def test4_get_cond_conditional_head_uses_tx_changed(self):
        q = DSQueue(sim=self.sim)
        out = []
        cond = q.get_cond(cond=lambda e: e == 'wanted')

        def consumer():
            got = yield from cond.check_and_gwait(20)
            out.append((self.sim.time, got))

        def producer():
            yield from self.sim.gwait(1)
            q.put_nowait('skip')
            yield from self.sim.gwait(1)
            q.put_nowait('wanted')
            yield from self.sim.gwait(1)
            q.get_nowait()  # remove "skip", so "wanted" becomes head

        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(30)

        self.assertEqual(out, [(3, 'wanted')])
        self.assertEqual(len(q), 0)

    def test5_put_cond_acquires_on_nfull_signal(self):
        q = DSQueue(capacity=1, sim=self.sim)
        q.put_nowait('first')
        out = []
        seen = []

        def putter():
            cond = q.put_cond('second')
            got = yield from cond.gwait(10)
            out.append((self.sim.time, got))

        def watcher():
            yield from self.sim.gwait(1)
            seen.append(q.tx_nfull.has_subscribers())

        def consumer():
            yield from self.sim.gwait(4)
            q.get_nowait()  # frees one slot and triggers tx_nfull

        self.sim.schedule(0, putter())
        self.sim.schedule(0, watcher())
        self.sim.schedule(0, consumer())
        self.sim.run(20)

        self.assertEqual(out, [(4, ('second',))])
        self.assertEqual(seen, [True])
        self.assertEqual(list(q), ['second'])

    def test6_put_cond_check_and_gwait_precheck(self):
        q = DSQueue(capacity=2, sim=self.sim)
        out = []

        def putter():
            cond = q.put_cond('x')
            got = yield from self.sim.check_and_gwait(10, cond=cond)
            out.append((self.sim.time, got))

        self.sim.schedule(0, putter())
        self.sim.run(5)

        self.assertEqual(out, [(0, ('x',))])
        self.assertEqual(list(q), ['x'])

    def test7_change_cond_checks_queue_state_on_tx_changed(self):
        q = DSQueue(sim=self.sim)
        out = []
        cond = q.change_cond(cond=lambda qq: len(qq) >= 2)

        def watcher():
            got = yield from cond.check_and_gwait(20)
            out.append((self.sim.time, got))

        def producer():
            yield from self.sim.gwait(2)
            q.put_nowait('a')
            yield from self.sim.gwait(1)
            q.put_nowait('b')

        self.sim.schedule(0, watcher())
        self.sim.schedule(0, producer())
        self.sim.run(30)

        self.assertEqual(out, [(3, q.tx_changed)])
        self.assertEqual(list(q), ['a', 'b'])


# ---------------------------------------------------------------------------
# DSQueue with DSLifoOrder policy
# ---------------------------------------------------------------------------

class TestQueueLifo(unittest.TestCase):

    def setUp(self):
        self.sim = DSSimulation()

    def test1_lifo_order_nowait(self):
        q = DSQueue(policy=DSLifoOrder(), sim=self.sim)
        q.put_nowait('a')
        q.put_nowait('b')
        q.put_nowait('c')
        self.assertEqual(q.get_n_nowait(), ['c'])
        self.assertEqual(q.get_n_nowait(), ['b'])
        self.assertEqual(q.get_n_nowait(), ['a'])

    def test2_buffer_is_dslifoqueue(self):
        q = DSQueue(policy=DSLifoOrder(), sim=self.sim)
        self.assertIsInstance(q._buffer, DSLifoOrder)

    def test3_fifo_is_default(self):
        q = DSQueue(sim=self.sim)
        self.assertIsInstance(q._buffer, DSBaseOrder)
        self.assertNotIsInstance(q._buffer, DSLifoOrder)

    def test4_lifo_blocking_gget(self):
        '''LIFO queue gives last-added item to a waiting consumer.'''
        results = []

        def consumer():
            items = yield from q.gget_n()
            results.append(items)

        def producer():
            yield from self.sim.gwait(3)
            q.put_nowait('first')
            q.put_nowait('second')

        q = DSQueue(policy=DSLifoOrder(), sim=self.sim)
        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(10)
        self.assertEqual(results, [['second']])


# ---------------------------------------------------------------------------
# Single-item API: get_nowait / gget / get
# ---------------------------------------------------------------------------

class TestQueueSingleItemGet(unittest.TestCase):
    '''
    DSQueue.get_nowait() / .gget() / .get() return a single element (not
    wrapped in a list), in contrast to get_n_nowait / gget_n / get_n which
    always return a list.
    '''

    def setUp(self):
        self.sim = DSSimulation()

    # ---- get_nowait --------------------------------------------------------

    def test1_get_nowait_returns_single_element(self):
        q = DSQueue(sim=self.sim)
        q.put_nowait('A')
        result = q.get_nowait()
        self.assertEqual(result, 'A')
        self.assertNotIsInstance(result, list)
        self.assertEqual(len(q), 0)

    def test2_get_nowait_returns_none_when_empty(self):
        q = DSQueue(sim=self.sim)
        result = q.get_nowait()
        self.assertIsNone(result)

    def test3_get_nowait_fifo_order(self):
        q = DSQueue(sim=self.sim)
        q.put_nowait('first', 'second', 'third')
        self.assertEqual(q.get_nowait(), 'first')
        self.assertEqual(q.get_nowait(), 'second')
        self.assertEqual(q.get_nowait(), 'third')

    def test4_get_nowait_with_passing_cond(self):
        q = DSQueue(sim=self.sim)
        q.put_nowait('match')
        result = q.get_nowait(cond=lambda e: e == 'match')
        self.assertEqual(result, 'match')

    def test5_get_nowait_with_failing_cond_returns_none(self):
        q = DSQueue(sim=self.sim)
        q.put_nowait('item')
        result = q.get_nowait(cond=lambda e: e == 'other')
        self.assertIsNone(result)
        self.assertEqual(len(q), 1)  # item still in queue

    def test6_get_nowait_vs_get_n_nowait_return_types(self):
        q = DSQueue(sim=self.sim)
        q.put_nowait('a')
        q.put_nowait('b')
        single = q.get_nowait()
        listed = q.get_n_nowait()
        self.assertNotIsInstance(single, list)
        self.assertIsInstance(listed, list)

    # ---- gget ---------------------------------------------------------------

    def test7_gget_returns_single_element_immediately(self):
        results = []

        def consumer():
            item = yield from q.gget()
            results.append(item)

        q = DSQueue(sim=self.sim)
        q.put_nowait('hello')
        self.sim.schedule(0, consumer())
        self.sim.run(5)
        self.assertEqual(results, ['hello'])
        self.assertNotIsInstance(results[0], list)

    def test8_gget_blocks_until_item_available(self):
        results = []

        def consumer():
            item = yield from q.gget()
            results.append(('got', self.sim.time, item))

        def producer():
            yield from self.sim.gwait(5)
            q.put_nowait('deferred')

        q = DSQueue(sim=self.sim)
        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(results, [('got', 5, 'deferred')])

    def test9_gget_timeout_returns_none(self):
        results = []

        def consumer():
            item = yield from q.gget(timeout=3)
            results.append(item)

        q = DSQueue(sim=self.sim)
        self.sim.schedule(0, consumer())
        self.sim.run(10)
        self.assertEqual(results, [None])

    def test10_gget_with_cond(self):
        '''gget wakes only when head satisfies cond.'''
        results = []

        def consumer():
            item = yield from q.gget(cond=lambda e: e == 'wanted')
            results.append(item)

        def producer():
            yield from self.sim.gwait(2)
            q.put_nowait('skip')
            yield from self.sim.gwait(2)
            # remove 'skip' first so 'wanted' becomes head
            q.get_nowait()
            q.put_nowait('wanted')

        q = DSQueue(sim=self.sim)
        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(results, ['wanted'])

    def test11_gget_vs_gget_n_different_return_types(self):
        results_single = []
        results_list = []

        def single_consumer():
            item = yield from q.gget()
            results_single.append(item)

        def list_consumer():
            items = yield from q.gget_n()
            results_list.append(items)

        q = DSQueue(sim=self.sim)
        q.put_nowait('x')
        q.put_nowait('y')
        self.sim.schedule(0, single_consumer())
        self.sim.schedule(0, list_consumer())
        self.sim.run(5)
        self.assertNotIsInstance(results_single[0], list)
        self.assertIsInstance(results_list[0], list)

    def test12_multiple_gget_consumers_each_get_one(self):
        order = []

        def consumer(name):
            item = yield from q.gget()
            order.append((name, self.sim.time, item))

        def producer():
            yield from self.sim.gwait(5)
            q.put_nowait('i1')
            q.put_nowait('i2')
            q.put_nowait('i3')

        q = DSQueue(sim=self.sim)
        self.sim.schedule(0, consumer('c1'))
        self.sim.schedule(0, consumer('c2'))
        self.sim.schedule(0, consumer('c3'))
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(len(order), 3)
        for _, t, _ in order:
            self.assertEqual(t, 5)

    # ---- async get ---------------------------------------------------------

    def test13_async_get_returns_single_element(self):
        results = []

        async def consumer():
            item = await q.get()
            results.append(item)

        q = DSQueue(sim=self.sim)
        q.put_nowait('async_item')
        self.sim.schedule(0, consumer())
        self.sim.run(5)
        self.assertEqual(results, ['async_item'])
        self.assertNotIsInstance(results[0], list)

    def test14_async_get_blocks_until_item_available(self):
        results = []

        async def consumer():
            item = await q.get()
            results.append(('got', self.sim.time, item))

        async def producer():
            await self.sim.wait(4)
            q.put_nowait('late')

        q = DSQueue(sim=self.sim)
        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(results, [('got', 4, 'late')])

    def test15_async_get_timeout_returns_none(self):
        results = []

        async def consumer():
            item = await q.get(timeout=2)
            results.append(item)

        q = DSQueue(sim=self.sim)
        self.sim.schedule(0, consumer())
        self.sim.run(10)
        self.assertEqual(results, [None])

    def test16_async_get_with_cond(self):
        results = []

        async def consumer():
            item = await q.get(cond=lambda e: isinstance(e, int))
            results.append(item)

        async def producer():
            await self.sim.wait(2)
            q.put_nowait('string')
            await self.sim.wait(1)
            q.get_nowait()        # remove 'string' so int becomes head
            q.put_nowait(42)

        q = DSQueue(sim=self.sim)
        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(results, [42])


# ---------------------------------------------------------------------------
# DSQueue with DSKeyOrder policy (priority queue integration tests)
# ---------------------------------------------------------------------------

class TestQueuePriority(unittest.TestCase):
    '''Integration tests for DSQueue backed by DSKeyOrder.

    These tests verify that the priority ordering provided by DSKeyOrder is
    preserved end-to-end through the DSQueue simulation component.
    '''

    def setUp(self):
        self.sim = DSSimulation()

    # ---- construction ------------------------------------------------------

    def test1_buffer_is_dskeyqueue(self):
        q = DSQueue(policy=DSKeyOrder(key=lambda x: x), sim=self.sim)
        self.assertIsInstance(q._buffer, DSKeyOrder)

    # ---- nowait API --------------------------------------------------------

    def test2_get_nowait_priority_order(self):
        '''Items are dequeued in ascending key order regardless of insertion order.'''
        q = DSQueue(policy=DSKeyOrder(key=lambda x: x), sim=self.sim)
        q.put_nowait(5)
        q.put_nowait(1)
        q.put_nowait(3)
        self.assertEqual(q.get_n_nowait(), [1])
        self.assertEqual(q.get_n_nowait(), [3])
        self.assertEqual(q.get_n_nowait(), [5])

    def test3_get_nowait_single_priority_order(self):
        '''get_nowait (single-item) respects priority.'''
        q = DSQueue(policy=DSKeyOrder(key=lambda x: x), sim=self.sim)
        q.put_nowait(10)
        q.put_nowait(2)
        q.put_nowait(7)
        self.assertEqual(q.get_nowait(), 2)
        self.assertEqual(q.get_nowait(), 7)
        self.assertEqual(q.get_nowait(), 10)

    def test4_max_priority_negated_key(self):
        '''Negating the key turns min-heap into max-heap.'''
        q = DSQueue(policy=DSKeyOrder(key=lambda x: -x), sim=self.sim)
        for v in [3, 1, 4, 1, 5]:
            q.put_nowait(v)
        order = [q.get_n_nowait()[0] for _ in range(5)]
        self.assertEqual(order, [5, 4, 3, 1, 1])

    def test5_equal_keys_fifo_order(self):
        '''Items with equal keys come out in FIFO (insertion) order.'''
        q = DSQueue(policy=DSKeyOrder(key=lambda x: x[0]), sim=self.sim)
        q.put_nowait((1, 'first'))
        q.put_nowait((1, 'second'))
        q.put_nowait((1, 'third'))
        self.assertEqual(q.get_nowait()[1], 'first')
        self.assertEqual(q.get_nowait()[1], 'second')
        self.assertEqual(q.get_nowait()[1], 'third')

    def test6_attribute_key(self):
        '''Key function on object attribute orders correctly.'''
        class Job:
            def __init__(self, name, prio):
                self.name = name
                self.prio = prio

        q = DSQueue(policy=DSKeyOrder(key=lambda j: j.prio), sim=self.sim)
        q.put_nowait(Job('low', 100))
        q.put_nowait(Job('high', 1))
        q.put_nowait(Job('mid', 50))
        self.assertEqual(q.get_nowait().name, 'high')
        self.assertEqual(q.get_nowait().name, 'mid')
        self.assertEqual(q.get_nowait().name, 'low')

    def test7_capacity_enforced(self):
        '''Capacity limit applies to priority queue as well.'''
        q = DSQueue(capacity=2, policy=DSKeyOrder(key=lambda x: x), sim=self.sim)
        self.assertIsNotNone(q.put_nowait(3))
        self.assertIsNotNone(q.put_nowait(1))
        self.assertIsNone(q.put_nowait(2))
        self.assertEqual(len(q), 2)

    # ---- pop / remove ------------------------------------------------------

    def test8_pop_at_sorted_index(self):
        '''DSQueue.pop(index) removes item at sorted-priority index.'''
        q = DSQueue(policy=DSKeyOrder(key=lambda x: x), sim=self.sim)
        q.put_nowait(30)
        q.put_nowait(10)
        q.put_nowait(20)
        # sorted order: [10, 20, 30]; pop index 1 => 20
        self.assertEqual(q.pop(1), 20)
        self.assertEqual(q.get_n_nowait(), [10])
        self.assertEqual(q.get_n_nowait(), [30])

    def test9_remove_exact_item(self):
        '''DSQueue.remove() by exact object works with priority buffer.'''
        q = DSQueue(policy=DSKeyOrder(key=lambda x: x), sim=self.sim)
        q.put_nowait(3)
        q.put_nowait(1)
        q.put_nowait(2)
        q.remove(1)
        self.assertEqual(len(q), 2)
        self.assertEqual(q.get_n_nowait(), [2])
        self.assertEqual(q.get_n_nowait(), [3])

    def test10_remove_callable_cond(self):
        '''DSQueue.remove(callable) removes matching items from priority buffer.'''
        q = DSQueue(policy=DSKeyOrder(key=lambda x: x), sim=self.sim)
        for v in [1, 2, 3, 4, 5]:
            q.put_nowait(v)
        q.remove(lambda e: e % 2 == 0)
        order = [q.get_n_nowait()[0] for _ in range(3)]
        self.assertEqual(order, [1, 3, 5])

    # ---- blocking gget (generator API) ------------------------------------

    def test11_gget_n_blocks_then_returns_highest_priority(self):
        '''Blocking gget_n returns the highest-priority item once available.'''
        results = []

        def consumer():
            item = yield from q.gget_n()
            results.append(('got', self.sim.time, item))

        def producer():
            yield from self.sim.gwait(4)
            q.put_nowait(9)
            q.put_nowait(3)
            q.put_nowait(6)

        q = DSQueue(policy=DSKeyOrder(key=lambda x: x), sim=self.sim)
        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(results, [('got', 4, [3])])

    def test12_gget_blocks_then_returns_single_highest_priority(self):
        '''Blocking gget (single-item variant) also respects priority.'''
        results = []

        def consumer():
            item = yield from q.gget()
            results.append(item)

        def producer():
            yield from self.sim.gwait(3)
            q.put_nowait(50)
            q.put_nowait(10)
            q.put_nowait(30)

        q = DSQueue(policy=DSKeyOrder(key=lambda x: x), sim=self.sim)
        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(results, [10])

    def test13_multiple_consumers_get_in_priority_order(self):
        '''Multiple waiting consumers each receive items in priority order.'''
        results = []

        def consumer(label):
            item = yield from q.gget()
            results.append((label, item))

        def producer():
            yield from self.sim.gwait(5)
            q.put_nowait(30)
            q.put_nowait(10)
            q.put_nowait(20)

        q = DSQueue(policy=DSKeyOrder(key=lambda x: x), sim=self.sim)
        self.sim.schedule(0, consumer('c1'))
        self.sim.schedule(0, consumer('c2'))
        self.sim.schedule(0, consumer('c3'))
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(len(results), 3)
        # Each consumer got exactly one item; items delivered lowest-first
        received_items = [item for _, item in results]
        self.assertEqual(sorted(received_items), [10, 20, 30])

    def test14_gget_timeout_returns_none(self):
        '''Blocking gget times out when no item arrives.'''
        results = []

        def consumer():
            item = yield from q.gget(timeout=3)
            results.append(item)

        q = DSQueue(policy=DSKeyOrder(key=lambda x: x), sim=self.sim)
        self.sim.schedule(0, consumer())
        self.sim.run(10)
        self.assertEqual(results, [None])

    def test15_gput_blocks_until_space_priority_queue(self):
        '''Blocking gput waits for capacity with priority buffer.'''
        results = []

        def producer():
            q.put_nowait(1)          # fill the queue
            retval = yield from q.gput(float('inf'), 2)
            results.append(('put', self.sim.time, retval))

        def consumer():
            yield from self.sim.gwait(4)
            q.get_nowait()           # free one slot

        q = DSQueue(capacity=1, policy=DSKeyOrder(key=lambda x: x), sim=self.sim)
        self.sim.schedule(0, producer())
        self.sim.schedule(0, consumer())
        self.sim.run(20)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][1], 4)   # unblocked at t=4

    # ---- async API ---------------------------------------------------------

    def test16_async_get_priority_order(self):
        '''Async get returns highest-priority item.'''
        results = []

        async def consumer():
            item = await q.get()
            results.append(item)

        async def producer():
            await self.sim.wait(3)
            q.put_nowait(99)
            q.put_nowait(1)
            q.put_nowait(42)

        q = DSQueue(policy=DSKeyOrder(key=lambda x: x), sim=self.sim)
        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(results, [1])

    def test17_async_get_n_priority_order(self):
        '''Async get_n returns items in priority order.'''
        results = []

        async def consumer():
            items = await q.get_n(amount=3)
            results.append(items)

        async def producer():
            await self.sim.wait(2)
            q.put_nowait(5)
            q.put_nowait(2)
            q.put_nowait(8)

        q = DSQueue(policy=DSKeyOrder(key=lambda x: x), sim=self.sim)
        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(results, [[2, 5, 8]])

    # ---- interleaved puts --------------------------------------------------

    def test18_interleaved_puts_maintain_priority(self):
        '''Priority ordering holds across interleaved put_nowait calls.'''
        q = DSQueue(policy=DSKeyOrder(key=lambda x: x), sim=self.sim)
        q.put_nowait(7)
        q.put_nowait(2)
        self.assertEqual(q.get_nowait(), 2)
        q.put_nowait(1)
        q.put_nowait(5)
        order = [q.get_nowait() for _ in range(3)]
        self.assertEqual(order, [1, 5, 7])


class TestQueueStatsProbe(unittest.TestCase):
    def setUp(self):
        self.sim = DSSimulation()

    def test0_stats_probe_name(self):
        q = DSQueue(capacity=1, name='q0', sim=self.sim)
        probe = q.add_stats_probe()
        self.assertEqual(probe.name, 'q0.stats_probe')
        probe2 = q.add_stats_probe(name='ops')
        self.assertEqual(probe2.name, 'q0.ops')

    def test1_stats_probe_counts(self):
        q = DSQueue(capacity=1, sim=self.sim)
        probe = q.add_stats_probe()

        def actor():
            q.put_nowait('a')
            yield from self.sim.gwait(1)
            q.put_nowait('b')  # full -> fail (no nempty signal)
            yield from self.sim.gwait(1)
            q.get_nowait()

        self.sim.schedule(0, actor())
        self.sim.run(10)

        stats = probe.stats()
        self.assertEqual(stats['put_count'], 1)
        self.assertEqual(stats['get_count'], 1)
        self.assertEqual(stats['max_len'], 1)
        self.assertEqual(stats['current_len'], 0)

    def test2_stats_probe_time_weighted_length(self):
        q = DSQueue(sim=self.sim)
        probe = q.add_stats_probe()

        def actor():
            q.put_nowait('a')      # t=0, len=1
            yield from self.sim.gwait(3)
            q.put_nowait('b')      # t=3, len=2
            yield from self.sim.gwait(2)
            q.get_nowait()         # t=5, len=1
            yield from self.sim.gwait(5)
            q.get_nowait()         # t=10, len=0

        self.sim.schedule(0, actor())
        self.sim.run(10)

        stats = probe.get_statistics()
        self.assertEqual(stats['duration'], 10)
        self.assertAlmostEqual(stats['time_avg_len'], 1.2, places=6)
        self.assertAlmostEqual(stats['time_nonempty_ratio'], 1.0, places=6)
        self.assertEqual(stats['max_len'], 2)

    def test3_stats_probe_reset(self):
        q = DSQueue(sim=self.sim)
        probe = q.add_stats_probe()
        q.put_nowait('x')
        self.sim.run(5)
        before_reset = probe.stats()
        self.assertAlmostEqual(before_reset['time_avg_len'], 1.0, places=6)

        probe.reset()
        q.get_nowait()
        self.sim.run(10)
        after_reset = probe.stats()
        self.assertEqual(after_reset['duration'], 5)
        self.assertAlmostEqual(after_reset['time_avg_len'], 0.0, places=6)
        self.assertEqual(after_reset['put_count'], 0)
        self.assertEqual(after_reset['get_count'], 1)


class TestQueueOpsProbe(unittest.TestCase):
    def setUp(self):
        self.sim = DSSimulation()

    def test0_ops_probe_name(self):
        q = DSQueue(capacity=1, name='q0', sim=self.sim)
        probe = q.add_ops_probe()
        self.assertEqual(probe.name, 'q0.ops_probe')
        probe2 = q.add_ops_probe(name='flow')
        self.assertEqual(probe2.name, 'q0.flow')

    def test1_ops_probe_nowait_counts(self):
        q = DSQueue(capacity=1, sim=self.sim)
        probe = q.add_ops_probe()

        def actor(_event=None):
            q.put_nowait('a')      # success
            q.put_nowait('b')      # fail (full)
            q.get_nowait()         # success
            q.get_nowait()         # fail (empty)

        self.sim.schedule(0, actor)
        self.sim.run(1)

        stats = probe.stats()
        self.assertEqual(stats['put_attempt_count'], 2)
        self.assertEqual(stats['put_success_count'], 1)
        self.assertEqual(stats['put_fail_count'], 1)
        self.assertEqual(stats['put_requested_items'], 2)
        self.assertEqual(stats['put_moved_items'], 1)
        self.assertEqual(stats['get_attempt_count'], 2)
        self.assertEqual(stats['get_success_count'], 1)
        self.assertEqual(stats['get_fail_count'], 1)
        self.assertEqual(stats['get_requested_items'], 2)
        self.assertEqual(stats['get_moved_items'], 1)
        self.assertEqual(stats['put_blocked_count'], 0)
        self.assertEqual(stats['get_blocked_count'], 0)
        self.assertEqual(stats['put_timeout_count'], 0)
        self.assertEqual(stats['get_timeout_count'], 0)
        self.assertEqual(stats['max_put_batch'], 1)
        self.assertEqual(stats['max_get_batch'], 1)
        self.assertEqual(stats['current_len'], 0)

    def test2_ops_probe_put_blocked_and_timeout(self):
        q = DSQueue(capacity=1, sim=self.sim)
        probe = q.add_ops_probe()
        out = []

        def producer():
            q.put_nowait('seed')                # immediate success
            ret = yield from q.gput(1, 'x')     # blocked, timeout
            out.append(ret)
            ret = yield from q.gput(10, 'y')    # blocked, later success
            out.append(ret)

        def consumer():
            yield from self.sim.gwait(3)
            q.get_nowait()  # free one slot for second gput

        self.sim.schedule(0, producer())
        self.sim.schedule(0, consumer())
        self.sim.run(20)

        self.assertEqual(out[0], None)
        self.assertIsNotNone(out[1])
        stats = probe.stats()
        self.assertEqual(stats['put_attempt_count'], 3)
        self.assertEqual(stats['put_success_count'], 2)
        self.assertEqual(stats['put_fail_count'], 1)
        self.assertEqual(stats['put_blocked_count'], 2)
        self.assertEqual(stats['put_timeout_count'], 1)
        self.assertEqual(stats['put_requested_items'], 3)
        self.assertEqual(stats['put_moved_items'], 2)

    def test3_ops_probe_get_blocked_and_timeout(self):
        q = DSQueue(sim=self.sim)
        probe = q.add_ops_probe()
        out = []

        def consumer():
            ret = yield from q.gget(1)          # blocked, timeout
            out.append(ret)
            ret = yield from q.gget(10)         # blocked, later success
            out.append(ret)

        def producer():
            yield from self.sim.gwait(3)
            q.put_nowait('hello')

        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)

        self.assertEqual(out[0], None)
        self.assertEqual(out[1], 'hello')
        stats = probe.stats()
        self.assertEqual(stats['get_attempt_count'], 2)
        self.assertEqual(stats['get_success_count'], 1)
        self.assertEqual(stats['get_fail_count'], 1)
        self.assertEqual(stats['get_blocked_count'], 2)
        self.assertEqual(stats['get_timeout_count'], 1)
        self.assertEqual(stats['get_requested_items'], 2)
        self.assertEqual(stats['get_moved_items'], 1)
        self.assertEqual(stats['put_attempt_count'], 1)
        self.assertEqual(stats['put_success_count'], 1)

    def test4_ops_probe_pop_remove_setitem(self):
        q = DSQueue(sim=self.sim)
        probe = q.add_ops_probe()

        def actor(_event=None):
            q.put_nowait('a', 'b', 'c')         # put batch size 3
            q.pop(1)                            # success
            q.pop(10)                           # fail
            q[0] = 'x'                          # setitem
            q.remove(lambda e: e == 'x')        # success, removed one
            q.remove('zzz')                     # fail

        self.sim.schedule(0, actor)
        self.sim.run(1)

        stats = probe.stats()
        self.assertEqual(stats['pop_attempt_count'], 2)
        self.assertEqual(stats['pop_success_count'], 1)
        self.assertEqual(stats['pop_fail_count'], 1)
        self.assertEqual(stats['pop_moved_items'], 1)
        self.assertEqual(stats['remove_attempt_count'], 2)
        self.assertEqual(stats['remove_success_count'], 1)
        self.assertEqual(stats['remove_fail_count'], 1)
        self.assertEqual(stats['remove_moved_items'], 1)
        self.assertEqual(stats['setitem_count'], 1)
        self.assertEqual(stats['max_put_batch'], 3)


class TestQueueLatencyProbe(unittest.TestCase):
    def setUp(self):
        self.sim = DSSimulation()

    def test0_latency_probe_name(self):
        q = DSQueue(capacity=1, name='q0', sim=self.sim)
        probe = q.add_latency_probe()
        self.assertEqual(probe.name, 'q0.latency_probe')
        probe2 = q.add_latency_probe(name='lat')
        self.assertEqual(probe2.name, 'q0.lat')

    def test1_stay_time_basic(self):
        q = DSQueue(sim=self.sim)
        probe = q.add_latency_probe()

        def actor():
            q.put_nowait('a')
            yield from self.sim.gwait(3)
            q.get_nowait()

        self.sim.schedule(0, actor())
        self.sim.run(10)

        stats = probe.stats()
        self.assertEqual(stats['stay_count'], 1)
        self.assertAlmostEqual(stats['stay_time_avg'], 3.0, places=6)
        self.assertAlmostEqual(stats['stay_time_min'], 3.0, places=6)
        self.assertAlmostEqual(stats['stay_time_max'], 3.0, places=6)
        self.assertEqual(stats['untracked_exit_count'], 0)

    def test2_put_wait_time_blocked_and_timeout(self):
        q = DSQueue(capacity=1, sim=self.sim)
        probe = q.add_latency_probe()

        def producer():
            q.put_nowait('seed')
            _ = yield from q.gput(2, 'x')   # timeout at t=2
            _ = yield from q.gput(10, 'y')  # waits until t=4

        def consumer():
            yield from self.sim.gwait(4)
            q.get_nowait()

        self.sim.schedule(0, producer())
        self.sim.schedule(0, consumer())
        self.sim.run(20)

        stats = probe.stats()
        self.assertEqual(stats['put_wait_count'], 2)
        self.assertEqual(stats['put_wait_timeout_count'], 1)
        self.assertAlmostEqual(stats['put_wait_time_total'], 4.0, places=6)
        self.assertAlmostEqual(stats['put_wait_time_avg'], 2.0, places=6)
        self.assertAlmostEqual(stats['put_wait_time_min'], 2.0, places=6)
        self.assertAlmostEqual(stats['put_wait_time_max'], 2.0, places=6)

    def test3_get_wait_time_blocked_and_timeout(self):
        q = DSQueue(sim=self.sim)
        probe = q.add_latency_probe()
        out = []

        def consumer():
            out.append((yield from q.gget(2)))    # timeout at t=2
            out.append((yield from q.gget(10)))   # waits to t=5

        def producer():
            yield from self.sim.gwait(5)
            q.put_nowait('hello')

        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)

        self.assertEqual(out[0], None)
        self.assertEqual(out[1], 'hello')
        stats = probe.stats()
        self.assertEqual(stats['get_wait_count'], 2)
        self.assertEqual(stats['get_wait_timeout_count'], 1)
        self.assertAlmostEqual(stats['get_wait_time_total'], 5.0, places=6)
        self.assertAlmostEqual(stats['get_wait_time_avg'], 2.5, places=6)
        self.assertAlmostEqual(stats['get_wait_time_min'], 2.0, places=6)
        self.assertAlmostEqual(stats['get_wait_time_max'], 3.0, places=6)

    def test4_seeded_items_and_setitem_stay_time(self):
        q = DSQueue(sim=self.sim)
        q.put_nowait('pre')
        probe = q.add_latency_probe()

        def actor():
            yield from self.sim.gwait(1)
            q[0] = 'new'
            yield from self.sim.gwait(2)
            q.get_nowait()

        self.sim.schedule(0, actor())
        self.sim.run(10)

        stats = probe.stats()
        self.assertEqual(stats['seeded_item_count'], 1)
        self.assertEqual(stats['stay_count'], 2)
        # seeded item stayed 1, replacement stayed 2
        self.assertAlmostEqual(stats['stay_time_total'], 3.0, places=6)
        self.assertEqual(stats['untracked_exit_count'], 0)

if __name__ == '__main__':
    unittest.main()
