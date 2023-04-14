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
from dssim.simulation import DSProcess, DSCallback, DSKWCallback, DSSimulation
from dssim.pubsub import DSProducer, NotifierDict, NotifierRoundRobin, NotifierPriority

class SimMock:
    pass

class SomeObj:
    pass

class SomeIterableObj:
    def __iter__(self):
        pass

__all__ = ['TestPubSub']


class TestCallback(unittest.TestCase):
    ''' Test the DSCallback '''

    def test0_fcn(self):
        my_consumer_fcn = Mock()
        c = DSCallback(my_consumer_fcn, sim=SomeObj())
        c.send({'data': 1})
        my_consumer_fcn.assert_called_once_with({'data': 1})
        my_consumer_fcn.reset_mock()
        c.send({'data': 0})
        my_consumer_fcn.assert_called_once_with({'data': 0})
        my_consumer_fcn.reset_mock()

    def test1_kw_fcn(self):
        my_consumer_fcn = Mock()
        c = DSKWCallback(my_consumer_fcn, sim=SomeObj())
        c.send({'data': 1})
        my_consumer_fcn.assert_called_once_with(data=1)
        my_consumer_fcn.reset_mock()
        c.send({'data': 0})
        my_consumer_fcn.assert_called_once_with(data=0)
        my_consumer_fcn.reset_mock()

    def test2_method(self):
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

    def test3_kw_method(self):
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

    def test4_consumer_with_filter(self):
        my_consumer_fcn = Mock()
        c = DSCallback(my_consumer_fcn, cond=lambda e:e['data'] > 0, sim=SomeObj())
        c.send({'data': 1})
        my_consumer_fcn.assert_called_once_with({'data': 1})
        my_consumer_fcn.reset_mock()
        c.send({'data': 0})
        my_consumer_fcn.send.assert_not_called()
        my_consumer_fcn.reset_mock()

    def test5_kw_consumer_with_filter(self):
        my_consumer_fcn = Mock()
        c = DSKWCallback(my_consumer_fcn, cond=lambda e:e['data'] > 0, sim=SomeObj())
        c.send({'data': 1})
        my_consumer_fcn.assert_called_once_with(data=1)
        my_consumer_fcn.reset_mock()
        c.send({'data': 0})
        my_consumer_fcn.send.assert_not_called()
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
        self.sim.send = Mock(return_value=True) # always returns true
        self.sim.schedule = Mock(return_value=1000) # new process id retval
        self.sim.schedule_event = Mock()

    def test0_producer_add(self):
        p = DSProducer(sim=self.sim)
        process = self.__my_process_consumer()
        c0 = DSProcess(process, start=True, sim=self.sim)
        c1 = DSProcess(process, start=True, sim=self.sim)
        p.add_subscriber(subscriber=c0)
        self.assertEqual(p.subs['pre'].d, {})
        self.assertEqual(p.subs['act'].d, {c0: 1})
        self.assertEqual(p.subs['post'].d, {})
        p.add_subscriber(subscriber=c1)
        self.assertEqual(p.subs['pre'].d, {})
        self.assertEqual(p.subs['act'].d, {c0: 1, c1: 1})
        self.assertEqual(p.subs['post'].d, {})
        p.add_subscriber(subscriber=c0)
        self.assertEqual(p.subs['pre'].d, {})
        self.assertEqual(p.subs['act'].d, {c0: 2, c1: 1})
        self.assertEqual(p.subs['post'].d, {})
        p.add_subscriber(phase='pre', subscriber=c0)
        self.assertEqual(p.subs['pre'].d, {c0: 1})
        self.assertEqual(p.subs['act'].d, {c0: 2, c1: 1})
        self.assertEqual(p.subs['post'].d, {})
        p.add_subscriber(phase='post', subscriber=c1)
        self.assertEqual(p.subs['pre'].d, {c0: 1})
        self.assertEqual(p.subs['act'].d, {c0: 2, c1: 1})
        self.assertEqual(p.subs['post'].d, {c1: 1})
        c2 = lambda e: False
        c3 = lambda e: True
        p.add_subscriber(phase='post', subscriber=c2)
        self.assertEqual(p.subs['pre'].d, {c0: 1})
        self.assertEqual(p.subs['act'].d, {c0: 2, c1: 1})
        self.assertEqual(p.subs['post'].d, {c2: 1, c1: 1})
        p.add_subscriber(phase='post', subscriber=c2)
        self.assertEqual(p.subs['pre'].d, {c0: 1})
        self.assertEqual(p.subs['act'].d, {c0: 2, c1: 1})
        self.assertEqual(p.subs['post'].d, {c2: 2, c1: 1})
        p.add_subscriber(phase='pre', subscriber=c3)
        self.assertEqual(p.subs['pre'].d, {c3: 1, c0: 1})
        self.assertEqual(p.subs['act'].d, {c0: 2, c1: 1})
        self.assertEqual(p.subs['post'].d, {c2: 2, c1: 1})

    def test1_producer_remove(self):
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
        p.subs['pre'].d = {}
        p.subs['act'].d = {c0: 1}
        p.subs['post'].d = {}
        p.remove_subscriber(subscriber=c0)
        self.assertEqual(p.subs['pre'].d, {})
        self.assertEqual(p.subs['act'].d, {c0: 0})
        self.assertEqual(p.subs['post'].d, {})
        p.send(None)
        self.assertEqual(p.subs['pre'].d, {})
        self.assertEqual(p.subs['act'].d, {})
        self.assertEqual(p.subs['post'].d, {})

        p.subs['pre'].d = {}
        p.subs['act'].d = {c0: 1, c1: 1}
        p.subs['post'].d = {}
        p.remove_subscriber(subscriber=c0)
        self.assertEqual(p.subs['pre'].d, {})
        self.assertEqual(p.subs['act'].d, {c0: 0, c1:1})
        self.assertEqual(p.subs['post'].d, {})
        p.send(None)
        self.assertEqual(p.subs['pre'].d, {})
        self.assertEqual(p.subs['act'].d, {c1: 1})
        self.assertEqual(p.subs['post'].d, {})

        p.subs['pre'].d = {c0: 1, c1: 1}
        p.subs['act'].d = {c0: 1, c1: 1}
        p.subs['post'].d = {}
        p.remove_subscriber(subscriber=c0)
        self.assertEqual(p.subs['pre'].d, {c0: 1, c1: 1})
        self.assertEqual(p.subs['act'].d, {c0: 0, c1: 1})
        self.assertEqual(p.subs['post'].d, {})
        p.send(None)
        self.assertEqual(p.subs['pre'].d, {c0: 1, c1: 1})
        self.assertEqual(p.subs['act'].d, {c1: 1})
        self.assertEqual(p.subs['post'].d, {})
        p.remove_subscriber(phase='pre', subscriber=c1)
        self.assertEqual(p.subs['pre'].d, {c0: 1, c1: 0})
        self.assertEqual(p.subs['act'].d, {c1: 1})
        self.assertEqual(p.subs['post'].d, {})
        p.send(None)
        self.assertEqual(p.subs['pre'].d, {c0: 1})
        self.assertEqual(p.subs['act'].d, {c1: 1})
        self.assertEqual(p.subs['post'].d, {})

        c2 = SomeIterableObj()
        p.subs['pre'].d = {c0: 1, c2: 1}
        p.subs['act'].d = {c1: 1, c2: 1}
        p.subs['post'].d = {}
        p.remove_subscriber(phase='pre', subscriber=c2)
        self.assertEqual(p.subs['pre'].d, {c0: 1, c2: 0})
        self.assertEqual(p.subs['act'].d, {c1: 1, c2: 1})
        self.assertEqual(p.subs['post'].d, {})
        p.remove_subscriber(subscriber=c2)
        self.assertEqual(p.subs['pre'].d, {c0: 1, c2: 0})
        self.assertEqual(p.subs['act'].d, {c1: 1, c2: 0})
        self.assertEqual(p.subs['post'].d, {})

    def test2_producer_signal_act_retval(self):
        self.sim.try_send = Mock(return_value=False)
        p = DSProducer(sim=self.sim)
        c0 = DSCallback(None, sim=self.sim)
        c1 = DSCallback(None, sim=self.sim)
        p.add_subscriber(c0)
        p.add_subscriber(c1)
        p.send(1)
        self.sim.try_send.assert_has_calls([call(c0, 1), call(c1, 1)])
        notify_fcn = Mock(return_value=True)       
        p = DSProducer(sim=self.sim)
        c0 = DSCallback(notify_fcn, sim=self.sim)
        c1 = DSCallback(notify_fcn, sim=self.sim)
        p.add_subscriber(c0)
        p.add_subscriber(c1)
        p.send(2)
        self.sim.try_send.assert_has_calls([call(c0, 2),])

    def test3_producer_signal_act(self):
        self.sim.try_send = Mock(return_value=True)
        p = DSProducer(sim=self.sim)
        c0 = DSCallback(None, sim=self.sim)
        c1 = DSCallback(None, sim=self.sim)
        p.add_subscriber(c0)
        p.add_subscriber(c1)
        p.send(1)
        self.sim.try_send.assert_called_once_with(c0, 1)

        self.sim.try_send.reset_mock()
        p.add_subscriber(subscriber=c0)  # 2 times a subscriber
        p.send(2)
        self.sim.try_send.assert_called_once_with(c0, 2)

    def test4_producer_signal_pre(self):
        self.sim.try_send = Mock(return_value=True)
        p = DSProducer(sim=self.sim)
        c0 = DSCallback(None, sim=self.sim)
        c1 = DSCallback(None, sim=self.sim)
        p.add_subscriber(c0, phase='pre')
        p.add_subscriber(c1, phase='pre')
        p.send(1)
        self.sim.try_send.assert_has_calls([call(c0, 1), call(c1, 1)])

        self.sim.try_send.reset_mock()
        p.add_subscriber(c0, phase='pre')  # 2 times a subscriber
        p.send(2)
        self.sim.try_send.assert_has_calls([call(c0, 2), call(c1, 2)])

    def test5_producer_signal_post(self):
        self.sim.try_send = Mock(return_value=True)
        p = DSProducer(sim=self.sim)
        c0 = DSCallback(None, sim=self.sim)
        c1 = DSCallback(None, sim=self.sim)
        p.add_subscriber(c0, phase='post')
        p.add_subscriber(c1, phase='post')
        p.send(1)
        self.sim.try_send.assert_has_calls([call(c0, 1), call(c1, 1)])

        self.sim.try_send.reset_mock()
        p.add_subscriber(c0, phase='post')  # 2 times a subscriber
        p.send(2)
        self.sim.try_send.assert_has_calls([call(c0, 2), call(c1, 2)])


    def test6_producer_signal_same(self):
        c0 = DSCallback(None, sim=self.sim)
        c1 = DSCallback(None, sim=self.sim)
        self.sim.try_send = Mock(return_value=False)
        tests = ( 
            ('pre', 'c0c1', True, True),
            ('pre', 'c1c0', True, True),
            ('act', 'c0c1', True, True),
            ('act', 'c1c0', False, True),
            ('post', 'c0c1', True, True),
            ('post', 'c1c0', True, True),
        )
        for phase, order, c0_called, c1_called in tests:
            self.sim.try_send.reset_mock()
            p = DSProducer(sim=self.sim)
            if order == 'c0c1':
                p.add_subscriber(phase=phase, subscriber=c0)
                p.add_subscriber(phase=phase, subscriber=c1)
            else:
                p.add_subscriber(phase=phase, subscriber=c1)
                p.add_subscriber(phase=phase, subscriber=c0)
            p.send(None)
            calls = []
            if c0_called:
                calls.append(call(c0, None))
            if c1_called:
                calls.append(call(c1, None))
            self.sim.try_send.assert_has_calls(calls, any_order=True)


    def test7_producer_signal_combi(self):
        c0 = DSCallback(None, sim=self.sim)
        c1 = DSCallback(None, sim=self.sim)
        self.sim.try_send = Mock(return_value=False)

        tests = ( 
            ('pre', 'act', True, True),
            ('act', 'pre', True, True),
            ('pre', 'post', True, True),
            ('post', 'pre', True, True),
            ('act', 'post', True, True),
            ('post', 'act', False, True),
        )
        for c0_phase, c1_phase, c0_called, c1_called in tests:
            self.sim.try_send.reset_mock()
            p = DSProducer(sim=self.sim)
            p.add_subscriber(phase=c0_phase, subscriber=c0)
            p.add_subscriber(phase=c1_phase, subscriber=c1)
            p.send(None)
            calls = []
            if c0_called:
                calls.append(call(c0, None))
            if c1_called:
                calls.append(call(c1, None))
            self.sim.try_send.assert_has_calls(calls, any_order=True)


    def test8_producer_add_subscriber_in_send_hook(self):
        ''' Test the behavior of signal function when send handler adds a subscriber '''
        self.sim = DSSimulation()
        p = DSProducer(sim=self.sim)
        c0 = DSCallback(Mock(return_value=False), sim=self.sim)
        c1 = DSCallback(lambda e: p.add_subscriber(subscriber=c0), sim=self.sim)
        p.add_subscriber(subscriber=c1)
        p.add_subscriber(subscriber=c0)
        self.assertEqual(p.subs['pre'].d, {})
        self.assertEqual(p.subs['act'].d, {c0: 1, c1: 1})
        self.assertEqual(p.subs['post'].d, {})
        p.send(None)
        c0.forward_method.assert_called_once()
        self.assertEqual(p.subs['pre'].d, {})
        self.assertEqual(p.subs['act'].d, {c0: 2, c1: 1})
        self.assertEqual(p.subs['post'].d, {})


    def test9_producer_remove_subscriber_in_send_hook(self):
        ''' Test the behavior of signal function when send handler removes a subscriber '''
        self.sim = DSSimulation()
        p = DSProducer(sim=self.sim)
        c0 = DSCallback(Mock(return_value=False), sim=self.sim)
        c1 = DSCallback(lambda e: p.remove_subscriber(subscriber=c1), sim=self.sim)
        p.add_subscriber(subscriber=c1)
        p.add_subscriber(subscriber=c0)
        self.assertEqual(p.subs['pre'].d, {})
        self.assertEqual(p.subs['act'].d, {c0: 1, c1: 1})
        self.assertEqual(p.subs['post'].d, {})
        p.send(None)
        c0.forward_method.assert_called_once()
        self.assertEqual(p.subs['pre'].d, {})
        self.assertEqual(p.subs['act'].d, {c0: 1})
        self.assertEqual(p.subs['post'].d, {})

