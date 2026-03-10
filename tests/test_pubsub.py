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
from dssim import DSProcess, DSCallback, DSKWCallback, DSSimulation
from dssim import DSProducer, NotifierDict, NotifierRoundRobin, NotifierPriority
from dssim.pubsub import NotifierRoundRobinItem

class SimMock:
    pass

class SomeObj:
    names = {}
    pass

class SomeIterableObj:
    def __iter__(self):
        pass

__all__ = ['TestPubSub']


class TestCallback(unittest.TestCase):
    ''' Test the DSCallback '''

    def test1_fcn(self):
        my_consumer_fcn = Mock()
        c = DSCallback(my_consumer_fcn, sim=SomeObj())
        c.send({'data': 1})
        my_consumer_fcn.assert_called_once_with({'data': 1})
        my_consumer_fcn.reset_mock()
        c.send({'data': 0})
        my_consumer_fcn.assert_called_once_with({'data': 0})
        my_consumer_fcn.reset_mock()

    def test2_kw_fcn(self):
        my_consumer_fcn = Mock()
        c = DSKWCallback(my_consumer_fcn, sim=SomeObj())
        c.send({'data': 1})
        my_consumer_fcn.assert_called_once_with(data=1)
        my_consumer_fcn.reset_mock()
        c.send({'data': 0})
        my_consumer_fcn.assert_called_once_with(data=0)
        my_consumer_fcn.reset_mock()

    def test3_method(self):
        class ObjWithCallback:
            def cb(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs
        obj = ObjWithCallback()
        c = DSCallback(obj.cb, sim=SomeObj())
        c.send({'data': 1})
        self.assertEqual(obj.args, ({'data': 1},))
        self.assertEqual(obj.kwargs, {})
        c.send({'data': 0})
        self.assertEqual(obj.args, ({'data': 0},))
        self.assertEqual(obj.kwargs, {})

    def test4_kw_method(self):
        class ObjWithCallback:
            def cb(self, data):
                self.args = []
                self.kwargs = {'data': data}
        obj = ObjWithCallback()
        c = DSKWCallback(obj.cb, sim=SomeObj())
        c.send({'data': 1})
        self.assertEqual(obj.args, [])
        self.assertEqual(obj.kwargs, {'data': 1})
        c.send({'data': 0})
        self.assertEqual(obj.args, [])
        self.assertEqual(obj.kwargs, {'data': 0})

    def test5_consumer_with_filter(self):
        my_consumer_fcn = Mock()
        c = DSCallback(my_consumer_fcn, cond=lambda e:e['data'] > 0, sim=SomeObj())
        c.send({'data': 1})
        my_consumer_fcn.assert_called_once_with({'data': 1})
        my_consumer_fcn.reset_mock()
        c.send({'data': 0})
        my_consumer_fcn.send.assert_not_called()
        my_consumer_fcn.reset_mock()

    def test6_kw_consumer_with_filter(self):
        my_consumer_fcn = Mock()
        c = DSKWCallback(my_consumer_fcn, cond=lambda e:e['data'] > 0, sim=SomeObj())
        c.send({'data': 1})
        my_consumer_fcn.assert_called_once_with(data=1)
        my_consumer_fcn.reset_mock()
        c.send({'data': 0})
        my_consumer_fcn.send.assert_not_called()
        my_consumer_fcn.reset_mock()

class SomeObj2:
    pass


class TestConsumer(unittest.TestCase):
    ''' Tests for DSConsumer.try_send '''

    def test1_try_send_checks_cond_before_dispatch(self):
        ''' try_send must check condition first; if rejected, send_object must not be called '''
        from unittest.mock import MagicMock
        sim = DSSimulation()
        sim.send_object = Mock()
        consumer = DSCallback(lambda e: True, sim=sim)
        consumer.meta = SomeObj2()
        consumer.meta.cond = MagicMock()
        consumer.meta.cond.check = Mock(return_value=(False, 'abc'))
        consumer.try_send(None)
        consumer.meta.cond.check.assert_called_once()
        sim.send_object.assert_not_called()

    def test2_try_send_dispatches_after_cond_passes(self):
        ''' try_send must call send_object with the event returned by cond.check '''
        from unittest.mock import MagicMock
        call_order = []
        sim = DSSimulation()
        def called_check_condition(*args, **kwargs):
            call_order.append(call('check_condition', *args, **kwargs))
            return (True, 'abc')
        def called_send_object(*args, **kwargs):
            call_order.append(call('send_object', *args, **kwargs))
            return True
        consumer = DSCallback(lambda e: True, sim=sim)
        consumer.meta = SomeObj2()
        consumer.meta.cond = MagicMock()
        consumer.meta.cond.check = Mock(side_effect=called_check_condition)
        sim.send_object = Mock(side_effect=called_send_object)
        consumer.try_send(None)
        consumer.meta.cond.check.assert_called_once()
        sim.send_object.assert_called_once()
        self.assertEqual(call_order, [call('check_condition', None), call('send_object', consumer, 'abc')])


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
        self.sim.send = Mock(return_value=True) # always returns true
        self.sim.schedule = Mock(return_value=1000) # new process id retval
        self.sim.schedule_event = Mock()
        self.sim.names = {}

    def _make_recorder(self, consumer_retval_pairs):
        '''Mock try_send on each consumer to record calls into a shared Mock.
        Replaces the old sim.try_send mock pattern now that try_send lives on DSConsumer.
        Returns the shared Mock so assert_has_calls / assert_not_called etc. still work.
        '''
        m = Mock()
        for consumer, retval in consumer_retval_pairs:
            def make_ts(c=consumer, rv=retval):
                def ts(event):
                    m(c, event)
                    return rv
                return ts
            consumer.try_send = make_ts()
        return m

    def test1_producer_add(self):
        p = DSProducer(sim=self.sim)
        process = self.__my_process_consumer()
        c0 = DSProcess(process, start=True, sim=self.sim)
        c1 = DSProcess(process, start=True, sim=self.sim)
        p.add_subscriber(subscriber=c0)
        self.assertEqual(p.subs[DSProducer.Phase.PRE].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.CONSUME].d, {c0: 1})
        self.assertEqual(p.subs[DSProducer.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.POST_MISS].d, {})
        p.add_subscriber(subscriber=c1)
        self.assertEqual(p.subs[DSProducer.Phase.PRE].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.CONSUME].d, {c0: 1, c1: 1})
        self.assertEqual(p.subs[DSProducer.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.POST_MISS].d, {})
        p.add_subscriber(subscriber=c0)
        self.assertEqual(p.subs[DSProducer.Phase.PRE].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.CONSUME].d, {c0: 2, c1: 1})
        self.assertEqual(p.subs[DSProducer.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.POST_MISS].d, {})
        p.add_subscriber(phase=DSProducer.Phase.PRE, subscriber=c0)
        self.assertEqual(p.subs[DSProducer.Phase.PRE].d, {c0: 1})
        self.assertEqual(p.subs[DSProducer.Phase.CONSUME].d, {c0: 2, c1: 1})
        self.assertEqual(p.subs[DSProducer.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.POST_MISS].d, {})
        p.add_subscriber(phase=DSProducer.Phase.POST_HIT, subscriber=c1)
        self.assertEqual(p.subs[DSProducer.Phase.PRE].d, {c0: 1})
        self.assertEqual(p.subs[DSProducer.Phase.CONSUME].d, {c0: 2, c1: 1})
        self.assertEqual(p.subs[DSProducer.Phase.POST_HIT].d, {c1: 1})
        self.assertEqual(p.subs[DSProducer.Phase.POST_MISS].d, {})
        p.add_subscriber(phase=DSProducer.Phase.POST_MISS, subscriber=c0)
        self.assertEqual(p.subs[DSProducer.Phase.PRE].d, {c0: 1})
        self.assertEqual(p.subs[DSProducer.Phase.CONSUME].d, {c0: 2, c1: 1})
        self.assertEqual(p.subs[DSProducer.Phase.POST_HIT].d, {c1: 1})
        self.assertEqual(p.subs[DSProducer.Phase.POST_MISS].d, {c0: 1})
        c2 = lambda e: False
        c3 = lambda e: True
        p.add_subscriber(phase=DSProducer.Phase.POST_HIT, subscriber=c2)
        self.assertEqual(p.subs[DSProducer.Phase.PRE].d, {c0: 1})
        self.assertEqual(p.subs[DSProducer.Phase.CONSUME].d, {c0: 2, c1: 1})
        self.assertEqual(p.subs[DSProducer.Phase.POST_HIT].d, {c2: 1, c1: 1})
        self.assertEqual(p.subs[DSProducer.Phase.POST_MISS].d, {c0: 1})
        p.add_subscriber(phase=DSProducer.Phase.POST_HIT, subscriber=c2)
        self.assertEqual(p.subs[DSProducer.Phase.PRE].d, {c0: 1})
        self.assertEqual(p.subs[DSProducer.Phase.CONSUME].d, {c0: 2, c1: 1})
        self.assertEqual(p.subs[DSProducer.Phase.POST_HIT].d, {c2: 2, c1: 1})
        self.assertEqual(p.subs[DSProducer.Phase.POST_MISS].d, {c0: 1})
        p.add_subscriber(phase=DSProducer.Phase.PRE, subscriber=c3)
        self.assertEqual(p.subs[DSProducer.Phase.PRE].d, {c3: 1, c0: 1})
        self.assertEqual(p.subs[DSProducer.Phase.CONSUME].d, {c0: 2, c1: 1})
        self.assertEqual(p.subs[DSProducer.Phase.POST_HIT].d, {c2: 2, c1: 1})
        self.assertEqual(p.subs[DSProducer.Phase.POST_MISS].d, {c0: 1})

    def test2_producer_remove(self):
        p = DSProducer(sim=DSSimulation())
        c0 = Mock()
        c0.send = Mock(return_value=False)
        c0.meta.cond = Mock()
        c0.meta.cond.check = Mock(return_value=(True, None))
        c0.get_cond = lambda: c0.meta.cond
        c1 = Mock()
        c1.send = Mock(return_value=False)
        c1.meta.cond = Mock()
        c1.meta.cond.check = Mock(return_value=(True, None))
        c1.get_cond = lambda: c0.meta.cond
        p.subs[DSProducer.Phase.PRE].d = {}
        p.subs[DSProducer.Phase.CONSUME].d = {c0: 1}
        p.subs[DSProducer.Phase.POST_HIT].d = {}
        p.subs[DSProducer.Phase.POST_MISS].d = {}
        p.remove_subscriber(subscriber=c0)
        self.assertEqual(p.subs[DSProducer.Phase.PRE].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.CONSUME].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.POST_MISS].d, {})
        p.send(None)
        self.assertEqual(p.subs[DSProducer.Phase.PRE].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.CONSUME].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.POST_MISS].d, {})

        p.subs[DSProducer.Phase.PRE].d = {}
        p.subs[DSProducer.Phase.CONSUME].d = {c0: 1, c1: 1}
        p.subs[DSProducer.Phase.POST_HIT].d = {}
        p.subs[DSProducer.Phase.POST_MISS].d = {}
        p.remove_subscriber(subscriber=c0)
        self.assertEqual(p.subs[DSProducer.Phase.PRE].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.CONSUME].d, {c1: 1})
        self.assertEqual(p.subs[DSProducer.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.POST_MISS].d, {})
        p.send(None)
        self.assertEqual(p.subs[DSProducer.Phase.PRE].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.CONSUME].d, {c1: 1})
        self.assertEqual(p.subs[DSProducer.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.POST_MISS].d, {})

        p.subs[DSProducer.Phase.PRE].d = {c0: 1, c1: 1}
        p.subs[DSProducer.Phase.CONSUME].d = {c0: 1, c1: 1}
        p.subs[DSProducer.Phase.POST_HIT].d = {}
        p.subs[DSProducer.Phase.POST_MISS].d = {}
        p.remove_subscriber(subscriber=c0)
        self.assertEqual(p.subs[DSProducer.Phase.PRE].d, {c0: 1, c1: 1})
        self.assertEqual(p.subs[DSProducer.Phase.CONSUME].d, {c1: 1})
        self.assertEqual(p.subs[DSProducer.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.POST_MISS].d, {})
        p.send(None)
        self.assertEqual(p.subs[DSProducer.Phase.PRE].d, {c0: 1, c1: 1})
        self.assertEqual(p.subs[DSProducer.Phase.CONSUME].d, {c1: 1})
        self.assertEqual(p.subs[DSProducer.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.POST_MISS].d, {})
        p.remove_subscriber(phase=DSProducer.Phase.PRE, subscriber=c1)
        self.assertEqual(p.subs[DSProducer.Phase.PRE].d, {c0: 1})
        self.assertEqual(p.subs[DSProducer.Phase.CONSUME].d, {c1: 1})
        self.assertEqual(p.subs[DSProducer.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.POST_MISS].d, {})
        p.send(None)
        self.assertEqual(p.subs[DSProducer.Phase.PRE].d, {c0: 1})
        self.assertEqual(p.subs[DSProducer.Phase.CONSUME].d, {c1: 1})
        self.assertEqual(p.subs[DSProducer.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.POST_MISS].d, {})

        c2 = SomeIterableObj()
        p.subs[DSProducer.Phase.PRE].d = {c0: 1, c2: 1}
        p.subs[DSProducer.Phase.CONSUME].d = {c1: 1, c2: 1}
        p.subs[DSProducer.Phase.POST_HIT].d = {}
        p.subs[DSProducer.Phase.POST_MISS].d = {}
        p.remove_subscriber(phase=DSProducer.Phase.PRE, subscriber=c2)
        self.assertEqual(p.subs[DSProducer.Phase.PRE].d, {c0: 1})
        self.assertEqual(p.subs[DSProducer.Phase.CONSUME].d, {c1: 1, c2: 1})
        self.assertEqual(p.subs[DSProducer.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.POST_MISS].d, {})
        p.remove_subscriber(subscriber=c2)
        self.assertEqual(p.subs[DSProducer.Phase.PRE].d, {c0: 1})
        self.assertEqual(p.subs[DSProducer.Phase.CONSUME].d, {c1: 1})
        self.assertEqual(p.subs[DSProducer.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.POST_MISS].d, {})

    def test3_producer_signal_act_retval(self):
        p = DSProducer(sim=self.sim)
        c0 = DSCallback(None, sim=self.sim)
        c1 = DSCallback(None, sim=self.sim)
        self.sim.try_send = self._make_recorder([(c0, False), (c1, False)])
        p.add_subscriber(c0)
        p.add_subscriber(c1)
        p.send(1)
        self.sim.try_send.assert_has_calls([call(c0, 1), call(c1, 1)])
        p = DSProducer(sim=self.sim)
        c0 = DSCallback(None, sim=self.sim)
        c1 = DSCallback(None, sim=self.sim)
        self.sim.try_send = self._make_recorder([(c0, True), (c1, True)])
        p.add_subscriber(c0)
        p.add_subscriber(c1)
        p.send(2)
        self.sim.try_send.assert_has_calls([call(c0, 2),])

    def test4_producer_signal_act(self):
        p = DSProducer(sim=self.sim)
        c0 = DSCallback(None, sim=self.sim)
        c1 = DSCallback(None, sim=self.sim)
        self.sim.try_send = self._make_recorder([(c0, True), (c1, True)])
        p.add_subscriber(c0)
        p.add_subscriber(c1)
        p.send(1)
        self.sim.try_send.assert_called_once_with(c0, 1)

        self.sim.try_send = self._make_recorder([(c0, True), (c1, True)])
        p.add_subscriber(subscriber=c0)  # 2 times a subscriber
        p.send(2)
        self.sim.try_send.assert_called_once_with(c0, 2)

    def test5_producer_signal_pre(self):
        p = DSProducer(sim=self.sim)
        c0 = DSCallback(None, sim=self.sim)
        c1 = DSCallback(None, sim=self.sim)
        self.sim.try_send = self._make_recorder([(c0, True), (c1, True)])
        p.add_subscriber(c0, phase=DSProducer.Phase.PRE)
        p.add_subscriber(c1, phase=DSProducer.Phase.PRE)
        p.send(1)
        self.sim.try_send.assert_has_calls([call(c0, 1), call(c1, 1)])

        self.sim.try_send = self._make_recorder([(c0, True), (c1, True)])
        p.add_subscriber(c0, phase=DSProducer.Phase.PRE)  # 2 times a subscriber
        p.send(2)
        self.sim.try_send.assert_has_calls([call(c0, 2), call(c1, 2)])

    def test6_producer_signal_post_plus(self):
        p = DSProducer(sim=self.sim)
        c0 = DSCallback(None, sim=self.sim)
        c1 = DSCallback(None, sim=self.sim)
        self.sim.try_send = self._make_recorder([(c0, True), (c1, True)])
        p.add_subscriber(c0, phase=DSProducer.Phase.POST_HIT)
        p.add_subscriber(c1, phase=DSProducer.Phase.POST_HIT)
        p.send(1)
        self.sim.try_send.assert_not_called()

        p = DSProducer(sim=self.sim)
        c0 = DSCallback(None, sim=self.sim)
        c1 = DSCallback(None, sim=self.sim)
        self.sim.try_send = self._make_recorder([(c0, True), (c1, True)])
        p.add_subscriber(c0, phase=DSProducer.Phase.POST_HIT)
        p.add_subscriber(c1, phase=DSProducer.Phase.POST_HIT)
        p.add_subscriber(c0)  # add consumer
        p.send(1)
        self.sim.try_send.assert_has_calls([call(c0, 1), call(c0, {'consumer': c0, 'event': 1}), call(c1, {'consumer': c0, 'event': 1})])

        self.sim.try_send = self._make_recorder([(c0, True), (c1, True)])
        p.add_subscriber(c0, phase=DSProducer.Phase.POST_HIT)  # 2 times a subscriber
        p.send(2)
        self.sim.try_send.assert_has_calls([call(c0, 2), call(c0, {'consumer': c0, 'event': 2}), call(c1, {'consumer': c0, 'event': 2})])

    def test7_producer_signal_post_minus(self):
        p = DSProducer(sim=self.sim)
        c0 = DSCallback(None, sim=self.sim)
        c1 = DSCallback(None, sim=self.sim)
        self.sim.try_send = self._make_recorder([(c0, True), (c1, True)])
        p.add_subscriber(c0, phase=DSProducer.Phase.POST_MISS)
        p.add_subscriber(c1, phase=DSProducer.Phase.POST_MISS)
        p.send(1)
        self.sim.try_send.assert_has_calls([call(c0, 1), call(c1, 1)])

        self.sim.try_send = self._make_recorder([(c0, True), (c1, True)])
        p.add_subscriber(c0, phase=DSProducer.Phase.POST_MISS)  # 2 times a subscriber
        p.send(2)
        self.sim.try_send.assert_has_calls([call(c0, 2), call(c1, 2)])


    def test8_producer_signal_same(self):
        c0 = DSCallback(None, sim=self.sim)
        c1 = DSCallback(None, sim=self.sim)
        tests = (
            (DSProducer.Phase.PRE, 'c0c1', True, True),
            (DSProducer.Phase.PRE, 'c1c0', True, True),
            (DSProducer.Phase.CONSUME, 'c0c1', True, True),
            (DSProducer.Phase.CONSUME, 'c1c0', False, True),
            (DSProducer.Phase.POST_HIT, 'c0c1', False, False),  # post+ requires the signal to be consumed
            (DSProducer.Phase.POST_HIT, 'c1c0', False, False),
            (DSProducer.Phase.POST_MISS, 'c0c1', True, True),
            (DSProducer.Phase.POST_MISS, 'c1c0', True, True),
        )
        for phase, order, c0_called, c1_called in tests:
            self.sim.try_send = self._make_recorder([(c0, False), (c1, False)])
            p = DSProducer(sim=self.sim)
            if order == 'c0c1':
                p.add_subscriber(phase=phase, subscriber=c0)
                p.add_subscriber(phase=phase, subscriber=c1)
            else:
                p.add_subscriber(phase=phase, subscriber=c1)
                p.add_subscriber(phase=phase, subscriber=c0)
            p.send('Hi')
            calls = []
            if c0_called:
                calls.append(call(c0, 'Hi'))
            if c1_called:
                calls.append(call(c1, 'Hi'))
            self.sim.try_send.assert_has_calls(calls, any_order=True)


    def test9_producer_signal_combi_nonconsume(self):
        c0 = DSCallback(lambda e: True, sim=self.sim)
        c1 = DSCallback(lambda e: True, sim=self.sim)

        tests = (
            (DSProducer.Phase.PRE, DSProducer.Phase.CONSUME, call(c0, 'Hi'), call(c1, 'Hi')),
            (DSProducer.Phase.CONSUME, DSProducer.Phase.PRE, call(c0, 'Hi'), call(c1, 'Hi')),
            (DSProducer.Phase.PRE, DSProducer.Phase.POST_HIT, call(c0, 'Hi'), None),
            (DSProducer.Phase.POST_HIT, DSProducer.Phase.PRE, None, call(c1, 'Hi')),
            (DSProducer.Phase.PRE, DSProducer.Phase.POST_MISS, call(c0, 'Hi'), call(c1, 'Hi')),
            (DSProducer.Phase.POST_MISS, DSProducer.Phase.PRE, call(c0, 'Hi'), call(c1, 'Hi')),
            (DSProducer.Phase.CONSUME, DSProducer.Phase.POST_HIT, call(c0, 'Hi'), None),
            (DSProducer.Phase.POST_HIT, DSProducer.Phase.CONSUME, None, call(c1, 'Hi')),
            (DSProducer.Phase.CONSUME, DSProducer.Phase.POST_MISS, call(c0, 'Hi'), call(c1, 'Hi')),
            (DSProducer.Phase.POST_MISS, DSProducer.Phase.CONSUME, call(c0, 'Hi'), call(c1, 'Hi')),
            (DSProducer.Phase.POST_HIT, DSProducer.Phase.POST_MISS, None, call(c1, 'Hi')),
            (DSProducer.Phase.POST_MISS, DSProducer.Phase.POST_HIT, call(c0, 'Hi'), None),
        )
        for c0_phase, c1_phase, c0_called, c1_called in tests:
            self.sim.try_send = self._make_recorder([(c0, False), (c1, False)])
            p = DSProducer(sim=self.sim)
            p.add_subscriber(phase=c0_phase, subscriber=c0)
            p.add_subscriber(phase=c1_phase, subscriber=c1)
            p.send('Hi')
            calls = []
            if c0_called:
                calls.append(c0_called)
            if c1_called:
                calls.append(c1_called)
            self.sim.try_send.assert_has_calls(calls, any_order=True)


    def test10_producer_signal_combi_consume(self):
        c0 = DSCallback(lambda e: True, sim=self.sim)
        c1 = DSCallback(lambda e: True, sim=self.sim)

        tests = (
            (DSProducer.Phase.PRE, DSProducer.Phase.CONSUME, call(c0, 'Hi'), call(c1, 'Hi')),
            (DSProducer.Phase.CONSUME, DSProducer.Phase.PRE, call(c0, 'Hi'), call(c1, 'Hi')),
            (DSProducer.Phase.PRE, DSProducer.Phase.POST_HIT, call(c0, 'Hi'), None),
            (DSProducer.Phase.POST_HIT, DSProducer.Phase.PRE, None, call(c1, 'Hi')),
            (DSProducer.Phase.PRE, DSProducer.Phase.POST_MISS, call(c0, 'Hi'), call(c1, 'Hi')),
            (DSProducer.Phase.POST_MISS, DSProducer.Phase.PRE, call(c0, 'Hi'), call(c1, 'Hi')),
            (DSProducer.Phase.CONSUME, DSProducer.Phase.POST_HIT, call(c0, 'Hi'), call(c1, {'consumer': c0, 'event': 'Hi'})),
            (DSProducer.Phase.POST_HIT, DSProducer.Phase.CONSUME, call(c0, {'consumer': c1, 'event': 'Hi'}), call(c1, 'Hi')),
            (DSProducer.Phase.CONSUME, DSProducer.Phase.POST_MISS, call(c0, 'Hi'), None),
            (DSProducer.Phase.POST_MISS, DSProducer.Phase.CONSUME, None, call(c1, 'Hi')),
            (DSProducer.Phase.POST_HIT, DSProducer.Phase.POST_MISS, None, call(c1, 'Hi')),
            (DSProducer.Phase.POST_MISS, DSProducer.Phase.POST_HIT, call(c0, 'Hi'), None),
        )
        for c0_phase, c1_phase, c0_called, c1_called in tests:
            self.sim.try_send = self._make_recorder([(c0, True), (c1, True)])
            p = DSProducer(sim=self.sim)
            p.add_subscriber(phase=c0_phase, subscriber=c0)
            p.add_subscriber(phase=c1_phase, subscriber=c1)
            p.send('Hi')
            calls = []
            if c0_called:
                calls.append(c0_called)
            if c1_called:
                calls.append(c1_called)
            self.sim.try_send.assert_has_calls(calls, any_order=True)


    def test11_producer_add_subscriber_in_send_hook(self):
        ''' Test the behavior of signal function when send handler adds a subscriber '''
        self.sim = DSSimulation()
        p = DSProducer(sim=self.sim)
        c0 = DSCallback(Mock(return_value=False), sim=self.sim)
        c1 = DSCallback(lambda e: p.add_subscriber(subscriber=c0), sim=self.sim)
        p.add_subscriber(subscriber=c1)
        p.add_subscriber(subscriber=c0)
        self.assertEqual(p.subs[DSProducer.Phase.PRE].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.CONSUME].d, {c0: 1, c1: 1})
        self.assertEqual(p.subs[DSProducer.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.POST_MISS].d, {})
        p.send(None)
        c0.forward_method.assert_called_once()
        self.assertEqual(p.subs[DSProducer.Phase.PRE].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.CONSUME].d, {c0: 2, c1: 1})
        self.assertEqual(p.subs[DSProducer.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.POST_MISS].d, {})


    def test12_producer_remove_subscriber_in_send_hook(self):
        ''' Test the behavior of signal function when send handler removes a subscriber '''
        self.sim = DSSimulation()
        p = DSProducer(sim=self.sim)
        c0 = DSCallback(Mock(return_value=False), sim=self.sim)
        c1 = DSCallback(lambda e: p.remove_subscriber(subscriber=c1), sim=self.sim)
        p.add_subscriber(subscriber=c1)
        p.add_subscriber(subscriber=c0)
        self.assertEqual(p.subs[DSProducer.Phase.PRE].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.CONSUME].d, {c0: 1, c1: 1})
        self.assertEqual(p.subs[DSProducer.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.POST_MISS].d, {})
        p.send(None)
        c0.forward_method.assert_called_once()
        self.assertEqual(p.subs[DSProducer.Phase.PRE].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.CONSUME].d, {c0: 1})
        self.assertEqual(p.subs[DSProducer.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSProducer.Phase.POST_MISS].d, {})

