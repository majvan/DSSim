# Copyright 2020 NXP Semiconductors
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
from dssim.timequeue import TimeQueue, ZeroTimeQueue, _void_subscriber

class TestTimeQueue(unittest.TestCase):
    ''' Test the time queue class behavior '''

    def setUp(self):
        self.tq = TimeQueue()

    def _get_len(self):
        return len(self.tq), len(self.tq._queue), len(self.tq._queue)

    def test1_init(self):
        ''' Assert initialization behavior '''
        self.assertEqual(self._get_len(), (0, 0, 0))

    def test2_put_get(self):
        ''' Test adding an event '''
        self.tq.add_element(0.123, 'An element')
        self.assertEqual(self._get_len(), (1, 1, 1))
        self.assertEqual(self.tq._queue[0][0], 0.123)
        self.assertEqual(self.tq._queue[0][1], 'An element')
        time, element = self.tq.get0()
        self.assertEqual((time, element), (0.123, 'An element'))
        time, element = self.tq.pop()
        self.assertEqual((time, element), (0.123, 'An element'))
        self.assertEqual(self._get_len(), (0, 0, 0))
        time, element = self.tq.get0()
        self.assertEqual((time, element), (float("inf"), (_void_subscriber, None)))

    def test3_insert(self):
        ''' Test inserting an event '''
        self.tq.add_element(10, 'First element')
        self.tq.add_element(5, 'Second element')
        self.tq.add_element(0, 'Third element')
        time, element = self.tq.pop()
        self.assertEqual((time, element), (0, 'Third element'))
        time, element = self.tq.pop()
        self.assertEqual((time, element), (5, 'Second element'))
        time, element = self.tq.pop()
        self.assertEqual((time, element), (10, 'First element'))
        self.assertEqual(self._get_len(), (0, 0, 0))

        self.tq.add_element(10, '1st element')
        self.tq.add_element(0, '2nd element')
        self.tq.add_element(5, '3rd element')
        time, element = self.tq.pop()
        self.assertEqual((time, element), (0, '2nd element'))
        time, element = self.tq.pop()
        self.assertEqual((time, element), (5, '3rd element'))
        time, element = self.tq.pop()
        self.assertEqual((time, element), (10, '1st element'))
        self.assertEqual(self._get_len(), (0, 0, 0))

    def test4_insert_infinite_time(self):
        ''' The elements with infinite time are valid elements '''
        self.tq.add_element(float('inf'), 'First element')
        self.tq.add_element(10, 'Second element')
        time, element = self.tq.pop()
        self.assertEqual((time, element), (10, 'Second element'))
        self.assertEqual(self._get_len(), (1, 1, 1))
        time, element = self.tq.pop()
        self.assertEqual((time, element), (float('inf'), 'First element'))
        self.assertEqual(self._get_len(), (0, 0, 0))

    def test5_insert_elements_with_equal_time(self):
        ''' The elements with the same time shall be inserted in FIFO order '''
        self.tq.add_element(10, '1st element')
        self.tq.add_element(0, '2nd element')
        self.tq.add_element(5, '3rd element')
        self.tq.add_element(5, '4th element')
        self.tq.add_element(5, '5th element')
        time, element = self.tq.pop()
        self.assertEqual((time, element), (0, '2nd element'))
        time, element = self.tq.pop()
        self.assertEqual((time, element), (5, '3rd element'))
        time, element = self.tq.pop()
        self.assertEqual((time, element), (5, '4th element'))
        time, element = self.tq.pop()
        self.assertEqual((time, element), (5, '5th element'))
        time, element = self.tq.pop()
        self.assertEqual((time, element), (10, '1st element'))
        self.assertEqual(self._get_len(), (0, 0, 0))

    def test6_delete_cond(self):
        ''' Assert deleting an event '''
        self.tq.add_element(2, {'a': 1, 'b': 2, 'c': 3})
        self.tq.add_element(1, {'b': 1, 'c': 2, 'd': 3})
        self.tq.add_element(3, {'x': 1, 'y': 2, 'z': 3})
        self.tq.add_element(4, {'a': 1, 'b': 2, 'c': 3, 'x': -1, 'y': -2})
        self.tq.delete_cond(cond=lambda e:'x' in e)
        self.assertEqual(len(self.tq), 2)
        time, element = self.tq.pop()
        self.assertEqual((time, element), (1, {'b': 1, 'c': 2, 'd': 3}))
        time, element = self.tq.pop()
        self.assertEqual((time, element), (2, {'a': 1, 'b': 2, 'c': 3}))
        self.tq.delete_cond(lambda e:'b' in e)
        self.assertEqual(len(self.tq), 0)

    def test7_delete_val(self):
        ''' Assert deleting an event '''
        self.tq.add_element(2, {'a': 1, 'b': 2, 'c': 3})
        self.tq.add_element(1, {'b': 1, 'c': 2, 'd': 3})
        self.tq.add_element(3, {'x': 1, 'y': 2, 'z': 3})
        self.tq.add_element(4, {'a': 1, 'b': 2, 'c': 3, 'x': -1, 'y': -2})
        self.tq.delete_val({'x': 1, 'y': 2, 'z': 3})
        self.assertEqual(len(self.tq), 3)
        time, element = self.tq.pop()
        self.assertEqual((time, element), (1, {'b': 1, 'c': 2, 'd': 3}))
        time, element = self.tq.pop()
        self.assertEqual((time, element), (2, {'a': 1, 'b': 2, 'c': 3}))
        self.assertEqual(len(self.tq), 1)
        self.tq.delete_val({'a': 100, 'b': 2, 'c': 3, 'x': -1, 'y': -2})
        self.assertEqual(len(self.tq), 1)
        self.tq.delete_val({'a': 1, 'b': 2, 'c': 3, 'x': -1, 'y': -2})
        self.assertEqual(len(self.tq), 0)


class TestZeroTimeQueue(unittest.TestCase):
    ''' Test the ZeroTimeQueue class behavior '''

    def setUp(self):
        self.q = ZeroTimeQueue()

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
        ''' ZeroTimeQueue(generator) filters items — used by cleanup() '''
        consumer_a, consumer_b = object(), object()
        self.q.append((consumer_a, 'ev1'))
        self.q.append((consumer_b, 'ev2'))
        self.q.append((consumer_a, 'ev3'))
        # Keep only items NOT for consumer_a (same pattern as sim.cleanup)
        filtered = ZeroTimeQueue(item for item in self.q if item[0] is not consumer_a)
        self.assertEqual(len(filtered), 1)
        c, e = filtered.popleft()
        self.assertIs(c, consumer_b)
        self.assertEqual(e, 'ev2')
