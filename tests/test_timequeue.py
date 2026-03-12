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
Tests for timequeue module
'''
import unittest
from collections import deque
from dssim.timequeue import TimeQueue, NowQueue

class TestTimeQueue(unittest.TestCase):
    '''Test the TimeQueue API behaviour.'''

    def setUp(self) -> None:
        self.tq = TimeQueue()

    def _pop_one(self):
        '''Pop one event using only public TimeQueue API.'''
        t = self.tq.get_first_time()
        bucket = self.tq.pop_first_bucket()
        element = bucket.popleft()
        if bucket:
            self.tq.insertleft(t, bucket)
        return t, element

    def test1_init_empty(self):
        self.assertFalse(self.tq)
        self.assertEqual(self.tq.event_count(), 0)
        self.assertEqual(len(self.tq._queue), 0)

    def test2_add_element_builds_sorted_buckets(self):
        self.tq.add_element(10, 'a')
        self.tq.add_element(0, 'b')
        self.tq.add_element(5, 'c')
        self.tq.add_element(5, 'd')
        self.assertTrue(self.tq)
        self.assertEqual(self.tq.event_count(), 4)
        self.assertEqual([t for t, _ in self.tq._queue], [0, 5, 10])
        self.assertEqual([len(q) for _, q in self.tq._queue], [1, 2, 1])
        self.assertEqual(list(self.tq._queue[1][1]), ['c', 'd'])

    def test3_pop_one_respects_global_and_bucket_fifo(self):
        self.tq.add_element(10, 'a')
        self.tq.add_element(0, 'b')
        self.tq.add_element(5, 'c')
        self.tq.add_element(5, 'd')
        self.assertEqual(self._pop_one(), (0, 'b'))
        self.assertEqual(self._pop_one(), (5, 'c'))
        self.assertEqual(self._pop_one(), (5, 'd'))
        self.assertEqual(self._pop_one(), (10, 'a'))
        self.assertFalse(self.tq)
        self.assertEqual(self.tq.event_count(), 0)

    def test4_get_first_time_and_pop_first_bucket(self):
        self.tq.add_element(2, 'a')
        self.tq.add_element(2, 'b')
        self.tq.add_element(3, 'c')
        self.assertEqual(self.tq.get_first_time(), 2)
        bucket = self.tq.pop_first_bucket()
        self.assertEqual(list(bucket), ['a', 'b'])
        self.assertEqual(self.tq.event_count(), 1)
        self.assertEqual(self.tq.get_first_time(), 3)

    def test5_insertleft_merges_with_same_time_bucket(self):
        self.tq.add_element(1, 'a')
        self.tq.insertleft(1, deque(['b', 'c']))
        self.assertEqual([t for t, _ in self.tq._queue], [1])
        self.assertEqual(list(self.tq._queue[0][1]), ['a', 'b', 'c'])
        self.assertEqual(self.tq.event_count(), 3)

    def test6_insertleft_prepends_earlier_bucket(self):
        self.tq.add_element(5, 'x')
        self.tq.insertleft(1, deque(['a', 'b']))
        self.assertEqual([t for t, _ in self.tq._queue], [1, 5])
        self.assertEqual(self._pop_one(), (1, 'a'))
        self.assertEqual(self._pop_one(), (1, 'b'))
        self.assertEqual(self._pop_one(), (5, 'x'))

    def test7_insertleft_later_time_keeps_sorted_order(self):
        self.tq.add_element(1, 'a')
        self.tq.add_element(5, 'e')
        self.tq.insertleft(3, deque(['c', 'd']))
        self.assertEqual([t for t, _ in self.tq._queue], [1, 3, 5])
        self.assertEqual(self._pop_one(), (1, 'a'))
        self.assertEqual(self._pop_one(), (3, 'c'))
        self.assertEqual(self._pop_one(), (3, 'd'))
        self.assertEqual(self._pop_one(), (5, 'e'))

    def test8_infinite_time_is_valid(self):
        self.tq.add_element(float('inf'), 'later')
        self.tq.add_element(10, 'now')
        self.assertEqual(self._pop_one(), (10, 'now'))
        self.assertEqual(self._pop_one(), (float('inf'), 'later'))

    def test9_delete_sub_filters_all_matching_subscribers(self):
        sub_a, sub_b, sub_c = object(), object(), object()
        self.tq.add_element(2, (sub_a, {'a': 1, 'b': 2, 'c': 3}))
        self.tq.add_element(1, (sub_b, {'b': 1, 'c': 2, 'd': 3}))
        self.tq.add_element(3, (sub_c, {'x': 1, 'y': 2, 'z': 3}))
        self.tq.add_element(4, (sub_a, {'a': 10}))
        self.tq.delete_sub(sub_a)
        self.assertEqual(self.tq.event_count(), 2)
        time, element = self._pop_one()
        self.assertEqual((time, element), (1, (sub_b, {'b': 1, 'c': 2, 'd': 3})))
        time, element = self._pop_one()
        self.assertEqual((time, element), (3, (sub_c, {'x': 1, 'y': 2, 'z': 3})))
        self.tq.delete_sub(sub_b)
        self.assertEqual(self.tq.event_count(), 0)

    def test10_delete_val_filters_matching_values(self):
        self.tq.add_element(2, {'a': 1, 'b': 2, 'c': 3})
        self.tq.add_element(1, {'b': 1, 'c': 2, 'd': 3})
        self.tq.add_element(3, {'x': 1, 'y': 2, 'z': 3})
        self.tq.add_element(4, {'a': 1, 'b': 2, 'c': 3, 'x': -1, 'y': -2})
        self.tq.delete_val({'x': 1, 'y': 2, 'z': 3})
        self.assertEqual(self.tq.event_count(), 3)
        time, element = self._pop_one()
        self.assertEqual((time, element), (1, {'b': 1, 'c': 2, 'd': 3}))
        time, element = self._pop_one()
        self.assertEqual((time, element), (2, {'a': 1, 'b': 2, 'c': 3}))
        self.assertEqual(self.tq.event_count(), 1)
        self.tq.delete_val({'a': 100, 'b': 2, 'c': 3, 'x': -1, 'y': -2})
        self.assertEqual(self.tq.event_count(), 1)
        self.tq.delete_val({'a': 1, 'b': 2, 'c': 3, 'x': -1, 'y': -2})
        self.assertEqual(self.tq.event_count(), 0)

class TestNowQueue(unittest.TestCase):
    '''Test the NowQueue class behavior.'''

    def setUp(self):
        self.q = NowQueue()

    def test1_init(self):
        ''' Assert initialization — queue is empty '''
        self.assertEqual(len(self.q), 0)
        self.assertFalse(self.q)

    def test2_append_popleft(self):
        ''' Single item: append then popleft round-trips correctly '''
        self.q.append('a')
        self.assertEqual(len(self.q), 1)
        self.assertTrue(self.q)
        item = self.q.popleft()
        self.assertEqual(item, 'a')
        self.assertEqual(len(self.q), 0)
        self.assertFalse(self.q)

    def test3_fifo_order(self):
        ''' Multiple items are delivered in FIFO order '''
        self.q.append('first')
        self.q.append('second')
        self.q.append('third')
        self.assertEqual(len(self.q), 3)
        self.assertEqual(self.q.popleft(), 'first')
        self.assertEqual(self.q.popleft(), 'second')
        self.assertEqual(self.q.popleft(), 'third')
        self.assertEqual(len(self.q), 0)

    def test4_tuple_elements(self):
        ''' Stores (consumer, event) tuples as used by the simulator '''
        consumer_a, consumer_b = object(), object()
        self.q.append((consumer_a, 'event1'))
        self.q.append((consumer_b, 'event2'))
        c, e = self.q.popleft()
        self.assertIs(c, consumer_a)
        self.assertEqual(e, 'event1')
        c, e = self.q.popleft()
        self.assertIs(c, consumer_b)
        self.assertEqual(e, 'event2')

    def test5_filter_constructor(self):
        ''' NowQueue(generator) filters items — used by cleanup() '''
        consumer_a, consumer_b = object(), object()
        self.q.append((consumer_a, 'ev1'))
        self.q.append((consumer_b, 'ev2'))
        self.q.append((consumer_a, 'ev3'))
        # Keep only items NOT for consumer_a (same pattern as sim.cleanup)
        filtered = NowQueue(item for item in self.q if item[0] is not consumer_a)
        self.assertEqual(len(filtered), 1)
        c, e = filtered.popleft()
        self.assertIs(c, consumer_b)
        self.assertEqual(e, 'ev2')
