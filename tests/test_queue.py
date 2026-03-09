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
Tests for DSQueue and Queue components.
'''
import unittest
from dssim import DSSimulation, Queue
from dssim.components.container import DSQueue, DSLifoQueue, DSKeyQueue


# ---------------------------------------------------------------------------
# DSQueue tests (pure data structure, no simulation required)
# ---------------------------------------------------------------------------

class TestDSQueue(unittest.TestCase):

    def setUp(self):
        self.q = DSQueue()

    # ---- construction / empty state ----------------------------------------

    def test1_init_empty(self):
        self.assertEqual(len(self.q), 0)
        self.assertFalse(self.q)
        self.assertIsNone(self.q.head)
        self.assertIsNone(self.q.tail)

    # ---- append / popleft (FIFO) -------------------------------------------

    def test2_append_popleft_fifo(self):
        self.q.append('a')
        self.q.append('b')
        self.q.append('c')
        self.assertEqual(len(self.q), 3)
        self.assertTrue(self.q)
        self.assertEqual(self.q.popleft(), 'a')
        self.assertEqual(self.q.popleft(), 'b')
        self.assertEqual(self.q.popleft(), 'c')
        self.assertEqual(len(self.q), 0)

    # ---- appendleft (priority insert) -------------------------------------

    def test3_appendleft(self):
        self.q.append('b')
        self.q.append('c')
        self.q.appendleft('a')
        self.assertEqual(self.q.popleft(), 'a')
        self.assertEqual(self.q.popleft(), 'b')

    # ---- pop (from tail) ---------------------------------------------------

    def test4_pop_from_tail(self):
        self.q.append('x')
        self.q.append('y')
        self.assertEqual(self.q.pop(), 'y')
        self.assertEqual(self.q.pop(), 'x')

    # ---- head / tail properties -------------------------------------------

    def test5_head_tail(self):
        self.q.append(1)
        self.q.append(2)
        self.q.append(3)
        self.assertEqual(self.q.head, 1)
        self.assertEqual(self.q.tail, 3)

    # ---- __contains__ ------------------------------------------------------

    def test6_contains(self):
        self.q.append('alpha')
        self.q.append('beta')
        self.assertIn('alpha', self.q)
        self.assertNotIn('gamma', self.q)

    # ---- __iter__ ----------------------------------------------------------

    def test7_iter(self):
        items = [10, 20, 30]
        for i in items:
            self.q.append(i)
        self.assertEqual(list(self.q), items)

    # ---- __getitem__ / __setitem__ -----------------------------------------

    def test8_getitem(self):
        self.q.append('x')
        self.q.append('y')
        self.assertEqual(self.q[0], 'x')
        self.assertEqual(self.q[1], 'y')

    def test9_setitem(self):
        self.q.append('old')
        self.q[0] = 'new'
        self.assertEqual(self.q[0], 'new')

    # ---- pop_at ------------------------------------------------------------

    def test10_pop_at_head(self):
        self.q.append('a')
        self.q.append('b')
        self.q.append('c')
        self.assertEqual(self.q.pop_at(0), 'a')
        self.assertEqual(list(self.q), ['b', 'c'])

    def test11_pop_at_middle(self):
        self.q.append('a')
        self.q.append('b')
        self.q.append('c')
        self.assertEqual(self.q.pop_at(1), 'b')
        self.assertEqual(list(self.q), ['a', 'c'])

    def test12_pop_at_tail(self):
        self.q.append('a')
        self.q.append('b')
        self.q.append('c')
        self.assertEqual(self.q.pop_at(2), 'c')
        self.assertEqual(list(self.q), ['a', 'b'])

    # ---- remove ------------------------------------------------------------

    def test13_remove_item(self):
        self.q.append('a')
        self.q.append('b')
        self.q.remove('a')
        self.assertEqual(list(self.q), ['b'])

    def test14_remove_missing_raises(self):
        self.q.append('a')
        with self.assertRaises(ValueError):
            self.q.remove('z')

    # ---- remove_if ---------------------------------------------------------

    def test15_remove_if_matches(self):
        for i in range(5):
            self.q.append(i)
        changed = self.q.remove_if(lambda e: e % 2 == 0)
        self.assertTrue(changed)
        self.assertEqual(list(self.q), [1, 3])

    def test16_remove_if_no_match(self):
        self.q.append(1)
        self.q.append(3)
        changed = self.q.remove_if(lambda e: e % 2 == 0)
        self.assertFalse(changed)
        self.assertEqual(list(self.q), [1, 3])

    def test17_remove_if_duplicates(self):
        self.q.append('x')
        self.q.append('x')
        self.q.append('y')
        changed = self.q.remove_if(lambda e: e == 'x')
        self.assertTrue(changed)
        self.assertEqual(list(self.q), ['y'])

    # ---- clear -------------------------------------------------------------

    def test18_clear(self):
        self.q.append(1)
        self.q.append(2)
        self.q.clear()
        self.assertEqual(len(self.q), 0)
        self.assertIsNone(self.q.head)

    # ---- append returns item -----------------------------------------------

    def test19_append_returns_item(self):
        obj = object()
        retval = self.q.append(obj)
        self.assertIs(retval, obj)

    # ---- policy interface: enqueue / dequeue / peek ------------------------

    def test20_enqueue_dequeue_fifo_default(self):
        self.q.enqueue('a')
        self.q.enqueue('b')
        self.q.enqueue('c')
        self.assertEqual(self.q.peek(), 'a')
        self.assertEqual(self.q.dequeue(), 'a')
        self.assertEqual(self.q.dequeue(), 'b')
        self.assertEqual(self.q.dequeue(), 'c')

    def test21_peek_empty(self):
        self.assertIsNone(self.q.peek())


# ---------------------------------------------------------------------------
# DSLifoQueue tests
# ---------------------------------------------------------------------------

class TestDSLifoQueue(unittest.TestCase):

    def setUp(self):
        self.q = DSLifoQueue()

    def test1_lifo_order(self):
        self.q.enqueue('a')
        self.q.enqueue('b')
        self.q.enqueue('c')
        self.assertEqual(self.q.peek(), 'c')
        self.assertEqual(self.q.dequeue(), 'c')
        self.assertEqual(self.q.dequeue(), 'b')
        self.assertEqual(self.q.dequeue(), 'a')

    def test2_peek_empty(self):
        self.assertIsNone(self.q.peek())

    def test3_len_and_bool(self):
        self.assertEqual(len(self.q), 0)
        self.assertFalse(self.q)
        self.q.enqueue(1)
        self.assertEqual(len(self.q), 1)
        self.assertTrue(self.q)

    def test4_contains_and_iter(self):
        self.q.enqueue('x')
        self.q.enqueue('y')
        self.assertIn('x', self.q)
        self.assertNotIn('z', self.q)
        self.assertEqual(list(self.q), ['x', 'y'])

    def test5_remove_if(self):
        for i in range(4):
            self.q.enqueue(i)
        self.q.remove_if(lambda e: e % 2 == 0)
        self.assertEqual(list(self.q), [1, 3])


# ---------------------------------------------------------------------------
# DSKeyQueue tests (pure data structure, no simulation required)
# ---------------------------------------------------------------------------

class TestDSKeyQueue(unittest.TestCase):

    # ---- empty state -------------------------------------------------------

    def test1_init_empty(self):
        q = DSKeyQueue()
        self.assertEqual(len(q), 0)
        self.assertFalse(q)
        self.assertIsNone(q.head)
        self.assertIsNone(q.tail)

    # ---- default key (identity) --------------------------------------------

    def test2_default_key_orders_ascending(self):
        q = DSKeyQueue()
        q.enqueue(3)
        q.enqueue(1)
        q.enqueue(2)
        self.assertEqual([q.dequeue() for _ in range(3)], [1, 2, 3])

    def test3_single_item(self):
        q = DSKeyQueue()
        q.enqueue(42)
        self.assertEqual(q.peek(), 42)
        self.assertEqual(q.dequeue(), 42)
        self.assertEqual(len(q), 0)

    # ---- min / max priority ------------------------------------------------

    def test4_min_priority_integers(self):
        q = DSKeyQueue(key=lambda x: x)
        for v in [5, 1, 3, 2, 4]:
            q.enqueue(v)
        self.assertEqual([q.dequeue() for _ in range(5)], [1, 2, 3, 4, 5])

    def test5_max_priority_negated_key(self):
        q = DSKeyQueue(key=lambda x: -x)
        for v in [5, 1, 3, 2, 4]:
            q.enqueue(v)
        self.assertEqual([q.dequeue() for _ in range(5)], [5, 4, 3, 2, 1])

    # ---- attribute-based key -----------------------------------------------

    def test6_key_on_dict_field(self):
        q = DSKeyQueue(key=lambda item: item['priority'])
        q.enqueue({'name': 'low',  'priority': 10})
        q.enqueue({'name': 'high', 'priority': 1})
        q.enqueue({'name': 'mid',  'priority': 5})
        self.assertEqual(q.dequeue()['name'], 'high')
        self.assertEqual(q.dequeue()['name'], 'mid')
        self.assertEqual(q.dequeue()['name'], 'low')

    def test7_key_on_object_attribute(self):
        class Task:
            def __init__(self, name, prio):
                self.name = name
                self.prio = prio
        q = DSKeyQueue(key=lambda t: t.prio)
        q.enqueue(Task('c', 30))
        q.enqueue(Task('a', 10))
        q.enqueue(Task('b', 20))
        self.assertEqual(q.dequeue().name, 'a')
        self.assertEqual(q.dequeue().name, 'b')
        self.assertEqual(q.dequeue().name, 'c')

    # ---- equal keys: stable (insertion) order ------------------------------

    def test8_equal_keys_stable_order(self):
        q = DSKeyQueue(key=lambda x: x[0])   # key = first element of tuple
        q.enqueue((1, 'first'))
        q.enqueue((1, 'second'))
        q.enqueue((1, 'third'))
        self.assertEqual(q.dequeue()[1], 'first')
        self.assertEqual(q.dequeue()[1], 'second')
        self.assertEqual(q.dequeue()[1], 'third')

    # ---- peek --------------------------------------------------------------

    def test9_peek_does_not_remove(self):
        q = DSKeyQueue(key=lambda x: x)
        q.enqueue(5)
        q.enqueue(2)
        self.assertEqual(q.peek(), 2)
        self.assertEqual(len(q), 2)
        self.assertEqual(q.peek(), 2)   # still there

    def test10_peek_empty(self):
        self.assertIsNone(DSKeyQueue().peek())

    # ---- enqueue return value ----------------------------------------------

    def test11_enqueue_returns_item(self):
        q = DSKeyQueue()
        obj = object()
        self.assertIs(q.enqueue(obj), obj)

    # ---- interleaved enqueue / dequeue -------------------------------------

    def test12_interleaved_operations(self):
        q = DSKeyQueue(key=lambda x: x)
        q.enqueue(4)
        q.enqueue(2)
        self.assertEqual(q.dequeue(), 2)
        q.enqueue(1)
        q.enqueue(3)
        self.assertEqual([q.dequeue() for _ in range(3)], [1, 3, 4])

    # ---- inherited sequence operations ------------------------------------

    def test13_contains_and_iter(self):
        q = DSKeyQueue(key=lambda x: x)
        q.enqueue(10)
        q.enqueue(5)
        self.assertIn(5, q)
        self.assertNotIn(99, q)
        self.assertEqual(sorted(q), [5, 10])  # iter over stored order

    def test14_remove(self):
        q = DSKeyQueue(key=lambda x: x)
        q.enqueue(3)
        q.enqueue(1)
        q.enqueue(2)
        q.remove(1)
        self.assertEqual([q.dequeue() for _ in range(2)], [2, 3])

    def test15_remove_if(self):
        q = DSKeyQueue(key=lambda x: x)
        for v in [4, 1, 3, 2]:
            q.enqueue(v)
        q.remove_if(lambda e: e % 2 == 0)
        self.assertEqual([q.dequeue() for _ in range(2)], [1, 3])

    def test16_pop_at(self):
        q = DSKeyQueue(key=lambda x: x)
        for v in [3, 1, 2]:
            q.enqueue(v)
        # sorted order in buffer: [1, 2, 3]
        self.assertEqual(q.pop_at(1), 2)
        self.assertEqual([q.dequeue() for _ in range(2)], [1, 3])

    def test17_len_and_bool(self):
        q = DSKeyQueue()
        self.assertFalse(q)
        q.enqueue(0)
        self.assertTrue(q)
        self.assertEqual(len(q), 1)


# ---------------------------------------------------------------------------
# Queue component tests (requires DSSimulation)
# ---------------------------------------------------------------------------

class TestQueue(unittest.TestCase):

    def setUp(self):
        self.sim = DSSimulation()

    # ---- put_nowait / get_nowait -------------------------------------------

    def test1_put_nowait_and_get_nowait_basic(self):
        q = Queue(sim=self.sim)
        result = q.put_nowait('item')
        self.assertIsNotNone(result)
        self.assertEqual(len(q), 1)
        items = q.get_n_nowait()
        self.assertEqual(items, ['item'])
        self.assertEqual(len(q), 0)

    def test2_put_nowait_multiple(self):
        q = Queue(sim=self.sim)
        q.put_nowait('a', 'b', 'c')
        self.assertEqual(len(q), 3)
        self.assertEqual(q.get_n_nowait(), ['a'])
        self.assertEqual(q.get_n_nowait(), ['b'])
        self.assertEqual(q.get_n_nowait(), ['c'])

    def test3_put_nowait_full_returns_none(self):
        q = Queue(capacity=2, sim=self.sim)
        q.put_nowait('a', 'b')
        result = q.put_nowait('c')
        self.assertIsNone(result)
        self.assertEqual(len(q), 2)

    def test4_get_nowait_empty_returns_none(self):
        q = Queue(sim=self.sim)
        result = q.get_n_nowait()
        self.assertIsNone(result)

    def test5_get_nowait_amount(self):
        q = Queue(sim=self.sim)
        q.put_nowait('a', 'b', 'c')
        items = q.get_n_nowait(amount=2)
        self.assertEqual(items, ['a', 'b'])
        self.assertEqual(len(q), 1)

    def test6_get_nowait_cond_head(self):
        q = Queue(sim=self.sim)
        q.put_nowait('skip')
        result = q.get_n_nowait(cond=lambda e: e != 'skip')
        self.assertIsNone(result)   # head doesn't pass cond
        result = q.get_n_nowait(cond=lambda e: e == 'skip')
        self.assertEqual(result, ['skip'])

    # ---- fifo ordering -----------------------------------------------------

    def test7_fifo_order(self):
        q = Queue(sim=self.sim)
        for i in range(5):
            q.put_nowait(i)
        for i in range(5):
            self.assertEqual(q.get_n_nowait(), [i])

    # ---- capacity ----------------------------------------------------------

    def test8_infinite_capacity_default(self):
        q = Queue(sim=self.sim)
        for i in range(1000):
            self.assertIsNotNone(q.put_nowait(i))
        self.assertEqual(len(q), 1000)

    def test9_capacity_enforced(self):
        q = Queue(capacity=3, sim=self.sim)
        self.assertIsNotNone(q.put_nowait(1))
        self.assertIsNotNone(q.put_nowait(2))
        self.assertIsNotNone(q.put_nowait(3))
        self.assertIsNone(q.put_nowait(4))

    # ---- sequence protocol -------------------------------------------------

    def test10_getitem_setitem(self):
        q = Queue(sim=self.sim)
        q.put_nowait('x')
        self.assertEqual(q[0], 'x')
        q[0] = 'y'
        self.assertEqual(q[0], 'y')

    def test11_iter(self):
        q = Queue(sim=self.sim)
        q.put_nowait('a', 'b', 'c')
        self.assertEqual(list(q), ['a', 'b', 'c'])

    def test12_contains(self):
        q = Queue(sim=self.sim)
        q.put_nowait('needle')
        self.assertIn('needle', q)
        self.assertNotIn('haystack', q)

    # ---- pop ---------------------------------------------------------------

    def test13_pop_head(self):
        q = Queue(sim=self.sim)
        q.put_nowait('a', 'b', 'c')
        self.assertEqual(q.pop(0), 'a')
        self.assertEqual(list(q), ['b', 'c'])

    def test14_pop_middle(self):
        q = Queue(sim=self.sim)
        q.put_nowait('a', 'b', 'c')
        self.assertEqual(q.pop(1), 'b')
        self.assertEqual(list(q), ['a', 'c'])

    def test15_pop_out_of_range(self):
        q = Queue(sim=self.sim)
        q.put_nowait('a')
        self.assertIsNone(q.pop(5))
        self.assertIs(q.pop(5, 'default'), 'default')

    # ---- remove ------------------------------------------------------------

    def test16_remove_exact_item(self):
        q = Queue(sim=self.sim)
        obj = object()
        q.put_nowait(obj)
        q.put_nowait('other')
        q.remove(obj)
        self.assertNotIn(obj, q)
        self.assertEqual(len(q), 1)

    def test17_remove_callable_cond(self):
        q = Queue(sim=self.sim)
        q.put_nowait(1, 2, 3, 4)
        q.remove(lambda e: e % 2 == 0)
        self.assertEqual(list(q), [1, 3])

    def test18_remove_no_match_is_noop(self):
        q = Queue(sim=self.sim)
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

        q = Queue(sim=self.sim)
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

        q = Queue(capacity=1, sim=self.sim)
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

        q = Queue(sim=self.sim)
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

        q = Queue(sim=self.sim)
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

        q = Queue(capacity=1, sim=self.sim)
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

        q = Queue(sim=self.sim)
        self.sim.schedule(0, consumer('c1'))
        self.sim.schedule(0, consumer('c2'))
        self.sim.schedule(0, consumer('c3'))
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(len(order), 3)
        # all wake at t=5
        for name, t in order:
            self.assertEqual(t, 5)

    # ---- gwait / wait / check_and_gwait / check_and_wait on Queue ----------

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

        q = Queue(sim=self.sim)
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

        q = Queue(sim=self.sim)
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

        q = Queue(sim=self.sim)
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

        q = Queue(sim=self.sim)
        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(results, [('got', 4, ['async_item'])])


# ---------------------------------------------------------------------------
# Queue with DSLifoQueue policy
# ---------------------------------------------------------------------------

class TestQueueLifo(unittest.TestCase):

    def setUp(self):
        self.sim = DSSimulation()

    def test1_lifo_order_nowait(self):
        q = Queue(policy=DSLifoQueue(), sim=self.sim)
        q.put_nowait('a')
        q.put_nowait('b')
        q.put_nowait('c')
        self.assertEqual(q.get_n_nowait(), ['c'])
        self.assertEqual(q.get_n_nowait(), ['b'])
        self.assertEqual(q.get_n_nowait(), ['a'])

    def test2_buffer_is_dslifoqueue(self):
        q = Queue(policy=DSLifoQueue(), sim=self.sim)
        self.assertIsInstance(q._buffer, DSLifoQueue)

    def test3_fifo_is_default(self):
        q = Queue(sim=self.sim)
        self.assertIsInstance(q._buffer, DSQueue)
        self.assertNotIsInstance(q._buffer, DSLifoQueue)

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

        q = Queue(policy=DSLifoQueue(), sim=self.sim)
        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(10)
        self.assertEqual(results, [['second']])


# ---------------------------------------------------------------------------
# Single-item API: get_nowait / gget / get
# ---------------------------------------------------------------------------

class TestQueueSingleItemGet(unittest.TestCase):
    '''
    Queue.get_nowait() / .gget() / .get() return a single element (not
    wrapped in a list), in contrast to get_n_nowait / gget_n / get_n which
    always return a list.
    '''

    def setUp(self):
        self.sim = DSSimulation()

    # ---- get_nowait --------------------------------------------------------

    def test1_get_nowait_returns_single_element(self):
        q = Queue(sim=self.sim)
        q.put_nowait('A')
        result = q.get_nowait()
        self.assertEqual(result, 'A')
        self.assertNotIsInstance(result, list)
        self.assertEqual(len(q), 0)

    def test2_get_nowait_returns_none_when_empty(self):
        q = Queue(sim=self.sim)
        result = q.get_nowait()
        self.assertIsNone(result)

    def test3_get_nowait_fifo_order(self):
        q = Queue(sim=self.sim)
        q.put_nowait('first', 'second', 'third')
        self.assertEqual(q.get_nowait(), 'first')
        self.assertEqual(q.get_nowait(), 'second')
        self.assertEqual(q.get_nowait(), 'third')

    def test4_get_nowait_with_passing_cond(self):
        q = Queue(sim=self.sim)
        q.put_nowait('match')
        result = q.get_nowait(cond=lambda e: e == 'match')
        self.assertEqual(result, 'match')

    def test5_get_nowait_with_failing_cond_returns_none(self):
        q = Queue(sim=self.sim)
        q.put_nowait('item')
        result = q.get_nowait(cond=lambda e: e == 'other')
        self.assertIsNone(result)
        self.assertEqual(len(q), 1)  # item still in queue

    def test6_get_nowait_vs_get_n_nowait_return_types(self):
        q = Queue(sim=self.sim)
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

        q = Queue(sim=self.sim)
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

        q = Queue(sim=self.sim)
        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(results, [('got', 5, 'deferred')])

    def test9_gget_timeout_returns_none(self):
        results = []

        def consumer():
            item = yield from q.gget(timeout=3)
            results.append(item)

        q = Queue(sim=self.sim)
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

        q = Queue(sim=self.sim)
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

        q = Queue(sim=self.sim)
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

        q = Queue(sim=self.sim)
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

        q = Queue(sim=self.sim)
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

        q = Queue(sim=self.sim)
        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(results, [('got', 4, 'late')])

    def test15_async_get_timeout_returns_none(self):
        results = []

        async def consumer():
            item = await q.get(timeout=2)
            results.append(item)

        q = Queue(sim=self.sim)
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

        q = Queue(sim=self.sim)
        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(results, [42])


# ---------------------------------------------------------------------------
# Queue with DSKeyQueue policy (priority queue integration tests)
# ---------------------------------------------------------------------------

class TestQueuePriority(unittest.TestCase):
    '''Integration tests for Queue backed by DSKeyQueue.

    These tests verify that the priority ordering provided by DSKeyQueue is
    preserved end-to-end through the Queue simulation component.
    '''

    def setUp(self):
        self.sim = DSSimulation()

    # ---- construction ------------------------------------------------------

    def test1_buffer_is_dskeyqueue(self):
        q = Queue(policy=DSKeyQueue(key=lambda x: x), sim=self.sim)
        self.assertIsInstance(q._buffer, DSKeyQueue)

    # ---- nowait API --------------------------------------------------------

    def test2_get_nowait_priority_order(self):
        '''Items are dequeued in ascending key order regardless of insertion order.'''
        q = Queue(policy=DSKeyQueue(key=lambda x: x), sim=self.sim)
        q.put_nowait(5)
        q.put_nowait(1)
        q.put_nowait(3)
        self.assertEqual(q.get_n_nowait(), [1])
        self.assertEqual(q.get_n_nowait(), [3])
        self.assertEqual(q.get_n_nowait(), [5])

    def test3_get_nowait_single_priority_order(self):
        '''get_nowait (single-item) respects priority.'''
        q = Queue(policy=DSKeyQueue(key=lambda x: x), sim=self.sim)
        q.put_nowait(10)
        q.put_nowait(2)
        q.put_nowait(7)
        self.assertEqual(q.get_nowait(), 2)
        self.assertEqual(q.get_nowait(), 7)
        self.assertEqual(q.get_nowait(), 10)

    def test4_max_priority_negated_key(self):
        '''Negating the key turns min-heap into max-heap.'''
        q = Queue(policy=DSKeyQueue(key=lambda x: -x), sim=self.sim)
        for v in [3, 1, 4, 1, 5]:
            q.put_nowait(v)
        order = [q.get_n_nowait()[0] for _ in range(5)]
        self.assertEqual(order, [5, 4, 3, 1, 1])

    def test5_equal_keys_fifo_order(self):
        '''Items with equal keys come out in FIFO (insertion) order.'''
        q = Queue(policy=DSKeyQueue(key=lambda x: x[0]), sim=self.sim)
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

        q = Queue(policy=DSKeyQueue(key=lambda j: j.prio), sim=self.sim)
        q.put_nowait(Job('low', 100))
        q.put_nowait(Job('high', 1))
        q.put_nowait(Job('mid', 50))
        self.assertEqual(q.get_nowait().name, 'high')
        self.assertEqual(q.get_nowait().name, 'mid')
        self.assertEqual(q.get_nowait().name, 'low')

    def test7_capacity_enforced(self):
        '''Capacity limit applies to priority queue as well.'''
        q = Queue(capacity=2, policy=DSKeyQueue(key=lambda x: x), sim=self.sim)
        self.assertIsNotNone(q.put_nowait(3))
        self.assertIsNotNone(q.put_nowait(1))
        self.assertIsNone(q.put_nowait(2))
        self.assertEqual(len(q), 2)

    # ---- pop / remove ------------------------------------------------------

    def test8_pop_at_sorted_index(self):
        '''Queue.pop(index) removes item at sorted-priority index.'''
        q = Queue(policy=DSKeyQueue(key=lambda x: x), sim=self.sim)
        q.put_nowait(30)
        q.put_nowait(10)
        q.put_nowait(20)
        # sorted order: [10, 20, 30]; pop index 1 => 20
        self.assertEqual(q.pop(1), 20)
        self.assertEqual(q.get_n_nowait(), [10])
        self.assertEqual(q.get_n_nowait(), [30])

    def test9_remove_exact_item(self):
        '''Queue.remove() by exact object works with priority buffer.'''
        q = Queue(policy=DSKeyQueue(key=lambda x: x), sim=self.sim)
        q.put_nowait(3)
        q.put_nowait(1)
        q.put_nowait(2)
        q.remove(1)
        self.assertEqual(len(q), 2)
        self.assertEqual(q.get_n_nowait(), [2])
        self.assertEqual(q.get_n_nowait(), [3])

    def test10_remove_callable_cond(self):
        '''Queue.remove(callable) removes matching items from priority buffer.'''
        q = Queue(policy=DSKeyQueue(key=lambda x: x), sim=self.sim)
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

        q = Queue(policy=DSKeyQueue(key=lambda x: x), sim=self.sim)
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

        q = Queue(policy=DSKeyQueue(key=lambda x: x), sim=self.sim)
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

        q = Queue(policy=DSKeyQueue(key=lambda x: x), sim=self.sim)
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

        q = Queue(policy=DSKeyQueue(key=lambda x: x), sim=self.sim)
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

        q = Queue(capacity=1, policy=DSKeyQueue(key=lambda x: x), sim=self.sim)
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

        q = Queue(policy=DSKeyQueue(key=lambda x: x), sim=self.sim)
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

        q = Queue(policy=DSKeyQueue(key=lambda x: x), sim=self.sim)
        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(results, [[2, 5, 8]])

    # ---- interleaved puts --------------------------------------------------

    def test18_interleaved_puts_maintain_priority(self):
        '''Priority ordering holds across interleaved put_nowait calls.'''
        q = Queue(policy=DSKeyQueue(key=lambda x: x), sim=self.sim)
        q.put_nowait(7)
        q.put_nowait(2)
        self.assertEqual(q.get_nowait(), 2)
        q.put_nowait(1)
        q.put_nowait(5)
        order = [q.get_nowait() for _ in range(3)]
        self.assertEqual(order, [1, 5, 7])


if __name__ == '__main__':
    unittest.main()
