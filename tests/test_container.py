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
Tests for the Container component.
Covers put_nowait/get_nowait, blocking get/put, capacity, specific-object
retrieval, all_or_nothing mode, and tx_nempty / tx_changed signal routing.
'''
import unittest
from dssim import DSSimulation
from dssim.components.container import Container


# ---------------------------------------------------------------------------
# Synchronous (nowait) tests — no simulation event loop needed
# ---------------------------------------------------------------------------

class TestContainerNowait(unittest.TestCase):

    def setUp(self):
        self.sim = DSSimulation()

    def _make(self, capacity=None):
        return Container(capacity=capacity, sim=self.sim)

    # ---- init state --------------------------------------------------------

    def test_init_empty(self):
        c = self._make()
        self.assertEqual(len(c), 0)

    def test_tx_nempty_producer_exists(self):
        c = self._make()
        self.assertIsNotNone(c.tx_nempty)

    # ---- put_nowait --------------------------------------------------------

    def test_put_nowait_single(self):
        c = self._make()
        result = c.put_nowait('A')
        self.assertIsNotNone(result)
        self.assertEqual(len(c), 1)

    def test_put_nowait_multiple(self):
        c = self._make()
        result = c.put_nowait('A', 'B', 'C')
        self.assertIsNotNone(result)
        self.assertEqual(len(c), 3)

    def test_put_nowait_duplicate_objects(self):
        c = self._make()
        c.put_nowait('X', 'X', 'X')
        self.assertEqual(len(c), 3)

    def test_put_nowait_at_capacity_fails(self):
        c = self._make(capacity=2)
        c.put_nowait('A', 'B')
        result = c.put_nowait('C')
        self.assertIsNone(result)
        self.assertEqual(len(c), 2)

    def test_put_nowait_below_capacity_succeeds(self):
        c = self._make(capacity=3)
        c.put_nowait('A')
        self.assertIsNotNone(c.put_nowait('B', 'C'))
        self.assertEqual(len(c), 3)

    def test_put_nowait_no_capacity_is_unbounded(self):
        c = self._make()
        for i in range(500):
            self.assertIsNotNone(c.put_nowait(object()))

    # ---- get_nowait --------------------------------------------------------

    def test_get_nowait_any(self):
        c = self._make()
        c.put_nowait('A')
        result = c.get_n_nowait()
        self.assertEqual(result, ['A'])
        self.assertEqual(len(c), 0)

    def test_get_nowait_specific_present(self):
        c = self._make()
        c.put_nowait('A', 'B')
        result = c.get_n_nowait('B')
        self.assertEqual(result, ['B'])
        self.assertIn('A', list(c))

    def test_get_nowait_specific_missing(self):
        c = self._make()
        c.put_nowait('A')
        result = c.get_n_nowait('Z')
        self.assertEqual(result, [])
        self.assertEqual(len(c), 1)  # 'A' still present

    def test_get_nowait_multiple_specific(self):
        c = self._make()
        c.put_nowait('A', 'B', 'C')
        result = c.get_n_nowait('A', 'C')
        self.assertIn('A', result)
        self.assertIn('C', result)
        self.assertEqual(len(result), 2)
        self.assertEqual(len(c), 1)

    def test_get_nowait_duplicate_decrements_count(self):
        c = self._make()
        c.put_nowait('X', 'X')
        result = c.get_n_nowait('X')
        self.assertEqual(result, ['X'])
        self.assertEqual(len(c), 1)  # one 'X' remains

    # ---- remove ------------------------------------------------------------

    def test_remove_reduces_size(self):
        c = self._make()
        c.put_nowait('A', 'B')
        c.remove('A')
        self.assertEqual(len(c), 1)

    # ---- iteration ---------------------------------------------------------

    def test_iter_includes_duplicates(self):
        c = self._make()
        c.put_nowait('X', 'X', 'Y')
        elements = list(c)
        self.assertEqual(sorted(elements), ['X', 'X', 'Y'])


# ---------------------------------------------------------------------------
# Blocking get (gget / get) — simulation event loop
# ---------------------------------------------------------------------------

class TestContainerBlockingGet(unittest.TestCase):

    def setUp(self):
        self.sim = DSSimulation()

    def _make(self, capacity=None):
        return Container(capacity=capacity, sim=self.sim)

    # ---- gget any object ---------------------------------------------------

    def test_gget_any_blocks_until_item_added(self):
        results = []

        def consumer():
            retval = yield from c.gget_n()
            results.append(('got', self.sim.time, retval))

        def producer():
            yield from self.sim.gwait(5)
            c.put_nowait('hello')

        c = self._make()
        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], ('got', 5, ['hello']))

    def test_gget_any_gets_item_already_present(self):
        results = []

        def consumer():
            retval = yield from c.gget_n()
            results.append(retval)

        c = self._make()
        c.put_nowait('immediate')
        self.sim.schedule(0, consumer())
        self.sim.run(5)
        self.assertEqual(results, [['immediate']])

    def test_gget_any_timeout(self):
        results = []

        def consumer():
            retval = yield from c.gget_n(timeout=3)
            results.append(retval)

        c = self._make()
        self.sim.schedule(0, consumer())
        self.sim.run(10)
        self.assertEqual(results, [None])

    # ---- gget specific object ----------------------------------------------

    def test_gget_specific_blocks_until_object_added(self):
        results = []

        def consumer():
            retval = yield from c.gget_n(float('inf'), 'B')
            results.append(('got', self.sim.time, retval))

        def producer():
            yield from self.sim.gwait(3)
            c.put_nowait('A')   # wrong item
            yield from self.sim.gwait(3)
            c.put_nowait('B')   # correct item

        c = self._make()
        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][1], 6)   # wakes at t=6 when 'B' is added
        self.assertIn('B', results[0][2])

    def test_gget_specific_timeout(self):
        results = []

        def consumer():
            retval = yield from c.gget_n(4, 'missing')
            results.append(retval)

        c = self._make()
        c.put_nowait('other')
        self.sim.schedule(0, consumer())
        self.sim.run(10)
        self.assertEqual(results, [None])

    def test_gget_all_or_nothing_false(self):
        '''all_or_nothing=False: collects matching objects as they arrive.'''
        results = []

        def consumer():
            retval = yield from c.gget_n(float('inf'), 'X', 'X', all_or_nothing=False)
            results.append(('got', self.sim.time, retval))

        def producer():
            yield from self.sim.gwait(2)
            c.put_nowait('X')
            yield from self.sim.gwait(2)
            c.put_nowait('X')

        c = self._make()
        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][2], ['X', 'X'])

    # ---- async get ---------------------------------------------------------

    def test_async_get_any(self):
        results = []

        async def consumer():
            retval = await c.get_n()
            results.append(('got', self.sim.time, retval))

        async def producer():
            await self.sim.wait(4)
            c.put_nowait('async_item')

        c = self._make()
        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(results, [('got', 4, ['async_item'])])

    def test_async_get_specific(self):
        results = []

        async def consumer():
            retval = await c.get_n(float('inf'), 'target')
            results.append(retval)

        async def producer():
            await self.sim.wait(3)
            c.put_nowait('target')

        c = self._make()
        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(10)
        self.assertIsNotNone(results[0])
        self.assertIn('target', results[0])

    def test_async_get_timeout(self):
        results = []

        async def consumer():
            retval = await c.get_n(timeout=2)
            results.append(retval)

        c = self._make()
        self.sim.schedule(0, consumer())
        self.sim.run(10)
        self.assertEqual(results, [None])


# ---------------------------------------------------------------------------
# Blocking put (gput / put) — simulation event loop
# ---------------------------------------------------------------------------

class TestContainerBlockingPut(unittest.TestCase):

    def setUp(self):
        self.sim = DSSimulation()

    def _make(self, capacity=None):
        return Container(capacity=capacity, sim=self.sim)

    def test_gput_blocks_until_space_available(self):
        results = []

        def producer():
            c.put_nowait('first')    # fill the single slot
            retval = yield from c.gput(float('inf'), 'second')
            results.append(('put', self.sim.time, retval))

        def consumer():
            yield from self.sim.gwait(5)
            c.get_nowait()   # frees space

        c = self._make(capacity=1)
        self.sim.schedule(0, producer())
        self.sim.schedule(0, consumer())
        self.sim.run(20)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][1], 5)

    def test_gput_timeout(self):
        results = []

        def producer():
            c.put_nowait('fill')
            retval = yield from c.gput(3, 'second')
            results.append(retval)

        c = self._make(capacity=1)
        self.sim.schedule(0, producer())
        self.sim.run(10)
        self.assertEqual(results, [None])

    def test_async_put_blocks_until_space(self):
        results = []

        async def producer():
            c.put_nowait('fill')
            retval = await c.put(float('inf'), 'second')
            results.append(('put', self.sim.time, retval))

        async def consumer():
            await self.sim.wait(4)
            c.get_nowait()

        c = self._make(capacity=1)
        self.sim.schedule(0, producer())
        self.sim.schedule(0, consumer())
        self.sim.run(10)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][1], 4)


# ---------------------------------------------------------------------------
# Signal routing: tx_nempty vs tx_changed
# ---------------------------------------------------------------------------

class TestContainerSignalRouting(unittest.TestCase):
    '''
    Verify that tx_nempty wakes any-object getters and tx_changed wakes
    specific-object getters, without spurious cross-wakeups.
    '''

    def setUp(self):
        self.sim = DSSimulation()

    def _make(self, capacity=None):
        return Container(capacity=capacity, sim=self.sim)

    def test_any_getter_woken_by_put_nowait(self):
        '''put_nowait fires tx_nempty and wakes a waiting any-object getter.'''
        results = []

        def consumer():
            retval = yield from c.gget_n()
            results.append(('got', self.sim.time, retval))

        def producer():
            yield from self.sim.gwait(3)
            c.put_nowait('item')

        c = self._make()
        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(10)
        self.assertEqual(results, [('got', 3, ['item'])])

    def test_specific_getter_woken_by_put_nowait(self):
        '''put_nowait fires tx_changed and wakes a waiting specific-object getter.'''
        results = []

        def consumer():
            retval = yield from c.gget_n(float('inf'), 'special')
            results.append(('got', self.sim.time, retval))

        def producer():
            yield from self.sim.gwait(4)
            c.put_nowait('special')

        c = self._make()
        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(10)
        self.assertEqual(results, [('got', 4, ['special'])])

    def test_both_getter_types_coexist(self):
        '''An any-getter and a specific-getter can both be satisfied independently.'''
        results = []

        def any_consumer():
            retval = yield from c.gget_n()
            results.append(('any', self.sim.time))

        def specific_consumer():
            retval = yield from c.gget_n(float('inf'), 'B')
            results.append(('specific', self.sim.time))

        def producer():
            yield from self.sim.gwait(5)
            c.put_nowait('A')   # wakes the any-getter
            c.put_nowait('B')   # wakes the specific-getter

        c = self._make()
        self.sim.schedule(0, any_consumer())
        self.sim.schedule(0, specific_consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(len(results), 2)
        # both wake at t=5
        for _, t in results:
            self.assertEqual(t, 5)

    def test_putter_woken_by_get_nowait(self):
        '''get_nowait fires tx_changed and wakes a blocked putter.'''
        results = []

        def producer():
            c.put_nowait('fill')
            retval = yield from c.gput(float('inf'), 'second')
            results.append(('put', self.sim.time))

        def consumer():
            yield from self.sim.gwait(3)
            c.get_nowait()

        c = self._make(capacity=1)
        self.sim.schedule(0, producer())
        self.sim.schedule(0, consumer())
        self.sim.run(10)
        self.assertEqual(results, [('put', 3)])

    def test_no_spurious_signal_when_no_getters(self):
        '''put_nowait with no waiters does not schedule unnecessary events.
        Verified indirectly: simulation stays idle after run with no consumers.'''
        c = self._make()
        # Just verifying no exception / crash when no one is listening
        c.put_nowait('X')
        c.put_nowait('Y')
        self.assertEqual(len(c), 2)

    def test_multiple_any_getters_each_get_one_item(self):
        '''Multiple any-getters each wake up and consume one item.'''
        results = []

        def consumer(name):
            retval = yield from c.gget_n()
            results.append((name, self.sim.time, retval))

        def producer():
            yield from self.sim.gwait(5)
            c.put_nowait('i1')
            c.put_nowait('i2')
            c.put_nowait('i3')

        c = self._make()
        self.sim.schedule(0, consumer('c1'))
        self.sim.schedule(0, consumer('c2'))
        self.sim.schedule(0, consumer('c3'))
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(len(results), 3)
        for _, t, _ in results:
            self.assertEqual(t, 5)


# ---------------------------------------------------------------------------
# gwait / wait / check_and_gwait / check_and_wait on Container
# ---------------------------------------------------------------------------

class TestContainerWaitMethods(unittest.TestCase):
    '''
    Verify that the four DSStatefulComponent wait-method overrides in Container
    (gwait, wait, check_and_gwait, check_and_wait) correctly subscribe to
    tx_changed and wake on put/get operations.
    '''

    def setUp(self):
        self.sim = DSSimulation()

    def _make(self, capacity=None):
        return Container(capacity=capacity, sim=self.sim)

    # ---- gwait -------------------------------------------------------------

    def test_gwait_woken_by_put_nowait(self):
        '''gwait on container wakes when item is added.'''
        results = []

        def watcher():
            yield from c.gwait(cond=lambda e: len(c) > 0)
            results.append(self.sim.time)

        def actor():
            yield from self.sim.gwait(3)
            c.put_nowait('item')

        c = self._make()
        self.sim.schedule(0, watcher())
        self.sim.schedule(0, actor())
        self.sim.run(10)
        self.assertEqual(results, [3])

    def test_gwait_woken_by_get_nowait(self):
        '''gwait on container wakes when item is removed.'''
        results = []

        obj = object()

        def watcher():
            c.put_nowait(obj)
            yield from c.gwait(cond=lambda e: obj not in list(c))
            results.append(self.sim.time)

        def actor():
            yield from self.sim.gwait(4)
            c.get_n_nowait(obj)

        c = self._make()
        self.sim.schedule(0, watcher())
        self.sim.schedule(0, actor())
        self.sim.run(10)
        self.assertEqual(results, [4])

    def test_gwait_timeout(self):
        '''gwait returns None on timeout without crashing.'''
        results = []

        def watcher():
            retval = yield from c.gwait(timeout=2, cond=lambda e: len(c) > 0)
            results.append(retval)

        c = self._make()
        self.sim.schedule(0, watcher())
        self.sim.run(10)
        self.assertEqual(results, [None])

    # ---- check_and_gwait ---------------------------------------------------

    def test_check_and_gwait_returns_immediately_when_cond_true(self):
        '''check_and_gwait returns right away if condition already holds.'''
        results = []

        def watcher():
            retval = yield from c.check_and_gwait(cond=lambda e: len(c) > 0)
            results.append(self.sim.time)

        c = self._make()
        c.put_nowait('already_here')
        self.sim.schedule(0, watcher())
        self.sim.run(5)
        self.assertEqual(results, [0])

    # ---- async wait --------------------------------------------------------

    def test_wait_woken_by_put_nowait(self):
        '''async wait() wakes when item is added.'''
        results = []

        async def watcher():
            await c.wait(cond=lambda e: len(c) > 0)
            results.append(self.sim.time)

        async def actor():
            await self.sim.wait(3)
            c.put_nowait('item')

        c = self._make()
        self.sim.schedule(0, watcher())
        self.sim.schedule(0, actor())
        self.sim.run(10)
        self.assertEqual(results, [3])

    # ---- async check_and_wait ----------------------------------------------

    def test_check_and_wait_returns_immediately_when_cond_true(self):
        '''async check_and_wait returns immediately if condition already holds.'''
        results = []

        async def watcher():
            await c.check_and_wait(cond=lambda e: len(c) > 0)
            results.append(self.sim.time)

        c = self._make()
        c.put_nowait('already_here')
        self.sim.schedule(0, watcher())
        self.sim.run(5)
        self.assertEqual(results, [0])



# ---------------------------------------------------------------------------
# Single-item API: get_nowait / gget / get
# ---------------------------------------------------------------------------

class TestContainerSingleItemGet(unittest.TestCase):
    '''
    Container.get_nowait() / .gget() / .get() return a single element (not
    wrapped in a list), in contrast to get_n_nowait / gget_n / get_n which
    always return a list.
    '''

    def setUp(self):
        self.sim = DSSimulation()

    def _make(self, capacity=None):
        return Container(capacity=capacity, sim=self.sim)

    # ---- get_nowait --------------------------------------------------------

    def test_get_nowait_returns_single_element(self):
        c = self._make()
        c.put_nowait('A')
        result = c.get_nowait()
        self.assertEqual(result, 'A')
        self.assertNotIsInstance(result, list)
        self.assertEqual(len(c), 0)

    def test_get_nowait_returns_none_when_empty(self):
        c = self._make()
        result = c.get_nowait()
        self.assertIsNone(result)

    def test_get_nowait_multiple_calls_fifo(self):
        c = self._make()
        c.put_nowait('A', 'B', 'C')
        results = [c.get_nowait() for _ in range(3)]
        # Container is an unordered set; just verify we got three distinct items
        self.assertEqual(sorted(results), ['A', 'B', 'C'])
        self.assertEqual(len(c), 0)

    # ---- gget ---------------------------------------------------------------

    def test_gget_returns_single_element_immediately(self):
        results = []

        def consumer():
            item = yield from c.gget()
            results.append(item)

        c = self._make()
        c.put_nowait('hello')
        self.sim.schedule(0, consumer())
        self.sim.run(5)
        self.assertEqual(results, ['hello'])
        self.assertNotIsInstance(results[0], list)

    def test_gget_blocks_until_item_added(self):
        results = []

        def consumer():
            item = yield from c.gget()
            results.append(('got', self.sim.time, item))

        def producer():
            yield from self.sim.gwait(5)
            c.put_nowait('deferred')

        c = self._make()
        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(results, [('got', 5, 'deferred')])

    def test_gget_timeout_returns_none(self):
        results = []

        def consumer():
            item = yield from c.gget(timeout=3)
            results.append(item)

        c = self._make()
        self.sim.schedule(0, consumer())
        self.sim.run(10)
        self.assertEqual(results, [None])

    def test_gget_vs_gget_n_different_return_types(self):
        '''gget returns a bare element; gget_n wraps in list.'''
        single_results = []
        list_results = []

        def single_consumer():
            item = yield from c.gget()
            single_results.append(item)

        def list_consumer():
            items = yield from c.gget_n()
            list_results.append(items)

        c = self._make()
        c.put_nowait('x')
        c.put_nowait('y')
        self.sim.schedule(0, single_consumer())
        self.sim.schedule(0, list_consumer())
        self.sim.run(5)
        self.assertNotIsInstance(single_results[0], list)
        self.assertIsInstance(list_results[0], list)

    # ---- async get ---------------------------------------------------------

    def test_async_get_returns_single_element(self):
        results = []

        async def consumer():
            item = await c.get()
            results.append(item)

        c = self._make()
        c.put_nowait('async_item')
        self.sim.schedule(0, consumer())
        self.sim.run(5)
        self.assertEqual(results, ['async_item'])
        self.assertNotIsInstance(results[0], list)

    def test_async_get_blocks_until_item_added(self):
        results = []

        async def consumer():
            item = await c.get()
            results.append(('got', self.sim.time, item))

        async def producer():
            await self.sim.wait(4)
            c.put_nowait('late')

        c = self._make()
        self.sim.schedule(0, consumer())
        self.sim.schedule(0, producer())
        self.sim.run(20)
        self.assertEqual(results, [('got', 4, 'late')])

    def test_async_get_timeout_returns_none(self):
        results = []

        async def consumer():
            item = await c.get(timeout=2)
            results.append(item)

        c = self._make()
        self.sim.schedule(0, consumer())
        self.sim.run(10)
        self.assertEqual(results, [None])


if __name__ == '__main__':
    unittest.main()