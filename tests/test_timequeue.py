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
from dssim.timequeue import TimeQueue
from dssim.pubsub import void_consumer

class TestTimeQueue(unittest.TestCase):
    ''' Test the time queue class behavior '''

    def setUp(self):
        self.tq = TimeQueue()

    def _get_len(self):
        return len(self.tq), len(self.tq.timequeue), len(self.tq.timequeue)

    def test0_init(self):
        ''' Assert initialization behavior '''
        self.assertEqual(self._get_len(), (0, 0, 0))

    def test1_put_get(self):
        ''' Test adding an event '''
        self.tq.add_element(0.123, 'An element')
        self.assertEqual(self._get_len(), (1, 1, 1))
        self.assertEqual(self.tq.timequeue[0], 0.123)
        self.assertEqual(self.tq.elementqueue[0], 'An element')
        time, element = self.tq.get0()
        self.assertEqual((time, element), (0.123, 'An element'))
        time, element = self.tq.pop()
        self.assertEqual((time, element), (0.123, 'An element'))
        self.assertEqual(self._get_len(), (0, 0, 0))
        time, element = self.tq.get0()
        self.assertEqual((time, element), (float("inf"), (void_consumer, None)))

    def test2_insert(self):
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

    def test3_insert_infinite_time(self):
        ''' The elements with infinite time are valid elements '''
        self.tq.add_element(float('inf'), 'First element')
        self.tq.add_element(10, 'Second element')
        time, element = self.tq.pop()
        self.assertEqual((time, element), (10, 'Second element'))
        self.assertEqual(self._get_len(), (1, 1, 1))
        time, element = self.tq.pop()
        self.assertEqual((time, element), (float('inf'), 'First element'))
        self.assertEqual(self._get_len(), (0, 0, 0))

    def test4_insert_elements_with_equal_time(self):
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

    def test5_delete_cond(self):
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

    def test6_delete_val(self):
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