class TestNotifierDict(unittest.TestCase):

    def test1_inc_dec(self):
        n = NotifierDict()
        self.assertTrue(n.d == {})
        self.assertFalse(n.needs_cleanup)
        n.inc('a'), n.inc('a')
        self.assertEqual(n.d, {'a': 2})
        self.assertFalse(n.needs_cleanup)
        n.inc('b'), n.inc('a')
        self.assertEqual(n.d, {'a': 3, 'b': 1})
        self.assertFalse(n.needs_cleanup)
        n.dec('a'), n.inc('b')
        self.assertEqual(n.d, {'a': 2, 'b': 2})
        self.assertFalse(n.needs_cleanup)
        n.dec('a'), n.dec('a')
        self.assertEqual(n.d, {'b': 2})
        self.assertFalse(n.needs_cleanup)

    def test2_iter_change(self):
        n = NotifierDict()
        n.inc('a')
        count = 0
        for item in n:
            n.inc('b')
            n.dec('a')
            count += 1
        self.assertTrue(count == 1)

    def test3_cleanup(self):
        n = NotifierDict()
        self.assertFalse(n.needs_cleanup)
        self.assertEqual(n.d, {})
        n.cleanup()
        self.assertFalse(n.needs_cleanup)
        self.assertEqual(n.d, {})
        n.d = {'a': 2, 'b': 3}
        n.cleanup()
        self.assertFalse(n.needs_cleanup)
        self.assertEqual(n.d, {'a': 2, 'b': 3})
        n.dec('a'), n.dec('a')
        self.assertFalse(n.needs_cleanup)
        self.assertEqual(n.d, {'b': 3})
        n.cleanup()
        self.assertFalse(n.needs_cleanup)
        self.assertEqual(n.d, {'b': 3})
        n.dec('b'), n.dec('b'), n.dec('b')
        self.assertFalse(n.needs_cleanup)
        self.assertEqual(n.d, {})
        n.cleanup()
        self.assertFalse(n.needs_cleanup)
        self.assertEqual(n.d, {})

    def test4_iter(self):
        n = NotifierDict()
        n.d = {'c': 1, 'a': 2, 'b': 4}
        it = iter(n)
        el = next(it)
        self.assertTrue(el == ('c', 1))
        el = next(it)
        self.assertTrue(el == ('a', 2))
        el = next(it)
        self.assertTrue(el == ('b', 4))
        with self.assertRaises(StopIteration):
            el = next(it)

    def test5_rewind(self):
        n = NotifierDict()
        n.d = {'c': 1, 'a': 2, 'b': 4}
        it = iter(n)
        next(it), next(it)
        n.rewind()
        self.assertEqual(n.d, {'c': 1, 'a': 2, 'b': 4})

        it = iter(n)
        next(it), next(it), next(it)
        n.rewind()
        self.assertEqual(n.d, {'c': 1, 'a': 2, 'b': 4})

        it = iter(n)
        n.rewind()
        self.assertEqual(n.d, {'c': 1, 'a': 2, 'b': 4})
        