class TestNotifierDict(unittest.TestCase):

    def test0_inc_dec(self):
        n = NotifierDict()
        self.assertTrue(n.d == {})
        n.inc('a'), n.inc('a')
        self.assertEqual(n.d, {'a': 2})
        n.inc('b'), n.inc('a')
        self.assertEqual(n.d, {'a': 3, 'b': 1})
        n.dec('a'), n.inc('b')
        self.assertEqual(n.d, {'a': 2, 'b': 2})
        n.dec('a'), n.dec('a')
        self.assertEqual(n.d, {'a': 0, 'b': 2})

    def test1_iter_change(self):
        n = NotifierDict()
        n.inc('a')
        count = 0
        for item in n:
            n.inc('b')
            n.dec('a')
            count += 1
        self.assertTrue(count == 1)

    def test2_cleanup(self):
        n = NotifierDict()
        self.assertEqual(n.d, {})
        n.cleanup()
        self.assertEqual(n.d, {})
        n.d = {'a': 2, 'b': 3}
        n.cleanup()
        self.assertEqual(n.d, {'a': 2, 'b': 3})
        n.dec('a'), n.dec('a')
        self.assertEqual(n.d, {'a': 0, 'b': 3})
        n.cleanup()
        self.assertEqual(n.d, {'b': 3})
        n.dec('b'), n.dec('b'), n.dec('b')
        self.assertEqual(n.d, {'b': 0})
        n.cleanup()
        self.assertEqual(n.d, {})

    def test3_iter(self):
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

    def test3_rewind(self):
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

    def test0_inc_dec(self):
        n = NotifierRoundRobin()
        self.assertTrue(n.queue == [])
        n.inc('a'), n.inc('a')
        self.assertEqual(n.queue, [['a', 2]])
        n.inc('b'), n.inc('a')
        self.assertEqual(n.queue, [['a', 3], ['b', 1]])
        n.dec('a'), n.inc('b')
        self.assertEqual(n.queue, [['a', 2], ['b', 2]])
        n.dec('a'), n.dec('a')
        self.assertEqual(n.queue, [['a', 0], ['b', 2]])

    def test1_iter_change(self):
        n = NotifierRoundRobin()
        n.inc('a')
        count = 0
        for item in n:
            n.inc('b')
            n.dec('a')
            count += 1
        self.assertTrue(count == 1)

    def test2_cleanup(self):
        n = NotifierRoundRobin()
        self.assertEqual(n.queue, [])
        n.cleanup()
        self.assertEqual(n.queue, [])
        n.queue = [['a', 2], ['b', 3]]
        n.cleanup()
        self.assertEqual(n.queue, [['a', 2], ['b', 3]])
        n.dec('a'), n.dec('a')
        self.assertEqual(n.queue, [['a', 0], ['b', 3]])
        n.cleanup()
        self.assertEqual(n.queue, [['b', 3]])
        n.dec('b'), n.dec('b'), n.dec('b')
        self.assertEqual(n.queue, [['b', 0]])
        n.cleanup()
        self.assertEqual(n.queue, [])

    def test3_iter(self):
        n = NotifierRoundRobin()
        n.queue = [['c', 1], ['a', 2], ['b', 4]]
        it = iter(n)
        el = next(it)
        self.assertTrue(el == ['c', 1])
        el = next(it)
        self.assertTrue(el == ['a', 2])
        el = next(it)
        self.assertTrue(el == ['b', 4])
        with self.assertRaises(StopIteration):
            el = next(it)

    def test3_rewind(self):
        n = NotifierRoundRobin()
        n.queue = [['c', 1], ['a', 2], ['b', 4],]
        it = iter(n)
        next(it), next(it)
        n.rewind()
        self.assertEqual(n.queue, [['b', 4], ['c', 1], ['a', 2],])

        it = iter(n)
        next(it), next(it), next(it)
        n.rewind()
        self.assertEqual(n.queue, [['b', 4], ['c', 1], ['a', 2],])

        it = iter(n)
        n.rewind()
        self.assertEqual(n.queue, [['b', 4], ['c', 1], ['a', 2],])

