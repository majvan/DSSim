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
from dssim.pubsub import DSConsumer, DSProcessConsumer, DSProducer

class SimMock:
    pass

class SomeObj:
    pass

__all__ = ['TestPubSub']

class TestConsumer(unittest.TestCase):
    ''' Test the DSConsumer '''

    def test0_consumer(self):
        obj = SomeObj()
        my_consumer_fcn = Mock()
        c = DSConsumer(obj, my_consumer_fcn)
        c.notify(data=1)
        my_consumer_fcn.assert_called_once_with(obj, data=1)
        my_consumer_fcn.reset_mock()
        c.notify(data=0)
        my_consumer_fcn.assert_called_once_with(obj, data=0)
        my_consumer_fcn.reset_mock()
        
    def test1_consumer_with_filter(self):
        obj = SomeObj()
        my_consumer_fcn = Mock()
        c = DSConsumer(obj, my_consumer_fcn, cond=lambda e:e['data'] > 0)
        c.notify(data=1)
        my_consumer_fcn.assert_called_once_with(obj, data=1)
        my_consumer_fcn.reset_mock()
        c.notify(data=0)
        my_consumer_fcn.notify.assert_not_called()
        my_consumer_fcn.reset_mock()

class TestProcessConsumer(unittest.TestCase):
    ''' Test the DSProcessConsumer '''

    def __my_process_consumer(self):
        while True:
            event = yield  # wait forever

    def setUp(self):
        self.consumer_called = []
        self.sim = SimMock()
        self.sim.signal = Mock(return_value=True)  # always returns true
        self.sim.schedule = Mock(return_value=1000)  # new process id retval
        self.sim.schedule_event = Mock()
        self.process = self.__my_process_consumer()

    def test0_process_consumer(self):
        c = DSProcessConsumer(self.process, start=True, sim=self.sim)
        self.sim.schedule.assert_called_once_with(0, self.process)
        self.sim.schedule.reset_mock()
        c.notify(data=1)
        self.sim.signal.assert_called_once_with(1000, data=1)
        self.sim.signal.reset_mock()
        c.notify(data=0)
        self.sim.signal.assert_called_once_with(1000, data=0)
        self.sim.signal.reset_mock()

    def test1_process_consumer(self):
        c = DSProcessConsumer(self.process, start=True, delay=5, sim=self.sim)
        self.sim.schedule.assert_called_once_with(5, self.process)
        self.sim.schedule.reset_mock()
        c.notify(data=1)
        self.sim.signal.assert_called_once_with(1000, data=1)
        self.sim.signal.reset_mock()

    @unittest.skip('Check this behavior: notifying a ProcessConsumer which has not started yet')
    def test2_process_consumer(self):
        c = DSProcessConsumer(self.process, start=False, sim=self.sim)
        self.sim.schedule.assert_not_called()
        self.sim.schedule.reset_mock()
        c.notify(data=1)
        self.sim.signal.assert_called_once_with(1000, data=1)
        self.sim.signal.reset_mock()

    def test3_process_consumer(self):
        with self.assertRaises(ValueError):
            c = DSProcessConsumer(self.process, start=False, delay=1)

class TestProducer(unittest.TestCase):
    ''' Test the DSProducer '''

    def __my_process_consumer(self):
        event = yield  # wait forever

    def setUp(self):
        self.consumer_called = []
        self.sim = SimMock()
        self.sim.signal = Mock(return_value=True) # always returns true
        self.sim.schedule = Mock(return_value=1000) # new process id retval
        self.sim.schedule_event = Mock()

    def test0_producer(self):
        p = DSProducer(sim=self.sim)
        process = self.__my_process_consumer()
        c = DSProcessConsumer(process, start=True, sim=self.sim)
        p.add_consumer(c)
        self.assertEqual(p.get_consumers(), [c,])
        p.signal(data=1)
        self.sim.signal.assert_called_once_with(1000, data=1)
        self.sim.signal.reset_mock()

    def test1_producer_more_consumers(self):
        obj0, obj1 = SomeObj(), SomeObj()
        my_consumer_fcn0, my_consumer_fcn1 = Mock(), Mock()
        p = DSProducer(sim=self.sim)
        c0 = DSConsumer(obj0, my_consumer_fcn0, sim=self.sim)
        c1 = DSConsumer(obj1, my_consumer_fcn1, sim=self.sim)
        self.assertEqual(len(p.get_consumers()), 0)
        p.add_consumer(c0)
        p.add_consumer(c1)
        self.assertEqual(p.get_consumers(), [c0, c1])
        p.signal(data=1)
        my_consumer_fcn0.assert_called_once_with(obj0, data=1)
        my_consumer_fcn1.assert_called_once_with(obj1, data=1)

    def test2_producer_with_scheduled_event(self):
        obj = SomeObj()
        my_consumer_fcn = Mock()
        c = DSConsumer(obj, my_consumer_fcn, sim=self.sim)
        p = DSProducer(sim=self.sim)
        self.assertEqual(len(p.get_consumers()), 0)
        p.add_consumer(c)
        self.assertEqual(p.get_consumers(), [c,])
        self.sim.schedule.assert_not_called()
        p.schedule(0.5, data=1)
        self.sim.schedule_event.assert_called_once_with(0.5, {'producer':p, 'data':1}, None)
        self.sim.schedule_event.reset_mock()

    def test3_producer_with_scheduled_event_single_process(self):
        obj = SomeObj()
        my_consumer_fcn = Mock()
        process = self.__my_process_consumer()
        c = DSProcessConsumer(process, sim=self.sim)
        p = DSProducer(sim=self.sim)
        self.assertEqual(len(p.get_consumers()), 0)
        p.add_consumer(c)
        self.assertEqual(p.get_consumers(), [c,])
        self.sim.schedule.assert_not_called()
        p.schedule(0.5, data=1)
        self.sim.schedule_event.assert_called_once_with(0.5, {'data':1}, process)
        self.sim.schedule_event.reset_mock()