class TestNotifierRoundRobin(unittest.TestCase):

    def test1_inc_dec(self):
        n = NotifierRoundRobin()
        self.assertTrue(n.queue == [])
        self.assertFalse(n.needs_cleanup)
        n.inc('a'), n.inc('a')
        self.assertEqual(n.queue, [('a', 2)])
        self.assertFalse(n.needs_cleanup)
        n.inc('b'), n.inc('a')
        self.assertEqual(n.queue, [('a', 3), ('b', 1)])
        self.assertFalse(n.needs_cleanup)
        n.dec('a'), n.inc('b')
        self.assertEqual(n.queue, [('a', 2), ('b', 2)])
        self.assertFalse(n.needs_cleanup)
        n.dec('a'), n.dec('a')
        self.assertEqual(n.queue, [('a', 0), ('b', 2)])
        self.assertTrue(n.needs_cleanup)

    def test2_iter_change(self):
        n = NotifierRoundRobin()
        n.inc('a')
        count = 0
        for item in n:
            n.inc('b')
            n.dec('a')
            count += 1
        self.assertTrue(count == 1)

    def test3_cleanup(self):
        n = NotifierRoundRobin()
        self.assertFalse(n.needs_cleanup)
        self.assertEqual(n.queue, [])
        n.cleanup()
        self.assertFalse(n.needs_cleanup)
        self.assertEqual(n.queue, [])
        n.queue = [NotifierRoundRobinItem('a', 2), NotifierRoundRobinItem('b', 3)]
        n.cleanup()
        self.assertFalse(n.needs_cleanup)
        self.assertEqual(n.queue, [('a', 2), ('b', 3)])
        n.dec('a'), n.dec('a')
        self.assertTrue(n.needs_cleanup)
        self.assertEqual(n.queue, [('a', 0), ('b', 3)])
        n.cleanup()
        self.assertFalse(n.needs_cleanup)
        self.assertEqual(n.queue, [('b', 3)])
        n.dec('b'), n.dec('b'), n.dec('b')
        self.assertTrue(n.needs_cleanup)
        self.assertEqual(n.queue, [('b', 0)])
        n.cleanup()
        self.assertFalse(n.needs_cleanup)
        self.assertEqual(n.queue, [])

    def test4_iter(self):
        n = NotifierRoundRobin()
        n.queue = [NotifierRoundRobinItem('c', 1), NotifierRoundRobinItem('a', 2), NotifierRoundRobinItem('b', 4)]
        it = iter(n)
        el = next(it)
        self.assertTrue(el == ('c', 1))
        el = next(it)
        self.assertTrue(el == ('a', 2))
        el = next(it)
        self.assertTrue(el == ('b', 4))
        with self.assertRaises(StopIteration):
            el = next(it)

    def test5_rewind(self):
        n = NotifierRoundRobin()
        n.queue = [NotifierRoundRobinItem('c', 1), NotifierRoundRobinItem('a', 2), NotifierRoundRobinItem('b', 4),]
        it = iter(n)
        next(it), next(it)
        n.rewind()
        self.assertEqual(n.queue, [('b', 4), ('c', 1), ('a', 2),])

        it = iter(n)
        next(it), next(it), next(it)
        n.rewind()
        self.assertEqual(n.queue, [('b', 4), ('c', 1), ('a', 2),])

        it = iter(n)
        n.rewind()
        self.assertEqual(n.queue, [('b', 4), ('c', 1), ('a', 2),])

