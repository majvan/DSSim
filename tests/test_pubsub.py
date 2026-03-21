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
Tests for pubsub module
'''
import unittest
from unittest.mock import Mock, call
from dssim import DSProcess, DSCallback, DSCondCallback, DSKWCondCallback, DSCondSub, DSKWCallback, DSSimulation, DSSub, DSTrackableEvent
from dssim import DSPub, NotifierDict, NotifierRoundRobin, NotifierPriority
from dssim.pubsub import NotifierRoundRobinItem
from dssim.pubsub.base import SourceAwareEvent

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
        c = DSCondCallback(my_consumer_fcn, cond=lambda e:e['data'] > 0, sim=DSSimulation())
        c.send({'data': 1})
        my_consumer_fcn.assert_called_once_with({'data': 1})
        my_consumer_fcn.reset_mock()
        c.send({'data': 0})
        my_consumer_fcn.assert_not_called()
        my_consumer_fcn.reset_mock()

    def test6_kw_consumer_with_filter(self):
        my_consumer_fcn = Mock()
        c = DSKWCondCallback(my_consumer_fcn, cond=lambda e:e['data'] > 0, sim=DSSimulation())
        c.send({'data': 1})
        my_consumer_fcn.assert_called_once_with(data=1)
        my_consumer_fcn.reset_mock()
        c.send({'data': 0})
        my_consumer_fcn.assert_not_called()
        my_consumer_fcn.reset_mock()

    def test7_callback_rejects_cond(self):
        with self.assertRaises(TypeError):
            DSCallback(Mock(), cond=lambda e: True, sim=SomeObj())

    def test8_kw_callback_rejects_cond(self):
        with self.assertRaises(TypeError):
            DSKWCallback(Mock(), cond=lambda e: True, sim=SomeObj())

class SomeObj2:
    pass


class TestConsumer(unittest.TestCase):
    ''' Tests for DSSub.try_send '''

    def test1_try_send_checks_cond_before_dispatch(self):
        ''' try_send must check condition first; if rejected, send_object must not be called '''
        from unittest.mock import MagicMock
        sim = DSSimulation()
        sim.send_object = Mock()
        consumer = DSCondCallback(lambda e: True, sim=sim)
        consumer.meta = SomeObj2()
        consumer.meta.cond = MagicMock()
        consumer.meta.cond.check = Mock(return_value=(False, 'abc'))
        consumer.send(None)
        consumer.meta.cond.check.assert_called_once()
        sim.send_object.assert_not_called()

    def test2_try_send_dispatches_after_cond_passes(self):
        ''' try_send in post-check mode delegates to send() after condition check. '''
        from unittest.mock import MagicMock
        call_order = []
        sim = DSSimulation()
        def called_check_condition(*args, **kwargs):
            call_order.append(call('check_condition', *args, **kwargs))
            return (True, 'abc')
        def called_send_object(*args, **kwargs):
            call_order.append(call('send_object', *args, **kwargs))
            return True
        consumer = DSCondCallback(lambda e: True, sim=sim)
        consumer.meta = SomeObj2()
        consumer.meta.cond = MagicMock()
        consumer.meta.cond.check = Mock(side_effect=called_check_condition)
        sim.send_object = Mock(side_effect=called_send_object)
        consumer.send(None)
        consumer.meta.cond.check.assert_called_once()
        sim.send_object.assert_not_called()
        self.assertEqual(call_order, [call('check_condition', None)])


class TestSubscriber(unittest.TestCase):
    ''' TODO: test registratrion, deregistration, event data path when registered '''
    pass


class TestProducer(unittest.TestCase):
    ''' Test the DSPub '''

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
        Replaces the old sim.try_send mock pattern now that try_send lives on DSSub.
        Returns the shared Mock so assert_has_calls / assert_not_called etc. still work.
        '''
        m = Mock()
        for consumer, retval in consumer_retval_pairs:
            def make_route(c=consumer, rv=retval):
                def route(event):
                    m(c, event)
                    return rv
                return route
            route = make_route()
            # Keep tests compatible with both routing styles:
            # - consumer-level explicit dispatch via consumer.send(...)
            # - pub routing via producer.send(...)
            consumer.try_send = route
            consumer.send = route
        return m

    def test1_producer_add(self):
        p = DSPub(sim=self.sim)
        process = self.__my_process_consumer()
        c0 = DSProcess(process, start=True, sim=self.sim)
        c1 = DSProcess(process, start=True, sim=self.sim)
        p.add_subscriber(subscriber=c0)
        self.assertEqual(p.subs[DSPub.Phase.PRE].d, {})
        self.assertEqual(p.subs[DSPub.Phase.CONSUME].d, {c0: 1})
        self.assertEqual(p.subs[DSPub.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSPub.Phase.POST_MISS].d, {})
        p.add_subscriber(subscriber=c1)
        self.assertEqual(p.subs[DSPub.Phase.PRE].d, {})
        self.assertEqual(p.subs[DSPub.Phase.CONSUME].d, {c0: 1, c1: 1})
        self.assertEqual(p.subs[DSPub.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSPub.Phase.POST_MISS].d, {})
        p.add_subscriber(subscriber=c0)
        self.assertEqual(p.subs[DSPub.Phase.PRE].d, {})
        self.assertEqual(p.subs[DSPub.Phase.CONSUME].d, {c0: 2, c1: 1})
        self.assertEqual(p.subs[DSPub.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSPub.Phase.POST_MISS].d, {})
        p.add_subscriber(phase=DSPub.Phase.PRE, subscriber=c0)
        self.assertEqual(p.subs[DSPub.Phase.PRE].d, {c0: 1})
        self.assertEqual(p.subs[DSPub.Phase.CONSUME].d, {c0: 2, c1: 1})
        self.assertEqual(p.subs[DSPub.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSPub.Phase.POST_MISS].d, {})
        p.add_subscriber(phase=DSPub.Phase.POST_HIT, subscriber=c1)
        self.assertEqual(p.subs[DSPub.Phase.PRE].d, {c0: 1})
        self.assertEqual(p.subs[DSPub.Phase.CONSUME].d, {c0: 2, c1: 1})
        self.assertEqual(p.subs[DSPub.Phase.POST_HIT].d, {c1: 1})
        self.assertEqual(p.subs[DSPub.Phase.POST_MISS].d, {})
        p.add_subscriber(phase=DSPub.Phase.POST_MISS, subscriber=c0)
        self.assertEqual(p.subs[DSPub.Phase.PRE].d, {c0: 1})
        self.assertEqual(p.subs[DSPub.Phase.CONSUME].d, {c0: 2, c1: 1})
        self.assertEqual(p.subs[DSPub.Phase.POST_HIT].d, {c1: 1})
        self.assertEqual(p.subs[DSPub.Phase.POST_MISS].d, {c0: 1})
        c2 = lambda e: False
        c3 = lambda e: True
        p.add_subscriber(phase=DSPub.Phase.POST_HIT, subscriber=c2)
        self.assertEqual(p.subs[DSPub.Phase.PRE].d, {c0: 1})
        self.assertEqual(p.subs[DSPub.Phase.CONSUME].d, {c0: 2, c1: 1})
        self.assertEqual(p.subs[DSPub.Phase.POST_HIT].d, {c2: 1, c1: 1})
        self.assertEqual(p.subs[DSPub.Phase.POST_MISS].d, {c0: 1})
        p.add_subscriber(phase=DSPub.Phase.POST_HIT, subscriber=c2)
        self.assertEqual(p.subs[DSPub.Phase.PRE].d, {c0: 1})
        self.assertEqual(p.subs[DSPub.Phase.CONSUME].d, {c0: 2, c1: 1})
        self.assertEqual(p.subs[DSPub.Phase.POST_HIT].d, {c2: 2, c1: 1})
        self.assertEqual(p.subs[DSPub.Phase.POST_MISS].d, {c0: 1})
        p.add_subscriber(phase=DSPub.Phase.PRE, subscriber=c3)
        self.assertEqual(p.subs[DSPub.Phase.PRE].d, {c3: 1, c0: 1})
        self.assertEqual(p.subs[DSPub.Phase.CONSUME].d, {c0: 2, c1: 1})
        self.assertEqual(p.subs[DSPub.Phase.POST_HIT].d, {c2: 2, c1: 1})
        self.assertEqual(p.subs[DSPub.Phase.POST_MISS].d, {c0: 1})

    def test2_producer_remove(self):
        p = DSPub(sim=DSSimulation())
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
        p.subs[DSPub.Phase.PRE].d = {}
        p.subs[DSPub.Phase.CONSUME].d = {c0: 1}
        p.subs[DSPub.Phase.POST_HIT].d = {}
        p.subs[DSPub.Phase.POST_MISS].d = {}
        p.remove_subscriber(subscriber=c0)
        self.assertEqual(p.subs[DSPub.Phase.PRE].d, {})
        self.assertEqual(p.subs[DSPub.Phase.CONSUME].d, {})
        self.assertEqual(p.subs[DSPub.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSPub.Phase.POST_MISS].d, {})
        p.send(None)
        self.assertEqual(p.subs[DSPub.Phase.PRE].d, {})
        self.assertEqual(p.subs[DSPub.Phase.CONSUME].d, {})
        self.assertEqual(p.subs[DSPub.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSPub.Phase.POST_MISS].d, {})

        p.subs[DSPub.Phase.PRE].d = {}
        p.subs[DSPub.Phase.CONSUME].d = {c0: 1, c1: 1}
        p.subs[DSPub.Phase.POST_HIT].d = {}
        p.subs[DSPub.Phase.POST_MISS].d = {}
        p.remove_subscriber(subscriber=c0)
        self.assertEqual(p.subs[DSPub.Phase.PRE].d, {})
        self.assertEqual(p.subs[DSPub.Phase.CONSUME].d, {c1: 1})
        self.assertEqual(p.subs[DSPub.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSPub.Phase.POST_MISS].d, {})
        p.send(None)
        self.assertEqual(p.subs[DSPub.Phase.PRE].d, {})
        self.assertEqual(p.subs[DSPub.Phase.CONSUME].d, {c1: 1})
        self.assertEqual(p.subs[DSPub.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSPub.Phase.POST_MISS].d, {})

        p.subs[DSPub.Phase.PRE].d = {c0: 1, c1: 1}
        p.subs[DSPub.Phase.CONSUME].d = {c0: 1, c1: 1}
        p.subs[DSPub.Phase.POST_HIT].d = {}
        p.subs[DSPub.Phase.POST_MISS].d = {}
        p.remove_subscriber(subscriber=c0)
        self.assertEqual(p.subs[DSPub.Phase.PRE].d, {c0: 1, c1: 1})
        self.assertEqual(p.subs[DSPub.Phase.CONSUME].d, {c1: 1})
        self.assertEqual(p.subs[DSPub.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSPub.Phase.POST_MISS].d, {})
        p.send(None)
        self.assertEqual(p.subs[DSPub.Phase.PRE].d, {c0: 1, c1: 1})
        self.assertEqual(p.subs[DSPub.Phase.CONSUME].d, {c1: 1})
        self.assertEqual(p.subs[DSPub.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSPub.Phase.POST_MISS].d, {})
        p.remove_subscriber(phase=DSPub.Phase.PRE, subscriber=c1)
        self.assertEqual(p.subs[DSPub.Phase.PRE].d, {c0: 1})
        self.assertEqual(p.subs[DSPub.Phase.CONSUME].d, {c1: 1})
        self.assertEqual(p.subs[DSPub.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSPub.Phase.POST_MISS].d, {})
        p.send(None)
        self.assertEqual(p.subs[DSPub.Phase.PRE].d, {c0: 1})
        self.assertEqual(p.subs[DSPub.Phase.CONSUME].d, {c1: 1})
        self.assertEqual(p.subs[DSPub.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSPub.Phase.POST_MISS].d, {})

        c2 = SomeIterableObj()
        p.subs[DSPub.Phase.PRE].d = {c0: 1, c2: 1}
        p.subs[DSPub.Phase.CONSUME].d = {c1: 1, c2: 1}
        p.subs[DSPub.Phase.POST_HIT].d = {}
        p.subs[DSPub.Phase.POST_MISS].d = {}
        p.remove_subscriber(phase=DSPub.Phase.PRE, subscriber=c2)
        self.assertEqual(p.subs[DSPub.Phase.PRE].d, {c0: 1})
        self.assertEqual(p.subs[DSPub.Phase.CONSUME].d, {c1: 1, c2: 1})
        self.assertEqual(p.subs[DSPub.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSPub.Phase.POST_MISS].d, {})
        p.remove_subscriber(subscriber=c2)
        self.assertEqual(p.subs[DSPub.Phase.PRE].d, {c0: 1})
        self.assertEqual(p.subs[DSPub.Phase.CONSUME].d, {c1: 1})
        self.assertEqual(p.subs[DSPub.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSPub.Phase.POST_MISS].d, {})

    def test3_producer_signal_act_retval(self):
        p = DSPub(sim=self.sim)
        c0 = DSCallback(None, sim=self.sim)
        c1 = DSCallback(None, sim=self.sim)
        self.sim.try_send = self._make_recorder([(c0, False), (c1, False)])
        p.add_subscriber(c0)
        p.add_subscriber(c1)
        p.send(1)
        self.sim.try_send.assert_has_calls([call(c0, 1), call(c1, 1)])
        p = DSPub(sim=self.sim)
        c0 = DSCallback(None, sim=self.sim)
        c1 = DSCallback(None, sim=self.sim)
        self.sim.try_send = self._make_recorder([(c0, True), (c1, True)])
        p.add_subscriber(c0)
        p.add_subscriber(c1)
        p.send(2)
        self.sim.try_send.assert_has_calls([call(c0, 2),])

    def test4_producer_signal_act(self):
        p = DSPub(sim=self.sim)
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
        p = DSPub(sim=self.sim)
        c0 = DSCallback(None, sim=self.sim)
        c1 = DSCallback(None, sim=self.sim)
        self.sim.try_send = self._make_recorder([(c0, True), (c1, True)])
        p.add_subscriber(c0, phase=DSPub.Phase.PRE)
        p.add_subscriber(c1, phase=DSPub.Phase.PRE)
        p.send(1)
        self.sim.try_send.assert_has_calls([call(c0, 1), call(c1, 1)])

        self.sim.try_send = self._make_recorder([(c0, True), (c1, True)])
        p.add_subscriber(c0, phase=DSPub.Phase.PRE)  # 2 times a subscriber
        p.send(2)
        self.sim.try_send.assert_has_calls([call(c0, 2), call(c1, 2)])

    def test6_producer_signal_post_plus(self):
        p = DSPub(sim=self.sim)
        c0 = DSCallback(None, sim=self.sim)
        c1 = DSCallback(None, sim=self.sim)
        self.sim.try_send = self._make_recorder([(c0, True), (c1, True)])
        p.add_subscriber(c0, phase=DSPub.Phase.POST_HIT)
        p.add_subscriber(c1, phase=DSPub.Phase.POST_HIT)
        p.send(1)
        self.sim.try_send.assert_not_called()

        p = DSPub(sim=self.sim)
        c0 = DSCallback(None, sim=self.sim)
        c1 = DSCallback(None, sim=self.sim)
        self.sim.try_send = self._make_recorder([(c0, True), (c1, True)])
        p.add_subscriber(c0, phase=DSPub.Phase.POST_HIT)
        p.add_subscriber(c1, phase=DSPub.Phase.POST_HIT)
        p.add_subscriber(c0)  # add consumer
        p.send(1)
        self.sim.try_send.assert_has_calls([call(c0, 1), call(c0, {'consumer': c0, 'event': 1}), call(c1, {'consumer': c0, 'event': 1})])

        self.sim.try_send = self._make_recorder([(c0, True), (c1, True)])
        p.add_subscriber(c0, phase=DSPub.Phase.POST_HIT)  # 2 times a subscriber
        p.send(2)
        self.sim.try_send.assert_has_calls([call(c0, 2), call(c0, {'consumer': c0, 'event': 2}), call(c1, {'consumer': c0, 'event': 2})])

    def test7_producer_signal_post_minus(self):
        p = DSPub(sim=self.sim)
        c0 = DSCallback(None, sim=self.sim)
        c1 = DSCallback(None, sim=self.sim)
        self.sim.try_send = self._make_recorder([(c0, True), (c1, True)])
        p.add_subscriber(c0, phase=DSPub.Phase.POST_MISS)
        p.add_subscriber(c1, phase=DSPub.Phase.POST_MISS)
        p.send(1)
        self.sim.try_send.assert_has_calls([call(c0, 1), call(c1, 1)])

        self.sim.try_send = self._make_recorder([(c0, True), (c1, True)])
        p.add_subscriber(c0, phase=DSPub.Phase.POST_MISS)  # 2 times a subscriber
        p.send(2)
        self.sim.try_send.assert_has_calls([call(c0, 2), call(c1, 2)])


    def test8_producer_signal_same(self):
        c0 = DSCallback(None, sim=self.sim)
        c1 = DSCallback(None, sim=self.sim)
        tests = (
            (DSPub.Phase.PRE, 'c0c1', True, True),
            (DSPub.Phase.PRE, 'c1c0', True, True),
            (DSPub.Phase.CONSUME, 'c0c1', True, True),
            (DSPub.Phase.CONSUME, 'c1c0', False, True),
            (DSPub.Phase.POST_HIT, 'c0c1', False, False),  # post+ requires the signal to be consumed
            (DSPub.Phase.POST_HIT, 'c1c0', False, False),
            (DSPub.Phase.POST_MISS, 'c0c1', True, True),
            (DSPub.Phase.POST_MISS, 'c1c0', True, True),
        )
        for phase, order, c0_called, c1_called in tests:
            self.sim.try_send = self._make_recorder([(c0, False), (c1, False)])
            p = DSPub(sim=self.sim)
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
            (DSPub.Phase.PRE, DSPub.Phase.CONSUME, call(c0, 'Hi'), call(c1, 'Hi')),
            (DSPub.Phase.CONSUME, DSPub.Phase.PRE, call(c0, 'Hi'), call(c1, 'Hi')),
            (DSPub.Phase.PRE, DSPub.Phase.POST_HIT, call(c0, 'Hi'), None),
            (DSPub.Phase.POST_HIT, DSPub.Phase.PRE, None, call(c1, 'Hi')),
            (DSPub.Phase.PRE, DSPub.Phase.POST_MISS, call(c0, 'Hi'), call(c1, 'Hi')),
            (DSPub.Phase.POST_MISS, DSPub.Phase.PRE, call(c0, 'Hi'), call(c1, 'Hi')),
            (DSPub.Phase.CONSUME, DSPub.Phase.POST_HIT, call(c0, 'Hi'), None),
            (DSPub.Phase.POST_HIT, DSPub.Phase.CONSUME, None, call(c1, 'Hi')),
            (DSPub.Phase.CONSUME, DSPub.Phase.POST_MISS, call(c0, 'Hi'), call(c1, 'Hi')),
            (DSPub.Phase.POST_MISS, DSPub.Phase.CONSUME, call(c0, 'Hi'), call(c1, 'Hi')),
            (DSPub.Phase.POST_HIT, DSPub.Phase.POST_MISS, None, call(c1, 'Hi')),
            (DSPub.Phase.POST_MISS, DSPub.Phase.POST_HIT, call(c0, 'Hi'), None),
        )
        for c0_phase, c1_phase, c0_called, c1_called in tests:
            self.sim.try_send = self._make_recorder([(c0, False), (c1, False)])
            p = DSPub(sim=self.sim)
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
            (DSPub.Phase.PRE, DSPub.Phase.CONSUME, call(c0, 'Hi'), call(c1, 'Hi')),
            (DSPub.Phase.CONSUME, DSPub.Phase.PRE, call(c0, 'Hi'), call(c1, 'Hi')),
            (DSPub.Phase.PRE, DSPub.Phase.POST_HIT, call(c0, 'Hi'), None),
            (DSPub.Phase.POST_HIT, DSPub.Phase.PRE, None, call(c1, 'Hi')),
            (DSPub.Phase.PRE, DSPub.Phase.POST_MISS, call(c0, 'Hi'), call(c1, 'Hi')),
            (DSPub.Phase.POST_MISS, DSPub.Phase.PRE, call(c0, 'Hi'), call(c1, 'Hi')),
            (DSPub.Phase.CONSUME, DSPub.Phase.POST_HIT, call(c0, 'Hi'), call(c1, {'consumer': c0, 'event': 'Hi'})),
            (DSPub.Phase.POST_HIT, DSPub.Phase.CONSUME, call(c0, {'consumer': c1, 'event': 'Hi'}), call(c1, 'Hi')),
            (DSPub.Phase.CONSUME, DSPub.Phase.POST_MISS, call(c0, 'Hi'), None),
            (DSPub.Phase.POST_MISS, DSPub.Phase.CONSUME, None, call(c1, 'Hi')),
            (DSPub.Phase.POST_HIT, DSPub.Phase.POST_MISS, None, call(c1, 'Hi')),
            (DSPub.Phase.POST_MISS, DSPub.Phase.POST_HIT, call(c0, 'Hi'), None),
        )
        for c0_phase, c1_phase, c0_called, c1_called in tests:
            self.sim.try_send = self._make_recorder([(c0, True), (c1, True)])
            p = DSPub(sim=self.sim)
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
        p = DSPub(sim=self.sim)
        c0 = DSCallback(Mock(return_value=False), sim=self.sim)
        c1 = DSCallback(lambda e: p.add_subscriber(subscriber=c0), sim=self.sim)
        p.add_subscriber(subscriber=c1)
        p.add_subscriber(subscriber=c0)
        self.assertEqual(p.subs[DSPub.Phase.PRE].d, {})
        self.assertEqual(p.subs[DSPub.Phase.CONSUME].d, {c0: 1, c1: 1})
        self.assertEqual(p.subs[DSPub.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSPub.Phase.POST_MISS].d, {})
        p.send(None)
        c0.forward_method.assert_called_once()
        self.assertEqual(p.subs[DSPub.Phase.PRE].d, {})
        self.assertEqual(p.subs[DSPub.Phase.CONSUME].d, {c0: 2, c1: 1})
        self.assertEqual(p.subs[DSPub.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSPub.Phase.POST_MISS].d, {})


    def test12_producer_remove_subscriber_in_send_hook(self):
        ''' Test the behavior of signal function when send handler removes a subscriber '''
        self.sim = DSSimulation()
        p = DSPub(sim=self.sim)
        c0 = DSCallback(Mock(return_value=False), sim=self.sim)
        c1 = DSCallback(lambda e: p.remove_subscriber(subscriber=c1), sim=self.sim)
        p.add_subscriber(subscriber=c1)
        p.add_subscriber(subscriber=c0)
        self.assertEqual(p.subs[DSPub.Phase.PRE].d, {})
        self.assertEqual(p.subs[DSPub.Phase.CONSUME].d, {c0: 1, c1: 1})
        self.assertEqual(p.subs[DSPub.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSPub.Phase.POST_MISS].d, {})
        p.send(None)
        c0.forward_method.assert_called_once()
        self.assertEqual(p.subs[DSPub.Phase.PRE].d, {})
        self.assertEqual(p.subs[DSPub.Phase.CONSUME].d, {c0: 1})
        self.assertEqual(p.subs[DSPub.Phase.POST_HIT].d, {})
        self.assertEqual(p.subs[DSPub.Phase.POST_MISS].d, {})

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


