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
Tests for pubsub module
'''
import unittest
from unittest.mock import Mock
from dssim.components.queue import Queue

class SimMock:
    pass

class SomeObj:
    pass

def get_object(generator):
    try:
        obj = next(generator)
    except StopIteration as e:
        obj = e.value  # Python internal: a value returned by generator
    return obj

def wait_mock(self, timeout=float('inf'), cond=True):
    if False:
        yield something  # this is to make it generator
    return "WaitMockReturn1"

def wait_mock_with_one_dummy(self, timeout=float('inf'), cond=True):
    yield "WaitMockDummyReturn"  # this is dummy one call. It is needed to keep get() still not return with value
    return "WaitMockReturn2"


__all__ = ['TestQueue']

class TestQueue(unittest.TestCase):
    ''' Test Queue '''

    def setUp(self):
        self.consumer_called = []
        self.sim = SimMock()
        self.sim.signal = Mock(return_value=True)  # always returns true
        self.sim.schedule = Mock(return_value=1000)  # new process id retval
        self.sim.parent_process = 'parent_process'

    def test0_queue_put(self):
        q = Queue(sim=self.sim)
        obj0 = SomeObj()
        q.put(o=obj0)
        self.assertEqual(len(q.queue), 1)
        self.assertEqual(q.queue, [{'o': obj0}])
        obj1 = SomeObj()
        q.put(o=obj1)
        self.assertEqual(len(q.queue), 2)
        self.assertEqual(q.queue, [{'o': obj0}, {'o': obj1}])

    def test1_queue_get(self):
        q = Queue(sim=self.sim)
        obj0 = SomeObj()
        q.put(o=obj0)
        self.assertEqual(len(q.queue), 1)
        obj1 = get_object(q.get())
        self.assertEqual({'o': obj0}, obj1)
        self.assertEqual(len(q.queue), 0)

    def test2_queue_get_order(self):
        q = Queue(sim=self.sim)
        obj0 = SomeObj()
        q.put(o=obj0)
        obj1 = SomeObj()
        q.put(o=obj1)
        self.assertEqual(len(q.queue), 2)
        objR = get_object(q.get())
        self.assertEqual({'o': obj0}, objR)
        self.assertEqual(len(q.queue), 1)

    @unittest.skip('The following test is not a supported use case')
    def test3_queue_get_wait(self):
        '''
        This test and test4 are satisfying the condition:
        if we call get(), we should be blocked and after put we should unblock the get.

        However, this is the situation we can achieve with mocks:

        1. we call first get()
        1.1 mocked wait() will return an object
        1.2 get removes itself from the queue
        2. a call put() will not wake up any process, because the get in (1) was satisfied

        or

        1. we call first get()
        1.1 mocked wait() will yield an object
        1.2 get will NOT remove itself from the queue
        2. a call put() will wake the waiting process
        3. the following get() will return the next object
        '''
        q = Queue(sim=self.sim)
        self.sim.signal = Mock()
        self.sim.wait = wait_mock
        objR = get_object(q.get())
        self.assertEqual(objR, 'WaitMockReturn1')
        obj0 = SomeObj()
        q.put(o=obj0)
        self.sim.signal.assert_not_called()
        objR = get_object(q.get())
        self.assertEqual(objR, {'o': obj0})

    def test4_queue_get_wait(self):
        q = Queue(sim=self.sim)
        self.sim.signal = Mock()
        self.sim.wait = wait_mock_with_one_dummy
        # here we make sure that this get will not run the requested task removal
        get_generator = q.get()
        objR = get_object(get_generator)
        self.sim.signal.assert_not_called()
        self.assertEqual(objR, 'WaitMockDummyReturn')
        obj0 = SomeObj()
        q.put(o=obj0)
        self.sim.signal.assert_called_once()
        objR = get_object(get_generator)
        self.assertEqual(objR, 'WaitMockReturn2')
        