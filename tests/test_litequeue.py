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
Tests for LiteQueue — a minimal queue for LiteLayer2 simulations.
'''
import unittest
from dssim.simulation import DSSimulation, LiteLayer2
from dssim.lite.components.litequeue import LiteQueue


def _make(capacity=float('inf')):
    '''Return a fresh (sim, LiteQueue) pair.'''
    sim = DSSimulation(layer2=LiteLayer2)
    q = LiteQueue(capacity=capacity, sim=sim)
    return sim, q


# ---------------------------------------------------------------------------
# Sequence protocol (no simulation loop needed)
# ---------------------------------------------------------------------------

class TestLiteQueueSequenceProtocol(unittest.TestCase):
    '''LiteQueue exposes len / bool / iter / contains like a container.'''

    def setUp(self):
        _, self.q = _make()

    def test1_empty_len(self):
        self.assertEqual(len(self.q), 0)

    def test2_bool_always_true(self):
        '''LiteQueue is always truthy — even when its buffer is empty.

        Python falls back to __len__ when __bool__ is absent, which would make
        an empty queue falsy and break signal's
        ``consumer or _parent_process`` fallback.
        '''
        self.assertTrue(bool(self.q))
        self.q.put_nowait(1)
        self.assertTrue(bool(self.q))
        self.q.get_nowait()
        self.assertTrue(bool(self.q))   # empty again, must still be True

    def test3_len_tracks_buffer(self):
        self.q.put_nowait('a')
        self.q.put_nowait('b')
        self.assertEqual(len(self.q), 2)
        self.q.get_nowait()
        self.assertEqual(len(self.q), 1)
        self.q.get_nowait()
        self.assertEqual(len(self.q), 0)

    def test4_contains(self):
        self.q.put_nowait(42)
        self.assertIn(42, self.q)
        self.assertNotIn(99, self.q)

    def test5_iter(self):
        for i in range(3):
            self.q.put_nowait(i)
        self.assertEqual(list(self.q), [0, 1, 2])


# ---------------------------------------------------------------------------
# Nowait operations (no simulation loop needed)
# ---------------------------------------------------------------------------

class TestLiteQueueNowait(unittest.TestCase):
    '''put_nowait / get_nowait bypass the simulation event loop.'''

    def test1_put_nowait_returns_item(self):
        _, q = _make()
        self.assertEqual(q.put_nowait('x'), 'x')

    def test2_get_nowait_returns_none_when_empty(self):
        _, q = _make()
        self.assertIsNone(q.get_nowait())

    def test3_fill_drain_fifo_order(self):
        _, q = _make()
        for i in range(5):
            q.put_nowait(i)
        got = []
        while True:
            x = q.get_nowait()
            if x is None:
                break
            got.append(x)
        self.assertEqual(got, list(range(5)))

    def test4_put_nowait_respects_capacity(self):
        _, q = _make(capacity=2)
        self.assertEqual(q.put_nowait('a'), 'a')
        self.assertEqual(q.put_nowait('b'), 'b')
        self.assertIsNone(q.put_nowait('c'))   # full
        self.assertEqual(len(q), 2)

    def test5_get_nowait_respects_capacity_wakes_putters(self):
        '''get_nowait on a full queue should schedule _PUT_READY for waiters.

        This test verifies indirectly: a blocked gput is unblocked after a
        get_nowait drains the only slot.
        '''
        sim, q = _make(capacity=1)
        q.put_nowait(0)          # fill the slot
        unblocked = []

        def producer():
            yield from q.gput(1)  # blocks — queue full
            unblocked.append(1)

        sim.schedule(0, producer())
        # Kick the sim once so producer registers as a putter.
        sim.run(until=0)
        # Now drain via nowait — should schedule _PUT_READY for the putter.
        q.get_nowait()
        sim.run()
        self.assertEqual(unblocked, [1])


# ---------------------------------------------------------------------------
# Blocking get (gget)
# ---------------------------------------------------------------------------

class TestLiteQueueGget(unittest.TestCase):

    def test1_gget_returns_immediately_when_nonempty(self):
        '''gget on a non-empty queue never suspends the caller.'''
        sim, q = _make()
        q.put_nowait(7)
        results = []

        def process():
            item = yield from q.gget()
            results.append(item)

        sim.schedule(0, process())
        sim.run()
        self.assertEqual(results, [7])

    def test2_gget_blocks_until_gput_wakes_it(self):
        '''Consumer registers first; producer's gput schedules _GET_READY.'''
        sim, q = _make()
        log = []

        def producer():
            for i in range(3):
                yield from q.gput(i)
                log.append(f'put {i}')

        def consumer():
            for _ in range(3):
                item = yield from q.gget()
                log.append(f'got {item}')

        sim.schedule(0, consumer())   # consumer registers first → blocks
        sim.schedule(0, producer())
        sim.run()
        # With unlimited capacity producer puts all 3 before consumer unblocks.
        self.assertEqual(log, ['put 0', 'put 1', 'put 2', 'got 0', 'got 1', 'got 2'])

    def test3_multiple_getters_one_item_each(self):
        '''Two getters both block; each must receive exactly one item.

        This test requires the _GET_READY cascade in send() (line 118):
        the second gput does not schedule _GET_READY (buffer was already
        non-empty), so only one _GET_READY is ever queued.  Without the
        cascade, the second getter would be stuck forever.

        Timeline:
          c1 gget() → blocks (buffer empty)
          c2 gget() → blocks (buffer empty)
          producer gput(0) → was_empty=True  → schedules _GET_READY
          producer gput(1) → was_empty=False → no _GET_READY scheduled
          _GET_READY fires  → wake c1 with 0; buffer=[1], getters=[c2]
          line 118 fires    → schedule another _GET_READY
          _GET_READY fires  → wake c2 with 1
        '''
        sim, q = _make()
        got = []

        def getter(label):
            item = yield from q.gget()
            got.append((label, item))

        def producer():
            yield from q.gput(0)
            yield from q.gput(1)

        sim.schedule(0, getter('c1'))
        sim.schedule(0, getter('c2'))
        sim.schedule(0, producer())
        sim.run()
        self.assertEqual(got, [('c1', 0), ('c2', 1)])


