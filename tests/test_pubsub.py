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
from dssim.simulation import DSProcess
from dssim.pubsub import DSConsumer, DSProducer

class SimMock:
    pass

class SomeObj:
    pass

class SomeIterableObj:
    def __iter__(self):
        pass

__all__ = ['TestPubSub']


class TestConsumer(unittest.TestCase):
    ''' Test the DSConsumer '''

    def test0_consumer(self):
        my_consumer_fcn = Mock()
        c = DSConsumer(my_consumer_fcn)
        c.notify(data=1)
        my_consumer_fcn.assert_called_once_with(data=1)
        my_consumer_fcn.reset_mock()
        c.notify(data=0)
        my_consumer_fcn.assert_called_once_with(data=0)
        my_consumer_fcn.reset_mock()

    def test1_consumer(self):
        class ObjWithCallback:
            def cb(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs
        obj = ObjWithCallback()
        c = DSConsumer(obj.cb)
        c.notify(data=1)
        self.assertEqual(obj.args, ())
        self.assertEqual(obj.kwargs, {'data': 1})
        c.notify(data=0)
        self.assertEqual(obj.args, ())
        self.assertEqual(obj.kwargs, {'data': 0})

    def test2_consumer_with_filter(self):
        my_consumer_fcn = Mock()
        c = DSConsumer(my_consumer_fcn, cond=lambda e:e['data'] > 0)
        c.notify(data=1)
        my_consumer_fcn.assert_called_once_with(data=1)
        my_consumer_fcn.reset_mock()
        c.notify(data=0)
        my_consumer_fcn.notify.assert_not_called()
        my_consumer_fcn.reset_mock()

class TestSubscriber(unittest.TestCase):
    ''' TODO: test registratrion, deregistration, event data path when registered '''
    pass


class TestProducer(unittest.TestCase):
    ''' Test the DSProducer '''

    def __my_process_consumer(self):
        event = yield  # wait forever

    def setUp(self):
        self.consumer_called = []
        self.sim = SimMock()
        self.sim.time_process = SimMock()
        self.sim.signal = Mock(return_value=True) # always returns true
        self.sim.schedule = Mock(return_value=1000) # new process id retval
        self.sim.schedule_event = Mock()

    def test0_producer_add(self):
        p = DSProducer(sim=self.sim)
        process = self.__my_process_consumer()
        c0 = DSProcess(process, start=True, sim=self.sim)
        c1 = DSProcess(process, start=True, sim=self.sim)
        p.add_subscriber(subscriber=c0)
        self.assertEqual(p.subs, {'pre': {False: {}, True: {}}, 'act': {False: {}, True: {c0: 1}}, 'post': {False: {}, True: {}}})
        p.add_subscriber(subscriber=c1)
        self.assertEqual(p.subs, {'pre': {False: {}, True: {}}, 'act': {False: {}, True: {c0: 1, c1: 1}}, 'post': {False: {}, True: {}}})
        p.add_subscriber(subscriber=c0)
        self.assertEqual(p.subs, {'pre': {False: {}, True: {}}, 'act': {False: {}, True: {c0: 2, c1: 1}}, 'post': {False: {}, True: {}}})
        p.add_subscriber(phase='pre', subscriber=c0)
        self.assertEqual(p.subs, {'pre': {False: {}, True: {c0: 1}}, 'act': {False: {}, True: {c0: 2, c1: 1}}, 'post': {False: {}, True: {}}})
        p.add_subscriber(phase='post', subscriber=c1)
        self.assertEqual(p.subs, {'pre': {False: {}, True: {c0: 1}}, 'act': {False: {}, True: {c0: 2, c1: 1}}, 'post': {False: {}, True: {c1: 1}}})
        c2 = lambda e: False
        c3 = lambda e: True
        p.add_subscriber(phase='post', subscriber=c2)
        self.assertEqual(p.subs, {'pre': {False: {}, True: {c0: 1}}, 'act': {False: {}, True: {c0: 2, c1: 1}}, 'post': {False: {c2: 1}, True: {c1: 1}}})
        p.add_subscriber(phase='post', subscriber=c2)
        self.assertEqual(p.subs, {'pre': {False: {}, True: {c0: 1}}, 'act': {False: {}, True: {c0: 2, c1: 1}}, 'post': {False: {c2: 2}, True: {c1: 1}}})
        p.add_subscriber(phase='pre', subscriber=c3)
        self.assertEqual(p.subs, {'pre': {False: {c3: 1}, True: {c0: 1}}, 'act': {False: {}, True: {c0: 2, c1: 1}}, 'post': {False: {c2: 2}, True: {c1: 1}}})

    def test1_producer_remove(self):
        p = DSProducer(sim=self.sim)
        c0 = SomeObj()
        c0.notify = Mock(return_value=False)
        c1 = SomeObj()
        c1.notify = Mock(return_value=False)
        p.subs = {'pre': {False: {}, True: {}}, 'act': {False: {c0: 1}, True: {}}, 'post': {False: {}, True: {}}}
        p.remove_subscriber(subscriber=c0)
        self.assertEqual(p.subs, {'pre': {False: {}, True: {}}, 'act': {False: {c0: 0}, True: {}}, 'post': {False: {}, True: {}}})
        p.signal()
        self.assertEqual(p.subs, {'pre': {False: {}, True: {}}, 'act': {False: {}, True: {}}, 'post': {False: {}, True: {}}})

        p.subs = {'pre': {False: {}, True: {}}, 'act': {False: {c0: 1, c1: 1}, True: {}}, 'post': {False: {}, True: {}}}
        p.remove_subscriber(subscriber=c0)
        self.assertEqual(p.subs, {'pre': {False: {}, True: {}}, 'act': {False: {c0: 0, c1:1}, True: {}}, 'post': {False: {}, True: {}}})
        p.signal()
        self.assertEqual(p.subs, {'pre': {False: {}, True: {}}, 'act': {False: {c1: 1}, True: {}}, 'post': {False: {}, True: {}}})

        p.subs = {'pre': {False: {c0: 1, c1: 1}, True: {}}, 'act': {False: {c0: 1, c1: 1}, True: {}}, 'post': {False: {}, True: {}}}
        p.remove_subscriber(subscriber=c0)
        self.assertEqual(p.subs, {'pre': {False: {c0: 1, c1: 1}, True: {}}, 'act': {False: {c0: 0, c1: 1}, True: {}}, 'post': {False: {}, True: {}}})
        p.signal()
        self.assertEqual(p.subs, {'pre': {False: {c0: 1, c1: 1}, True: {}}, 'act': {False: {c1: 1}, True: {}}, 'post': {False: {}, True: {}}})
        p.remove_subscriber(phase='pre', subscriber=c1)
        self.assertEqual(p.subs, {'pre': {False: {c0: 1, c1: 0}, True: {}}, 'act': {False: {c1: 1}, True: {}}, 'post': {False: {}, True: {}}})
        p.signal()
        self.assertEqual(p.subs, {'pre': {False: {c0: 1}, True: {}}, 'act': {False: {c1: 1}, True: {}}, 'post': {False: {}, True: {}}})

        c2 = SomeIterableObj()
        p.subs = {'pre': {False: {c0: 1}, True: {c2: 1}}, 'act': {False: {c1: 1}, True: {c2: 1}}, 'post': {False: {}, True: {}}}
        p.remove_subscriber(phase='pre', subscriber=c2)
        self.assertEqual(p.subs, {'pre': {False: {c0: 1}, True: {c2: 0}}, 'act': {False: {c1: 1}, True: {c2: 1}}, 'post': {False: {}, True: {}}})
        p.remove_subscriber(subscriber=c2)
        self.assertEqual(p.subs, {'pre': {False: {c0: 1}, True: {c2: 0}}, 'act': {False: {c1: 1}, True: {c2: 0}}, 'post': {False: {}, True: {}}})

    def test2_producer_signal_act_retval(self):
        self._calls = 0
        notify_fcn = Mock(return_value=False)
        p = DSProducer(sim=self.sim)
        c0 = SomeObj()
        c0.notify = lambda e: notify_fcn('a')
        c1 = SomeObj()
        c1.notify = lambda e: notify_fcn('b')
        p.add_subscriber(c0)
        p.add_subscriber(c1)
        p.signal(e=1)
        notify_fcn.assert_has_calls([call('a'), call('b')])

        notify_fcn = Mock(return_value=True)       
        p = DSProducer(sim=self.sim)
        c0 = SomeObj()
        c0.notify = lambda e: notify_fcn('a')
        c1 = SomeObj()
        c1.notify = lambda e: notify_fcn('b')
        p.add_subscriber(c0)
        p.add_subscriber(c1)
        p.signal(e=2)
        notify_fcn.assert_has_calls([call('a')])

    def test3_producer_signal_act(self):
        p = DSProducer(sim=self.sim)
        c0 = SomeObj()
        c0.notify = Mock(return_value=False)
        c1 = SomeObj()
        c1.notify = Mock(return_value=True)  # stops the further notifications
        c0.notify.reset_mock()
        p.add_subscriber(subscriber=c0)
        p.signal()
        c0.notify.assert_called_once()
        c0.notify.reset_mock()
        p.add_subscriber(subscriber=c0)  # 2 times a subscriber
        p.signal()
        c0.notify.assert_called_once()

    def test4_producer_signal_pre(self):
        p = DSProducer(sim=self.sim)
        c0 = SomeObj()
        c0.notify = Mock(return_value=False)
        c1 = SomeObj()
        c1.notify = Mock(return_value=True)  # stops the further notifications
        c0.notify.reset_mock()
        p.add_subscriber(phase='pre', subscriber=c0)
        p.signal()
        c0.notify.assert_called_once()
        c0.notify.reset_mock()
        p.add_subscriber(phase='pre', subscriber=c0)  # 2 times a subscriber
        p.signal()
        c0.notify.assert_called_once()

    def test5_producer_signal_post(self):
        p = DSProducer(sim=self.sim)
        c0 = SomeObj()
        c0.notify = Mock(return_value=False)
        c1 = SomeObj()
        c1.notify = Mock(return_value=True)  # stops the further notifications
        c0.notify.reset_mock()
        p.add_subscriber(phase='post', subscriber=c0)
        p.signal()
        c0.notify.assert_called_once()
        c0.notify.reset_mock()
        p.add_subscriber(phase='post', subscriber=c0)  # 2 times a subscriber
        p.signal()
        c0.notify.assert_called_once()

    def test6_producer_signal_same(self):
        c0 = SomeObj()
        c0.notify = Mock(return_value=False)
        c1 = SomeObj()
        c1.notify = Mock(return_value=True)  # stops the further notifications

        tests = ( 
            ('pre', 'c0c1', True, True),
            ('pre', 'c1c0', True, True),
            ('act', 'c0c1', True, True),
            ('act', 'c1c0', False, True),
            ('post', 'c0c1', True, True),
            ('post', 'c1c0', True, True),
        )
        for phase, order, c0_called, c1_called in tests:
            c0.notify.reset_mock()
            c1.notify.reset_mock()
            p = DSProducer(sim=self.sim)
            if order == 'c0c1':
                p.add_subscriber(phase=phase, subscriber=c0)
                p.add_subscriber(phase=phase, subscriber=c1)
            else:
                p.add_subscriber(phase=phase, subscriber=c1)
                p.add_subscriber(phase=phase, subscriber=c0)
            p.signal()
            if c0_called:
                c0.notify.assert_called_once()
            else:
                c0.notify.assert_not_called()
            if c1_called:
                c1.notify.assert_called_once()
            else:
                c1.notify.assert_not_called()

    def test7_producer_signal_combi(self):
        c0 = SomeObj()
        c0.notify = Mock(return_value=False)
        c1 = SomeObj()
        c1.notify = Mock(return_value=True)  # stops the further notifications

        tests = ( 
            ('pre', 'act', True, True),
            ('act', 'pre', True, True),
            ('pre', 'post', True, True),
            ('post', 'pre', True, True),
            ('act', 'post', True, True),
            ('post', 'act', False, True),
        )
        for c0_phase, c1_phase, c0_called, c1_called in tests:
            c0.notify.reset_mock()
            c1.notify.reset_mock()
            p = DSProducer(sim=self.sim)
            p.add_subscriber(phase=c0_phase, subscriber=c0)
            p.add_subscriber(phase=c1_phase, subscriber=c1)
            p.signal()
            if c0_called:
                c0.notify.assert_called_once()
            else:
                c0.notify.assert_not_called()
            if c1_called:
                c1.notify.assert_called_once()
            else:
                c1.notify.assert_not_called()

    def test8_producer_add_subscriber_in_notify_hook(self):
        ''' Test the behavior of signal function when notify handler adds a subscriber '''
        p = DSProducer(sim=self.sim)
        c0 = SomeObj()
        c1 = SomeObj()
        c0.notify = Mock(return_value=False)
        c1.notify = lambda: p.add_subscriber(subscriber=c0)
        p.add_subscriber(subscriber=c0)
        p.add_subscriber(subscriber=c1)
        self.assertEqual(p.subs, {'pre': {False: {}, True: {}}, 'act': {False: {c0: 1, c1: 1}, True: {}}, 'post': {False: {}, True: {}}})
        p.signal()
        c0.notify.assert_called_once()
        self.assertEqual(p.subs, {'pre': {False: {}, True: {}}, 'act': {False: {c0: 2, c1: 1}, True: {}}, 'post': {False: {}, True: {}}})


    def test9_producer_remove_subscriber_in_notify_hook(self):
        ''' Test the behavior of signal function when notify handler removes a subscriber '''
        p = DSProducer(sim=self.sim)
        c0 = SomeObj()
        c1 = SomeObj()
        c0.notify = Mock(return_value=False)
        c1.notify = lambda: p.remove_subscriber(subscriber=c0)
        p.add_subscriber(subscriber=c0)
        p.add_subscriber(subscriber=c1)
        self.assertEqual(p.subs, {'pre': {False: {}, True: {}}, 'act': {False: {c0: 1, c1: 1}, True: {}}, 'post': {False: {}, True: {}}})
        p.signal()
        c0.notify.assert_called_once()
        self.assertEqual(p.subs, {'pre': {False: {}, True: {}}, 'act': {False: {c1: 1}, True: {}}, 'post': {False: {}, True: {}}})