class TestNotifierPriority(unittest.TestCase):

    def test0_inc_dec(self):
        n = NotifierPriority()
        self.assertTrue(n.d == {})
        n.inc('a', priority=1), n.inc('a', priority=1)
        self.assertEqual(n.d, {1: {'a': 2}})
        n.inc('b', priority=1), n.inc('a', priority=2)
        self.assertEqual(n.d, {1: {'a': 2, 'b': 1}, 2: {'a': 1}})
        n.dec('a', priority=1), n.inc('b', priority=1)
        self.assertEqual(n.d, {1: {'a': 1, 'b': 2}, 2: {'a': 1}})
        n.dec('a', priority=1)
        self.assertEqual(n.d, {1: {'a': 0, 'b': 2}, 2: {'a': 1}})
        n.dec('a', priority=2)
        self.assertEqual(n.d, {1: {'a': 0, 'b': 2}, 2: {'a': 0}})

    def test1_iter_change(self):
        n = NotifierPriority()
        n.inc('a', priority=1)
        count = 0
        for item in n:
            n.inc('b', priority=1)
            n.dec('a', priority=1)
            count += 1
        self.assertTrue(count == 1)

    def test2_cleanup(self):
        n = NotifierPriority()
        self.assertEqual(n.d, {})
        n.cleanup()
        self.assertEqual(n.d, {})
        n.d = {1: {'a': 2, 'b': 3}, 2: {'a': 1}}
        n.cleanup()
        self.assertEqual(n.d, {1: {'a': 2, 'b': 3}, 2: {'a': 1}})
        n.dec('a', priority=1), n.dec('a', priority=1)
        self.assertEqual(n.d, {1: {'a': 0, 'b': 3}, 2: {'a': 1}})
        n.cleanup()
        self.assertEqual(n.d, {1: {'b': 3}, 2: {'a': 1}})
        n.dec('a', priority=2)
        n.cleanup()
        self.assertEqual(n.d, {1: {'b': 3}})
        n.dec('b', priority=1), n.dec('b', priority=1), n.dec('b', priority=1)
        n.cleanup()
        self.assertEqual(n.d, {})

    def test3_iter(self):
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

    def test4_rewind(self):
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