class TestNotifierPriority(unittest.TestCase):

    def test1_inc_dec(self):
        n = NotifierPriority()
        self.assertTrue(n.d == {})
        self.assertFalse(n.needs_cleanup)
        n.inc('a', priority=1), n.inc('a', priority=1)
        self.assertEqual(n.d, {1: {'a': 2}})
        self.assertFalse(n.needs_cleanup)
        n.inc('b', priority=1), n.inc('a', priority=2)
        self.assertEqual(n.d, {1: {'a': 2, 'b': 1}, 2: {'a': 1}})
        self.assertFalse(n.needs_cleanup)
        n.dec('a', priority=1), n.inc('b', priority=1)
        self.assertEqual(n.d, {1: {'a': 1, 'b': 2}, 2: {'a': 1}})
        self.assertFalse(n.needs_cleanup)  # no bucket added/removed
        n.dec('a', priority=1)
        self.assertEqual(n.d, {1: {'b': 2}, 2: {'a': 1}})
        self.assertFalse(n.needs_cleanup)  # no bucket added/removed
        n.dec('a', priority=2)
        self.assertEqual(n.d, {1: {'b': 2}})
        self.assertFalse(n.needs_cleanup)

    def test2_iter_change(self):
        n = NotifierPriority()
        n.inc('a', priority=1)
        count = 0
        for item in n:
            n.inc('b', priority=1)
            n.dec('a', priority=1)
            count += 1
        self.assertTrue(count == 1)

    def test3_cleanup(self):
        n = NotifierPriority()
        self.assertFalse(n.needs_cleanup)
        self.assertEqual(n.d, {})
        n.cleanup()
        self.assertFalse(n.needs_cleanup)
        self.assertEqual(n.d, {})
        n.d = {1: {'a': 2, 'b': 3}, 2: {'a': 1}}
        n.cleanup()
        self.assertFalse(n.needs_cleanup)
        self.assertEqual(n.d, {1: {'a': 2, 'b': 3}, 2: {'a': 1}})
        n.dec('a', priority=1), n.dec('a', priority=1)
        self.assertFalse(n.needs_cleanup)  # key removed, bucket remains
        self.assertEqual(n.d, {1: {'b': 3}, 2: {'a': 1}})
        n.cleanup()
        self.assertFalse(n.needs_cleanup)
        self.assertEqual(n.d, {1: {'b': 3}, 2: {'a': 1}})
        n.dec('a', priority=2)
        self.assertFalse(n.needs_cleanup)
        n.cleanup()
        self.assertFalse(n.needs_cleanup)
        self.assertEqual(n.d, {1: {'b': 3}})
        n.dec('b', priority=1), n.dec('b', priority=1), n.dec('b', priority=1)
        self.assertFalse(n.needs_cleanup)
        n.cleanup()
        self.assertFalse(n.needs_cleanup)
        self.assertEqual(n.d, {})

    def test4_iter(self):
        n = NotifierPriority()
        n.d = {2: {'c': 1, 'a': 2, 'b': 4}, 1: {'d': 12, 'e': 14}}
        it = iter(n)
        el = next(it)
        self.assertTrue(el == ('d', 12))
        el = next(it)
        self.assertTrue(el == ('e', 14))
        el = next(it)
        self.assertTrue(el == ('c', 1))
        el = next(it)
        self.assertTrue(el == ('a', 2))
        el = next(it)
        self.assertTrue(el == ('b', 4))
        with self.assertRaises(StopIteration):
            el = next(it)

    def test5_rewind(self):
        n = NotifierPriority()
        n.d = {2: {'c': 1, 'a': 2, 'b': 4}, 1: {'d': 12, 'e': 14}}
        it = iter(n)
        next(it), next(it)
        n.rewind()
        self.assertEqual(n.d, {2: {'c': 1, 'a': 2, 'b': 4}, 1: {'d': 12, 'e': 14}})

        it = iter(n)
        next(it), next(it), next(it)
        n.rewind()
        self.assertEqual(n.d, {2: {'c': 1, 'a': 2, 'b': 4}, 1: {'d': 12, 'e': 14}})

        it = iter(n)
        next(it), next(it), next(it), next(it), next(it)
        n.rewind()
        self.assertEqual(n.d, {2: {'c': 1, 'a': 2, 'b': 4}, 1: {'d': 12, 'e': 14}})

        it = iter(n)
        next(it), next(it), next(it), next(it)
        n.rewind()
        self.assertEqual(n.d, {2: {'c': 1, 'a': 2, 'b': 4}, 1: {'d': 12, 'e': 14}})

        it = iter(n)
        n.rewind()
        self.assertEqual(n.d, {2: {'c': 1, 'a': 2, 'b': 4}, 1: {'d': 12, 'e': 14}})

    def test6_cached_sorted_priorities_updates_on_inc_dec(self):
        n = NotifierPriority()
        n.inc('a', priority=2)
        n.inc('b', priority=1)
        self.assertEqual(list(n), [('b', 1), ('a', 1)])
        # Remove last key in priority 1 bucket -> key set changes.
        n.dec('b', priority=1)
        self.assertEqual(list(n), [('a', 1)])

    def test7_cached_sorted_priorities_updates_on_direct_dict_replace(self):
        n = NotifierPriority()
        n.d = {3: {'x': 1}, 1: {'a': 1}}
        self.assertEqual(list(n), [('a', 1), ('x', 1)])
        # Replace dict directly with same length but different keys.
        n.d = {4: {'z': 2}, 2: {'y': 3}}
        self.assertEqual(list(n), [('y', 3), ('z', 2)])