class _DirectSubscriber(DSSub):
    dispatch_direct = True
    dispatch_source_aware = False

    def __init__(self, retval, *args, **kwargs):
        self.retval = retval
        self.events = []
        super().__init__(*args, **kwargs)

    def send(self, event):
        self.events.append(event)
        return self.retval


class _PlainSubscriber(DSSub):
    def __init__(self, retval, *args, **kwargs):
        self.retval = retval
        self.events = []
        super().__init__(*args, **kwargs)

    def send(self, event):
        self.events.append(event)
        return self.retval


class _RoutedSubscriber(DSCondSub):
    def __init__(self, retval, *args, **kwargs):
        self.retval = retval
        self.events = []
        super().__init__(*args, **kwargs)

    def send(self, event):
        self.events.append(event)
        return self.retval


class _SourceAwareSubscriber(DSSub):
    dispatch_direct = False
    dispatch_source_aware = True

    def __init__(self, retval, *args, **kwargs):
        self.retval = retval
        self.events = []
        super().__init__(*args, **kwargs)

    def send(self, event):
        self.events.append(event)
        return self.retval


class TestPubSubDirectDispatch(unittest.TestCase):
    def setUp(self):
        self.sim = DSSimulation()
        orig_send_object = self.sim.send_object
        self.sim.send_object = Mock(wraps=orig_send_object)

    def test_pre_observer_direct_bypasses_sim_send_object(self):
        pub = DSPub(sim=self.sim)
        observer = _DirectSubscriber(False, sim=self.sim)
        pub.add_subscriber(observer, phase=DSPub.Phase.PRE)

        pub.send('evt')

        self.assertEqual(observer.events, ['evt'])
        self.sim.send_object.assert_not_called()

    def test_pre_observer_dispatched_uses_sim_send_object(self):
        pub = DSPub(sim=self.sim)
        observer = _RoutedSubscriber(False, sim=self.sim, cond=lambda e: True)
        pub.add_subscriber(observer, phase=DSPub.Phase.PRE)

        pub.send('evt')

        self.assertEqual(len(observer.events), 1)
        observed = observer.events[0]
        self.assertTrue(isinstance(observed, SourceAwareEvent))
        self.assertEqual(observed.event, 'evt')
        self.assertIs(observed.source, pub)
        self.sim.send_object.assert_called_once()
        sent_subscriber, sent_payload = self.sim.send_object.call_args.args
        self.assertIs(sent_subscriber, observer)
        self.assertTrue(isinstance(sent_payload, SourceAwareEvent))
        self.assertEqual(sent_payload.event, 'evt')
        self.assertIs(sent_payload.source, pub)

    def test_consume_phase_mixes_direct_and_routed_dispatch(self):
        pub = DSPub(sim=self.sim)
        c0 = _DirectSubscriber(False, sim=self.sim)
        c1 = _RoutedSubscriber(True, sim=self.sim, cond=lambda e: True)
        pub.add_subscriber(c0, phase=DSPub.Phase.CONSUME)
        pub.add_subscriber(c1, phase=DSPub.Phase.CONSUME)

        pub.send('evt')

        self.assertEqual(c0.events, ['evt'])
        self.assertEqual(len(c1.events), 1)
        observed = c1.events[0]
        self.assertTrue(isinstance(observed, SourceAwareEvent))
        self.assertEqual(observed.event, 'evt')
        self.assertIs(observed.source, pub)
        self.sim.send_object.assert_called_once()
        sent_subscriber, sent_payload = self.sim.send_object.call_args.args
        self.assertIs(sent_subscriber, c1)
        self.assertTrue(isinstance(sent_payload, SourceAwareEvent))
        self.assertEqual(sent_payload.event, 'evt')
        self.assertIs(sent_payload.source, pub)

    def test_plain_dssub_defaults_to_direct_dispatch(self):
        pub = DSPub(sim=self.sim)
        observer = _PlainSubscriber(False, sim=self.sim)
        pub.add_subscriber(observer, phase=DSPub.Phase.PRE)

        pub.send('evt')

        self.assertTrue(observer.dispatch_direct)
        self.assertFalse(observer.dispatch_source_aware)
        self.assertEqual(observer.events, ['evt'])
        self.sim.send_object.assert_not_called()

    def test_pre_observer_source_aware_uses_wrapped_payload(self):
        pub = DSPub(sim=self.sim)
        observer = _SourceAwareSubscriber(False, sim=self.sim)
        pub.add_subscriber(observer, phase=DSPub.Phase.PRE)

        pub.send('evt')

        self.assertEqual(len(observer.events), 1)
        wrapped = observer.events[0]
        self.assertTrue(isinstance(wrapped, SourceAwareEvent))
        self.assertEqual(wrapped.event, 'evt')
        self.assertIs(wrapped.source, pub)
        self.sim.send_object.assert_called_once()
        sent_subscriber, sent_payload = self.sim.send_object.call_args.args
        self.assertIs(sent_subscriber, observer)
        self.assertTrue(isinstance(sent_payload, SourceAwareEvent))

    def test_pre_source_aware_reuses_same_wrapper_for_same_payload(self):
        pub = DSPub(sim=self.sim)
        o1 = _RoutedSubscriber(False, sim=self.sim, cond=lambda e: True)
        o2 = _RoutedSubscriber(False, sim=self.sim, cond=lambda e: True)
        pub.add_subscriber(o1, phase=DSPub.Phase.PRE)
        pub.add_subscriber(o2, phase=DSPub.Phase.PRE)

        pub.send('evt')

        self.assertEqual(len(o1.events), 1)
        self.assertEqual(len(o2.events), 1)
        self.assertIs(o1.events[0], o2.events[0])
        self.assertTrue(isinstance(o1.events[0], SourceAwareEvent))
        calls = self.sim.send_object.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertIs(calls[0].args[1], calls[1].args[1])

    def test_plain_dssub_consume_short_circuit(self):
        pub = DSPub(sim=self.sim)
        c0 = _PlainSubscriber(True, sim=self.sim)
        c1 = _PlainSubscriber(True, sim=self.sim)
        pub.add_subscriber(c0, phase=DSPub.Phase.CONSUME)
        pub.add_subscriber(c1, phase=DSPub.Phase.CONSUME)

        pub.send('evt')

        self.assertEqual(c0.events, ['evt'])
        self.assertEqual(c1.events, [])
        self.sim.send_object.assert_not_called()

    def test_plain_dssub_post_hit_receives_payload(self):
        pub = DSPub(sim=self.sim)
        consumer = _PlainSubscriber(True, sim=self.sim)
        hit_observer = _PlainSubscriber(False, sim=self.sim)
        pub.add_subscriber(consumer, phase=DSPub.Phase.CONSUME)
        pub.add_subscriber(hit_observer, phase=DSPub.Phase.POST_HIT)

        pub.send('evt')

        self.assertEqual(len(hit_observer.events), 1)
        payload = hit_observer.events[0]
        self.assertEqual(payload, {'consumer': consumer, 'event': 'evt'})
        self.sim.send_object.assert_not_called()

    def test_plain_dssub_post_miss_receives_event(self):
        pub = DSPub(sim=self.sim)
        consumer = _PlainSubscriber(False, sim=self.sim)
        miss_observer = _PlainSubscriber(False, sim=self.sim)
        pub.add_subscriber(consumer, phase=DSPub.Phase.CONSUME)
        pub.add_subscriber(miss_observer, phase=DSPub.Phase.POST_MISS)

        pub.send('evt')

        self.assertEqual(miss_observer.events, ['evt'])
        self.sim.send_object.assert_not_called()

    def test_trackable_event_forwarded_through_endpoints_without_crash(self):
        tx1 = self.sim.publisher(name='tx1')
        tx2 = self.sim.publisher(name='tx2')
        received = []

        def _forward(event):
            tx2.signal(event)
            return True

        forwarder = self.sim.callback(_forward, name='forwarder')
        sink = self.sim.callback(lambda e: (received.append(e), True)[1], name='sink')

        tx1.add_subscriber(forwarder, tx1.Phase.CONSUME)
        tx2.add_subscriber(sink, tx2.Phase.CONSUME)

        event = DSTrackableEvent({'id': 1})
        self.sim.schedule_event(0, event, tx1)
        self.sim.run()

        self.assertEqual(received, [event])
        trail = [getattr(node, 'name', None) for node in event.publishers]
        self.assertEqual(trail, ['tx1', 'forwarder', 'tx2', 'sink'])
        
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
