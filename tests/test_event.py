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
from unittest.mock import Mock, call
from dssim.components.event import Event

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

class TestEvent(unittest.TestCase):
    ''' Test Queue '''

    def setUp(self):
        self.sim = SimMock()
        self.sim.signal = Mock(return_value=True)  # always returns true
        self.sim.schedule = Mock(return_value=1000)  # new process id retval
        self.sim.parent_process = 'parent_process'

    def test0_event_signal(self):
        e = Event(sim=self.sim)
        self.assertEqual(e.waiting_tasks, [])
        self.assertEqual(e.signalled, False)
        e.signal()
        self.sim.signal.assert_not_called()
        self.assertEqual(e.signalled, True)
        e.clear()
        self.sim.signal.assert_not_called()
        self.assertEqual(e.signalled, False)

    def test1_event_wait(self):
        e = Event(sim=self.sim)
        e.signal()
        self.assertEqual(e.signalled, True)
        obj = get_object(e.wait())
        self.sim.signal.assert_not_called()
        self.assertEqual(e.signalled, True)
        self.assertEqual(e.waiting_tasks, [])

    def test2_event_wait_blocking(self):
        e = Event(sim=self.sim)
        self.sim.signal = Mock()
        self.sim.wait = wait_mock_with_one_dummy
        self.assertEqual(e.signalled, False)
        get_generator = e.wait()
        objR = get_object(get_generator)
        self.sim.signal.assert_not_called()
        self.assertEqual(objR, 'WaitMockDummyReturn')
        self.assertEqual(len(e.waiting_tasks), 1)
        e.signal()
        self.sim.signal.assert_called_once_with('parent_process', signalled=True)
        self.assertEqual(e.signalled, True)
        objR = get_object(get_generator)
        self.assertEqual(objR, 'WaitMockReturn2')
        self.assertEqual(len(e.waiting_tasks), 0)

    def test3_event_wait_blocking_more(self):
        e = Event(sim=self.sim)
        self.sim.signal = Mock()
        self.sim.wait = wait_mock_with_one_dummy
        get_generator0 = e.wait()
        get_generator1 = e.wait()
        objR = get_object(get_generator0)
        objR = get_object(get_generator1)
        self.sim.signal.assert_not_called()
        self.assertEqual(len(e.waiting_tasks), 2)
        e.signal()
        self.sim.signal.assert_has_calls([call('parent_process', signalled=True)] * 2) 
        self.assertEqual(e.signalled, True)
        objR = get_object(get_generator0)
        self.assertEqual(objR, 'WaitMockReturn2')
        objR = get_object(get_generator1)
        self.assertEqual(objR, 'WaitMockReturn2')
        self.assertEqual(len(e.waiting_tasks), 0)
        