# ---------------------------------------------------------------------------
# Blocking put (gput)
# ---------------------------------------------------------------------------

class TestLiteQueueGput(unittest.TestCase):

    def test1_gput_returns_immediately_when_space_available(self):
        '''gput on a queue with space never suspends the caller.'''
        sim, q = _make()
        results = []

        def process():
            item = yield from q.gput(42)
            results.append(item)

        sim.schedule(0, process())
        sim.run()
        self.assertEqual(results, [42])
        self.assertEqual(len(q), 1)

    def test2_gput_blocks_when_full_consumer_first(self):
        '''Consumer dequeues first, unblocking a waiting producer.'''
        sim, q = _make(capacity=1)
        log = []

        def producer():
            for i in range(3):
                yield from q.gput(i)
                log.append(f'put {i}')

        def consumer():
            for _ in range(3):
                item = yield from q.gget()
                log.append(f'got {item}')

        sim.schedule(0, consumer())
        sim.schedule(0, producer())
        sim.run()
        self.assertEqual(log, ['put 0', 'got 0', 'put 1', 'got 1', 'put 2', 'got 2'])

    def test3_gput_blocks_when_full_producer_first(self):
        '''Producer enqueues first then blocks; consumer drains and unblocks it.'''
        sim, q = _make(capacity=1)
        log = []

        def producer():
            for i in range(3):
                yield from q.gput(i)
                log.append(f'put {i}')

        def consumer():
            for _ in range(3):
                item = yield from q.gget()
                log.append(f'got {item}')

        sim.schedule(0, producer())
        sim.schedule(0, consumer())
        sim.run()
        self.assertEqual(log, ['put 0', 'got 0', 'put 1', 'got 1', 'put 2', 'got 2'])

    def test4_multiple_putters_one_slot(self):
        '''Three producers all block on a capacity=1 queue; consumer drains all.'''
        sim, q = _make(capacity=1)
        received = []

        def putter(val):
            yield from q.gput(val)

        def drainer():
            for _ in range(3):
                received.append((yield from q.gget()))

        sim.schedule(0, putter(10))
        sim.schedule(0, putter(20))
        sim.schedule(0, putter(30))
        sim.schedule(0, drainer())
        sim.run()
        self.assertEqual(sorted(received), [10, 20, 30])


# ---------------------------------------------------------------------------
# Mixed / stress scenarios
# ---------------------------------------------------------------------------

class TestLiteQueueMixed(unittest.TestCase):

    def test1_multiple_getters_multiple_putters_bounded(self):
        '''N producers and N consumers on a capacity=1 queue exchange N items.'''
        sim, q = _make(capacity=1)
        N = 5
        received = []

        def putter(val):
            yield from q.gput(val)

        def getter():
            received.append((yield from q.gget()))

        for i in range(N):
            sim.schedule(0, getter())
        for i in range(N):
            sim.schedule(0, putter(i))
        sim.run()
        self.assertEqual(sorted(received), list(range(N)))

    def test2_large_pipeline_bounded(self):
        '''Single producer / consumer with many items and capacity=1.'''
        sim, q = _make(capacity=1)
        N = 200
        received = []

        def producer():
            for i in range(N):
                yield from q.gput(i)

        def consumer():
            for _ in range(N):
                received.append((yield from q.gget()))

        sim.schedule(0, producer())
        sim.schedule(0, consumer())
        sim.run()
        self.assertEqual(received, list(range(N)))


if __name__ == '__main__':
    unittest.main()
