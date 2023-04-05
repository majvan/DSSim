# Copyright 2020 NXP Semiconductors
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
Tests for simulation module
'''
import unittest
from unittest.mock import Mock, MagicMock, call
from dssim.simulation import DSSimulation, DSAbortException, DSFuture, DSSchedulable, DSProcess
from dssim.simulation import _StackedCond
from dssim.simulation import DSSubscriberContextManager
from dssim.simulation import DSInterruptibleContext, DSTimeoutContextError
from dssim.pubsub import DSProducer

class SomeObj:
    pass

class SomeCallableObj:
    def __call__(self, event):
        return True

class FutureMock(Mock):
    def get_future_eps(self):
        return {self,}

class EventForwarder:
    ''' This represents basic forwarder which forwards events from time_process into a waiting
    process. Some kind of a DSProducer which produces data into one exact running process
    '''
    def __init__(self, test_unit_running_sim, receiving_process):
        self.testunit = test_unit_running_sim
        self.receiving_process = receiving_process

    def send(self, **data):
        self.testunit.sim.send(self.receiving_process, **data)

class TestDSSchedulable(unittest.TestCase):

    @DSSchedulable
    def __fcn(self):
        return 'Success'

    def __generator(self):
        yield 'First return'
        yield 'Second return'
        return 'Success'

    def __loopback_generator(self):
        data = yield
        while True:
            data = yield data

    @DSSchedulable
    def __waiting_for_join(self, process):
        yield from process.join()
        yield "After process finished"


    def test0_schedulable_fcn(self):
        process = self.__fcn()
        try:
            next(process)
        except StopIteration as e:
            retval = e.value
        self.assertEqual(retval, 'Success')

    def test1_schedulable_fcn_as_process(self):
        sim = DSSimulation()
        process = DSProcess(self.__fcn(), sim=sim)
        try:
            next(process)
        except StopIteration as e:
            retval = e.value
        self.assertEqual(retval, 'Success')

        process = DSProcess(self.__fcn(), sim=sim)
        retval = sim.send(process, None)
        self.assertEqual(retval, 'Success')
        self.assertEqual(process.value, 'Success')

    def test2_generator(self):
        process = self.__generator()
        retval = next(process)
        self.assertEqual(retval, 'First return')
        retval = next(process)
        self.assertEqual(retval, 'Second return')
        try:
            next(process)
        except StopIteration as e:
            retval = e.value
        self.assertEqual(retval, 'Success')

    def test3_generator_as_process(self):
        sim = DSSimulation()
        process = DSProcess(self.__generator(), sim=sim)
        retval = next(process)
        self.assertEqual(retval, 'First return')
        retval = next(process)
        self.assertEqual(retval, 'Second return')
        try:
            next(process)
        except StopIteration as e:
            retval = e.value
        self.assertEqual(retval, 'Success')

        process = DSProcess(self.__generator(), sim=sim)
        retval = next(process)
        self.assertEqual(retval, 'First return')
        retval = next(process)
        self.assertEqual(retval, 'Second return')
        retval = sim.send(process, None)
        self.assertEqual(retval, 'Success')
        self.assertEqual(process.value, 'Success')


    def test4_send_to_generator(self):
        process = self.__generator()
        retval = next(process)
        self.assertEqual(retval, 'First return')
        retval = process.send('anything0')
        self.assertEqual(retval, 'Second return')
        try:
            retval = process.send('anything1')
        except StopIteration as e:
            retval2 = e.value
        self.assertEqual(retval2, 'Success')

        try:
            retval = process.send('anything2')
        except StopIteration as e:
            retval2 = e.value
        self.assertEqual(retval2, None)

    def test5_send_to_process(self):
        sim = DSSimulation()
        process = DSProcess(self.__generator(), sim=sim)
        retval = next(process)
        self.assertEqual(retval, 'First return')
        retval = process.send('anything0')
        self.assertEqual(retval, 'Second return')
        try:
            retval = process.send('anything1')
        except StopIteration as e:
            retval2 = e.value
        self.assertEqual(retval2, 'Success')

        sim = DSSimulation()
        process = DSProcess(self.__generator(), sim=sim)
        retval = next(process)
        self.assertEqual(retval, 'First return')
        retval = process.send('anything0')
        self.assertEqual(retval, 'Second return')
        retval = sim.schedule_event(1, 'anything0', process)
        sim.run()
        self.assertEqual(process.value, 'Success')


    def test6_send_abort_to_generator(self):
        process = self.__loopback_generator()
        retval = next(process)
        retval = process.send('from_test0')
        self.assertEqual(retval, 'from_test0')
        retval = process.send(DSAbortException(producer='test'))
        self.assertTrue(isinstance(retval, DSAbortException))

    def test7_send_abort_to_generator_as_process(self):
        class MyExc(Exception):
            pass
        def my_wait(sim):
            i = 0
            while True:
                i = i + 1
                yield from sim.gwait(cond=lambda c: True, val=i)

        sim=DSSimulation()
        process = DSProcess(my_wait(sim), sim=sim)
        retval = next(process)
        retval = process.send('from_test0')
        self.assertEqual(retval, 2)
        self.assertEqual(process.value, 2)
        self.assertEqual(process.exc, None)
        process.abort()
        self.assertTrue(isinstance(process.exc, DSAbortException))
        self.assertEqual(process.value, 2)

        process = DSProcess(my_wait(sim), sim=sim)
        retval = next(process)
        process.abort(MyExc())
        self.assertTrue(isinstance(process.exc, MyExc))
        self.assertEqual(process.value, 1)


    def test8_joining_process(self):
        sim = DSSimulation()
        process = DSProcess(self.__generator(), sim=sim)
        process.join = MagicMock()
        process.join.return_value = iter(['Join called',])
        process_waiting = DSProcess(self.__waiting_for_join(process), sim=DSSimulation())
        retval = next(process)
        self.assertEqual(retval, 'First return')
        self.assertEqual(process.value, 'First return')
        sim.parent_process = process_waiting
        retval = next(process_waiting)
        self.assertEqual(process.value, 'First return')  # process not changed
        self.assertEqual(process_waiting.value, 'Join called')
        retval = next(process)
        self.assertEqual(process.value, 'Second return')
        self.assertEqual(process_waiting.value, 'Join called')
        with self.assertRaises(StopIteration):
            retval = next(process)
        # self.assertEqual(process.value, 'Success')  # This will not work as the process.value is set only with simulation run
        retval = next(process_waiting)
        self.assertEqual(process_waiting.value, 'After process finished')


class TestException(unittest.TestCase):

    def __my_buggy_code(self):
        yield 'First is ok'
        a = 10 / 0
        return 'Second unreachable'

    def __first_cyclic(self):
        yield 'Kick-on first'
        self.sim.send(self.process2, 'Signal from first process')
        yield 'After signalling first'
        return 'Done first'

    def __second_cyclic(self):
        yield 'Kick-on second'
        self.sim.send(self.process1, 'Signal from second process')
        yield 'After signalling second'
        return 'Done second'

    def setUp(self):
        self.sim = DSSimulation()
        self.__time_process_event = Mock()

    def test0_exception_usercode_generator(self):
        process = self.__my_buggy_code()
        self.sim._kick(process)
        exc_to_check = None
        try:
            self.sim.send(process, 'My data')
            # we should not get here, exception is expected
            self.assertTrue(1 == 2)
        except ZeroDivisionError as exc:
            self.assertTrue('generator already executing' not in str(exc))

    def test1_exception_usercode_generators(self):
        sim = DSSimulation()
        self.process1 = self.__first_cyclic()
        self.process2 = self.__second_cyclic()
        sim._kick(self.process1)
        sim._kick(self.process2)
        try:
            self.sim.send(self.process1, 'My data')
            # we should not get here, exception is expected
            self.assertTrue(1 == 2)
        except ValueError as exc:
            self.assertTrue('generator already executing' in str(exc))

    def test2_exception_usercode_process(self):
        sim = DSSimulation()
        self.process1 = DSProcess(self.__first_cyclic(), name="First cyclic", sim=self.sim)
        self.process2 = DSProcess(self.__second_cyclic(), name="Second cyclic", sim=self.sim)
        sim._kick(self.process1)
        sim._kick(self.process2)
        try:
            self.sim.send(self.process1, 'My data')
            # we should not get here, exception is expected
            self.assertTrue(1 == 2)
        except ValueError as exc:
            self.assertTrue('generator already executing' in str(exc))

class TestConditionChecking(unittest.TestCase):
    ''' Test the processing of the events by the simulation '''
    def __my_process(self):
        while True:
            yield 1

    def test0_process_metadata(self):
        sim = DSSimulation()
        self.assertTrue(len(sim._consumer_metadata) == 0)
        p = DSProcess(self.__my_process(), sim=sim)
        p.meta = 'My meta'
        meta = sim.get_consumer_metadata(p)
        self.assertEqual(meta, p.meta)
        self.assertTrue(len(sim._consumer_metadata) == 0)

        p = self.__my_process()
        self.assertTrue(len(sim._consumer_metadata) == 0)
        meta = sim.get_consumer_metadata(p)
        self.assertIsNotNone(meta)
        self.assertTrue(len(sim._consumer_metadata) == 1)  # write the metadata of the generator into the simulation registry
        meta = sim.get_consumer_metadata(p)
        self.assertIsNotNone(meta)
        self.assertTrue(len(sim._consumer_metadata) == 1)  # the next retrieve does not increase the registry

    def test1_check_storing_cond_in_metadata(self):
        ''' By calling wait, the metadata.cond should be stored '''
        def my_process():
            if True:
                return 100
            yield 101

        sim = DSSimulation()
        sim._wait_for_event = my_process
        process = DSProcess(my_process(), sim=sim)
        process.meta.cond = Mock()
        sim.parent_process = process
        waitable = sim.gwait(cond='condition')
        retval = next(waitable)
        self.assertTrue(retval)
        try:
            retval = next(waitable)
        except StopIteration as e:
            retval = e.value
        self.assertEqual(retval, None)
        process.meta.cond.push.assert_called_with('condition')

        condition = SomeObj()
        condition.cond_value = lambda e: 'condition value was computed in lambda'
        waitable = sim.gwait(cond=condition)
        retval = next(waitable)
        self.assertTrue(retval)
        try:
            retval = next(waitable)
        except StopIteration as e:
            retval = e.value
        self.assertEqual(retval, 'condition value was computed in lambda')
        process.meta.cond.push.assert_called_with(condition)
    
    def test2_check_cond(self):
        ''' Test 5 types of conditions - see _check_cond '''
        sim = DSSimulation()
        exception = Exception('error')
        for cond, event, expected_result in (
            (lambda e:False, None, (True, None)),
            (lambda e:True, None, (True, None)),
            ('abc', None, (True, None)),
            (None, None, (True, None)),
            (lambda e:False, exception, (True, exception)),
            (lambda e:True, exception, (True, exception)),
            ('abc', exception, (True, exception)),
            (exception, exception, (True, exception)),
            (lambda e:False, 'def', (False, None)),
            (lambda e:True, 'def', (True, 'def')),
            ('abc', 'def', (False, None)),
            ('def', 'def', (True, 'def')),
        ):
            retval = _StackedCond(cond).check(event)
            self.assertEqual(retval, expected_result)

    def test3_check_condition(self):
        ''' The check_condition should retrieve cond from the metadata and then call _check_cond '''
        sim = DSSimulation()
        p = DSProcess(self.__my_process(), sim=sim)
        p.meta = SomeObj()
        p.meta.cond = MagicMock()
        p.meta.cond.check = Mock(return_value=(True, 'abc'))
        retval = sim.check_condition(p, 'test')
        p.meta.cond.check.assert_called_once()
        self.assertEqual(retval, True)
    
    def test4_early_check(self):
        ''' Test if signal calls first check_condition and then send_object '''
        sim = DSSimulation()
        sim.check_condition = Mock(return_value=False)  # it will not allow to accept the event
        sim.send_object = Mock()
        consumer = Mock()
        # sim.check_condition.side_effect = lambda *a, **kw: call_order.append(call(*a, **kw))
        # sim.send_object.side_effect = lambda *a, **kw: call_order.append(call(*a, **kw))
        sim.send(consumer, None)
        sim.check_condition.assert_called_once()
        sim.send_object.assert_not_called()

        call_order = []
        sim = DSSimulation()
        def add_to_call_order(fcn_name, *args, **kwargs):
            call_order.append(call(fcn_name, *args, **kwargs))
            return True
        sim.check_condition = Mock(side_effect=lambda *a, **kw: add_to_call_order('check_condition', *a, **kw))  # it will allow to accept the event
        sim.send_object = Mock(side_effect=lambda *a, **kw: add_to_call_order('send_object', *a, **kw))
        # sim.check_condition.side_effect = 
        # sim.send_object.side_effect = lambda *a, **kw: call_order.append(call(*a, **kw))
        sim.send(consumer, None)
        sim.check_condition.assert_called_once()
        sim.send_object.assert_called_once()
        self.assertEqual(call_order, [call('check_condition', consumer, None), call('send_object', consumer, None)])

    def test5_check_and_gwait(self):
        ''' Test check_and_wait function. First it should call check and if check does not pass, it should call wait '''
        sim = DSSimulation()
        retval = 'abc'
        # The generator sim.check_and_wait yields in the middle with the value back, which is by default "True"
        retval = next(sim.check_and_gwait(cond=lambda c:False))
        self.assertTrue(retval == True)
        sim.get_consumer_metadata(None).cond.pop()  # remove stored condition for this task
        try:
            retval = next(sim.check_and_gwait(cond=lambda c:True))
        except StopIteration as e:
            retval = e.value
        self.assertTrue(isinstance(retval, object)) # we get back the object which was created in the check_and_wait function
        sim.get_consumer_metadata(None).cond.pop()  # remove stored condition for this task

        condition = SomeCallableObj()
        condition.cond_value = lambda e: 'condition value was computed in lambda'
        try:
            retval = next(sim.check_and_gwait(cond=condition))
            sim.get_consumer_metadata(None).cond.pop()  # remove stored condition for this task
        except StopIteration as e:
            retval = e.value
        self.assertTrue(retval == 'condition value was computed in lambda')

    def test5_check_and_wait(self):
        ''' Test check_and_wait function. First it should call check and if check does not pass, it should call wait '''
        sim = DSSimulation()
        retval = 'abc'
        # The generator sim.check_and_wait yields in the middle with the value back, which is by default "True"
        coro = sim.check_and_wait(cond=lambda c:False)
        retval = coro.send(None)
        sim.get_consumer_metadata(None).cond.pop()  # remove stored condition for this task
        self.assertTrue(retval == True)
        try:
            coro = sim.check_and_wait(cond=lambda c:True)
            retval = coro.send(None)
            sim.get_consumer_metadata(None).cond.pop()  # remove stored condition for this task
        except StopIteration as e:
            retval = e.value
        self.assertTrue(isinstance(retval, object)) # we get back the object which was created in the check_and_wait function

        condition = SomeCallableObj()
        condition.cond_value = lambda e: 'condition value was computed in lambda'
        try:
            coro = sim.check_and_wait(cond=condition)
            retval = coro.send(None)
            sim.get_consumer_metadata(None).cond.pop()  # remove stored condition for this task
        except StopIteration as e:
            retval = e.value
        self.assertTrue(retval == 'condition value was computed in lambda')

    def test6_gwait_return(self):
        def my_process():
            yield 1
            yield from self.sim.gwait(cond=lambda e:True, val=2)
            return 3
        self.sim = DSSimulation()
        p = my_process()
        retval = self.sim._kick(p)
        # self.assertTrue(retval == 1)  # kick does not return value
        retval = self.sim.send(p, None)
        self.assertTrue(retval == 2)
        retval = self.sim.send(p, None)
        self.assertTrue(retval == 3)

        p = DSProcess(my_process(), sim=self.sim)
        retval = self.sim._kick(p)
        # self.assertTrue(retval == 1)  # kick does not return value
        retval = self.sim.send(p, None)
        self.assertTrue(retval == 2)
        retval = self.sim.send(p, None)
        self.assertTrue(retval == 3)

        p = my_process()
        p = self.sim.schedule(0, p)
        # kick does not return value
        retval = self.sim.send(p, None)
        self.assertTrue(retval == 1)
        retval = self.sim.send(p, None)
        self.assertTrue(retval == 2)
        retval = self.sim.send(p, None)
        self.assertTrue(retval == 3)

        p = DSProcess(my_process(), sim=self.sim)
        p = self.sim.schedule(0, p)
        # kick does not return value
        retval = self.sim.send(p, None)
        self.assertTrue(retval == 1)
        retval = self.sim.send(p, None)
        self.assertTrue(retval == 2)
        retval = self.sim.send(p, None)
        self.assertTrue(retval == 3)

    def test7_wait_return(self):
        class SomeAwaitable:
            def __await__(self):
                yield 1
        async def my_process():
            await SomeAwaitable()
            await self.sim.wait(cond=lambda e:True, val=2)
            return 3
        self.sim = DSSimulation()
        p = my_process()
        retval = self.sim._kick(p)
        # self.assertTrue(retval == 1)  # kick does not return value
        retval = self.sim.send(p, None)
        self.assertTrue(retval == 2)
        retval = self.sim.send(p, None)
        self.assertTrue(retval == 3)

        p = DSProcess(my_process(), sim=self.sim)
        retval = self.sim._kick(p)
        # self.assertTrue(retval == 1)  # kick does not return value
        retval = self.sim.send(p, None)
        self.assertTrue(retval == 2)
        retval = self.sim.send(p, None)
        self.assertTrue(retval == 3)

        p = my_process()
        p = self.sim.schedule(0, p)
        # kick does not return value
        retval = self.sim.send(p, None)
        self.assertTrue(retval == 1)
        retval = self.sim.send(p, None)
        self.assertTrue(retval == 2)
        retval = self.sim.send(p, None)
        self.assertTrue(retval == 3)

        p = DSProcess(my_process(), sim=self.sim)
        p = self.sim.schedule(0, p)
        # kick does not return value
        retval = self.sim.send(p, None)
        self.assertTrue(retval == 1)
        retval = self.sim.send(p, None)
        self.assertTrue(retval == 2)
        retval = self.sim.send(p, None)
        self.assertTrue(retval == 3)


class TestSubscriberContext(unittest.TestCase):

    def __process(self):
        yield 1

    def test0_init_add_remove_producer(self):
        sim = DSSimulation()
        p = DSProcess(self.__process(), sim=sim)
        a, b, c, d, e = DSProducer(), DSProducer(), DSProducer(), DSProducer(), DSProducer()
        cm = DSSubscriberContextManager(p, 'pre', (a, b, c))
        self.assertTrue((len(cm.pre), len(cm.act), len(cm.post)) == (3, 0, 0))
        cm = DSSubscriberContextManager(p, 'act', (a, b, c, d))
        self.assertTrue((len(cm.pre), len(cm.act), len(cm.post)) == (0, 4, 0))
        cm = DSSubscriberContextManager(p, 'post', (a, b, c, d, e))
        self.assertTrue((len(cm.pre), len(cm.act), len(cm.post)) == (0, 0, 5))
        cm = cm + DSSubscriberContextManager(p, 'act', (a, b, c))
        self.assertTrue((len(cm.pre), len(cm.act), len(cm.post)) == (0, 3, 5))
        cm = cm + DSSubscriberContextManager(p, 'act', (d,))
        self.assertTrue((len(cm.pre), len(cm.act), len(cm.post)) == (0, 4, 5))
        cm = cm + DSSubscriberContextManager(p, 'act', (c,))
        self.assertTrue((len(cm.pre), len(cm.act), len(cm.post)) == (0, 4, 5))

    def test1_init_add_remove_future(self):
        sim = DSSimulation()
        p = DSProcess(self.__process(), sim=sim)
        a, b, c, d, e = DSFuture(), DSFuture(), DSFuture(), DSFuture(), DSFuture()
        cm = DSSubscriberContextManager(p, 'pre', (a, b, c))
        self.assertTrue((len(cm.pre), len(cm.act), len(cm.post)) == (3, 0, 0))
        cm = DSSubscriberContextManager(p, 'act', (a, b, c, d))
        self.assertTrue((len(cm.pre), len(cm.act), len(cm.post)) == (0, 4, 0))
        cm = DSSubscriberContextManager(p, 'post', (a, b, c, d, e))
        self.assertTrue((len(cm.pre), len(cm.act), len(cm.post)) == (0, 0, 5))
        cm = cm + DSSubscriberContextManager(p, 'act', (a, b, c))
        self.assertTrue((len(cm.pre), len(cm.act), len(cm.post)) == (0, 3, 5))
        cm = cm + DSSubscriberContextManager(p, 'act', (d,))
        self.assertTrue((len(cm.pre), len(cm.act), len(cm.post)) == (0, 4, 5))
        cm = cm + DSSubscriberContextManager(p, 'act', (c,))
        self.assertTrue((len(cm.pre), len(cm.act), len(cm.post)) == (0, 4, 5))

    def test2_enter_exit(self):
        sim = DSSimulation()
        p = DSProcess(self.__process(), sim=sim)
        a, b, c, d, e = (FutureMock(), FutureMock(), FutureMock(), FutureMock(), FutureMock())
        cm = DSSubscriberContextManager(p, 'pre', (a, c)) + DSSubscriberContextManager(p, 'post', (b,)) + DSSubscriberContextManager(p, 'act', (e,))
        cm.__enter__()
        a.add_subscriber.assert_called_once_with(p, 'pre')
        c.add_subscriber.assert_called_once_with(p, 'pre')
        b.add_subscriber.assert_called_once_with(p, 'post')
        d.add_subscriber.assert_not_called()
        e.add_subscriber.assert_called_once_with(p, 'act')
        _ = a.reset_mock(), b.reset_mock(), c.reset_mock(), d.reset_mock()
        cm.__exit__(None, None, None)
        a.remove_subscriber.assert_called_once_with(p, 'pre')
        c.remove_subscriber.assert_called_once_with(p, 'pre')
        b.remove_subscriber.assert_called_once_with(p, 'post')
        d.remove_subscriber.assert_not_called()
        e.remove_subscriber.assert_called_once_with(p, 'act')

    def test3_sim_functions_producer(self):
        sim = DSSimulation()
        sim.parent_process = DSProcess(self.__process(), sim=sim)
        a, b, c, d = (DSProducer(), DSProducer(), DSProducer(), DSProducer(),)
        cm = sim.observe_pre(a, b, c)
        self.assertTrue(type(cm) == DSSubscriberContextManager)
        self.assertTrue(cm.pre == {a, b, c})
        self.assertTrue((len(cm.act), len(cm.post)) == (0, 0))
        cm = sim.consume(a, c)
        self.assertTrue(type(cm) == DSSubscriberContextManager)
        self.assertTrue(cm.act == {a, c})
        self.assertTrue((len(cm.pre), len(cm.post)) == (0, 0))
        cm = sim.observe_post(d)
        self.assertTrue(type(cm) == DSSubscriberContextManager)
        self.assertTrue(cm.post == {d,})
        self.assertTrue((len(cm.pre), len(cm.act)) == (0, 0))
        cm = sim.observe_post(d) + sim.observe_pre(a) + sim.consume(b, c)
        self.assertTrue(type(cm) == DSSubscriberContextManager)
        self.assertTrue(cm.pre == {a,})
        self.assertTrue(cm.act == {b, c})
        self.assertTrue(cm.post == {d,})

    def test4_sim_functions_future(self):
        sim = DSSimulation()
        sim.parent_process = DSProcess(self.__process(), sim=sim)
        a, b, c, d = (DSFuture(), DSFuture(), DSFuture(), DSFuture(),)
        cm = sim.observe_pre(a, b, c)
        self.assertTrue(type(cm) == DSSubscriberContextManager)
        self.assertTrue(cm.pre == a.get_future_eps() | b.get_future_eps() | c.get_future_eps())
        self.assertTrue((len(cm.act), len(cm.post)) == (0, 0))
        cm = sim.consume(a, c)
        self.assertTrue(type(cm) == DSSubscriberContextManager)
        self.assertTrue(cm.act == a.get_future_eps() | c.get_future_eps())
        self.assertTrue((len(cm.pre), len(cm.post)) == (0, 0))
        cm = sim.observe_post(d)
        self.assertTrue(type(cm) == DSSubscriberContextManager)
        self.assertTrue(cm.post == d.get_future_eps())
        self.assertTrue((len(cm.pre), len(cm.act)) == (0, 0))
        cm = sim.observe_post(d) + sim.observe_pre(a) + sim.consume(b, c)
        self.assertTrue(type(cm) == DSSubscriberContextManager)
        self.assertTrue(cm.pre == a.get_future_eps())
        self.assertTrue(cm.act == b.get_future_eps() | c.get_future_eps())
        self.assertTrue(cm.post == d.get_future_eps())


class TestTimeoutContext(unittest.TestCase):

    def test0_init(self):
        sim = Mock()
        cm = DSInterruptibleContext(None, sim=sim)
        self.assertTrue(cm.time is None)
        self.assertTrue(cm.sim is sim)
        sim.schedule_event.assert_not_called()

        sim = Mock()
        cm = DSInterruptibleContext(0, sim=sim)
        self.assertTrue(cm.time == 0)
        self.assertTrue(cm.sim is sim)
        sim.schedule_event.assert_has_calls([call(0, None),])

        sim = Mock()
        event = DSTimeoutContextError()
        cm = DSInterruptibleContext(0, event, sim=sim)
        self.assertTrue(cm.time == 0)
        self.assertTrue(cm.sim is sim)
        sim.schedule_event.assert_has_calls([call(0, event),])

    def test1_reschedule(self):
        sim = DSSimulation()
        sim.parent_process = 'process'
        cm = DSInterruptibleContext(None, 'hello', sim=sim)
        self.assertTrue(len(sim.time_queue) == 0)
        cm.reschedule(2)
        self.assertTrue(len(sim.time_queue) == 1)
        self.assertTrue(sim.time_queue.get0() == (2, ('process', 'hello')))
        cm.reschedule(1)
        self.assertTrue(len(sim.time_queue) == 1)
        self.assertTrue(sim.time_queue.get0() == (1, ('process', 'hello')))

        sim = DSSimulation()
        sim.parent_process = 'process'
        cm = DSInterruptibleContext(0, 'hi', sim=sim)
        self.assertTrue(len(sim.time_queue) == 1)
        self.assertTrue(sim.time_queue.get0() == (0, ('process', 'hi')))
        cm.reschedule(2)
        self.assertTrue(len(sim.time_queue) == 1)
        self.assertTrue(sim.time_queue.get0() == (2, ('process', 'hi')))
        cm.reschedule(1)
        self.assertTrue(len(sim.time_queue) == 1)
        self.assertTrue(sim.time_queue.get0() == (1, ('process', 'hi')))

        event = 'hi'
        cm = DSInterruptibleContext(3, 'bye', sim=sim)
        self.assertTrue(len(sim.time_queue) == 2)
        self.assertTrue(sim.time_queue.get0() == (1, ('process', 'hi')))
        cm.reschedule(0)
        self.assertTrue(len(sim.time_queue) == 2)
        self.assertTrue(sim.time_queue.get0() == (0, ('process', 'bye')))
        cm.reschedule(3)
        self.assertTrue(len(sim.time_queue) == 2)
        self.assertTrue(sim.time_queue.pop() == (1, ('process', 'hi')))
        self.assertTrue(sim.time_queue.pop() == (3, ('process', 'bye')))

    def test2_sim_timeout_positive(self):
        sim = DSSimulation()
        sim.parent_process = 'process'
        with sim.interruptible(0) as cm:
            self.assertTrue(len(sim.time_queue) == 1)
            queued = sim.time_queue.get0()
            self.assertTrue(queued[0] == 0)
            self.assertTrue(queued[1][0] == 'process')
            self.assertTrue(isinstance(queued[1][1], DSTimeoutContextError))
            cm.reschedule(10)
            self.assertTrue(len(sim.time_queue) == 1)
            queued = sim.time_queue.get0()
            self.assertTrue(queued[0] == 10)
            self.assertTrue(queued[1][0] == 'process')
            self.assertTrue(isinstance(queued[1][1], DSTimeoutContextError))
        self.assertTrue(len(sim.time_queue) == 0)

    def test2_sim_timeout_negative(self):
        def process(sim, timeout):
            with sim.interruptible(timeout) as cm:
                self.assertFalse(cm.interrupted())
                yield from sim.gwait(10)
                self.assertTrue(timeout > 10)
            self.assertTrue(cm.interrupted() == (timeout < 10))

        sim = DSSimulation()
        p = process(sim, 20)
        sim.schedule(0, p)
        sim.run()

        sim = DSSimulation()
        p = process(sim, 1)
        sim.schedule(0, p)
        sim.run()




class TestSim(unittest.TestCase):
    ''' Test the time queue class behavior '''

    def __my_time_process(self):
        self.__time_process_event('kick-on')
        while True:
            event = yield
            if isinstance(event, DSAbortException):
                self.__time_process_event(self.sim.time, {'abort': True, 'info': event.info})
                break
            else:
                self.__time_process_event(self.sim.time, event)

    def __my_wait_process(self):
        try:
            event = yield from self.sim.gwait(2)
            self.__time_process_event(self.sim.time, None)
            event = yield from self.sim.gwait(cond=lambda e: 'data' in e)
            self.__time_process_event(self.sim.time, **event)
            event = yield from self.sim.gwait(cond=lambda e: True)
            self.__time_process_event(self.sim.time, **event)
        except Exception as e:
            return e

    def __my_handler(self):
        return True

    @DSSchedulable
    def __my_schedulable_handler(self):
        return True

    def setUp(self):
        self.__time_process_event = Mock()

    def test0_init_reset(self):
        sim = DSSimulation()
        self.assertEqual(sim.parent_process, None)
        self.assertEqual(len(sim.time_queue), 0)
        self.assertEqual(sim.time, 0)
        sim.schedule(0.5, self.__my_wait_process())
        sim.schedule(1.5, self.__my_wait_process())
        self.assertEqual(len(sim.time_queue), 2)
        sim.run(1)
        self.assertEqual(sim.time, 1)
        self.assertEqual(len(sim.time_queue), 1)
        sim.restart(0.9)
        self.assertEqual(sim.parent_process, None)
        self.assertEqual(len(sim.time_queue), 0)
        self.assertEqual(sim.time, 0.9)

    def test1_scheduling_events(self):
        ''' Assert working with time queue when pushing events '''
        sim = DSSimulation()
        sim.time_queue.add_element = Mock()
        sim.parent_process = 123456
        event_obj = {'producer': None, 'data': 1}
        sim.schedule_event(10, event_obj)
        sim.time_queue.add_element.assert_called_once_with(10, (123456, event_obj))
        sim.time_queue.add_element.reset_mock()
        sim.schedule_event(0, event_obj)
        sim.time_queue.add_element.assert_called_once_with(0, (123456, event_obj))
        sim.time_queue.add_element.reset_mock()
        with self.assertRaises(ValueError):
            sim.schedule_event(-0.5, event_obj)

    def test2_deleting_events(self):
        ''' Assert deleting from time queue when deleting events '''
        sim = DSSimulation()
        sim.time_queue.delete = Mock()
        condition = lambda x: 'A' * x
        sim.delete(condition)
        sim.time_queue.delete.assert_called_once_with(condition)
        sim.time_queue.delete.reset_mock()

    def test3_scheduling(self):
        ''' Assert the delay of scheduled process '''
        self.sim = DSSimulation()
        my_process = self.__my_time_process()
        # schedule a process
        with self.assertRaises(ValueError):
            # scheduling with negative time delta
            parent_process = self.sim.schedule(-0.5, my_process)
        parent_process = self.sim.schedule(2, my_process)
        self.assertEqual(len(self.sim.time_queue), 1)

    def test4_scheduling(self):
        self.sim = DSSimulation()
        producer = SomeObj()
        producer.send = Mock()
        event_obj = SomeObj()
        retval = self.sim.send_object(producer, event_obj)
        producer.send.assert_called_once_with(event_obj)

    def test5_scheduling(self):
        ''' Assert working with time queue when pushing events '''
        self.sim = DSSimulation()
        my_process = self.__my_time_process()
        # schedule a process
        with self.assertRaises(ValueError):
            # negative time
            self.sim.schedule(-0.5, my_process)

        parent_process = self.sim.schedule(0, my_process)
        self.assertNotEqual(parent_process, my_process)
        self.__time_process_event.assert_not_called()
        self.sim.run(0.5)
        self.__time_process_event.assert_called_once_with('kick-on')
        self.__time_process_event.reset_mock()
        # schedule an event
        with self.assertRaises(ValueError):
            # negative time
            self.sim.schedule_event(-0.5, {'producer': parent_process, 'data': 1})

        self.assertEqual(self.sim.time, 0.5)
        event_obj = {'producer': parent_process, 'data': 1}
        self.sim.schedule_event(2, event_obj, my_process)
        time, (process, event) = self.sim.time_queue.pop()
        self.assertEqual((time, process), (2.5, my_process))
        self.assertEqual(event, event_obj)
        self.sim.run(2.5)

        process = SomeObj()
        process.send = Mock()
        retval = self.sim.abort(parent_process, testing=-1)
        self.__time_process_event.assert_called_once_with(2.5, {'abort': True, 'info': {'testing': -1}})
        self.__time_process_event.reset_mock()

    def test6_schedulable_fcn(self):
        self.sim = DSSimulation()
        # The following has to pass without raising an error
        self.sim._kick(self.__my_schedulable_handler())

    def test7_run_process(self):
        ''' Assert event loop behavior for process '''
        self.sim = DSSimulation()
        self.sim.parent_process = Mock()
        my_process = self.__my_time_process()
        parent_process = self.sim.schedule(0, my_process)

        self.sim.run(0.5) # kick on the process
        self.sim.schedule_event(1, 3, my_process)
        self.sim.schedule_event(2, 2, my_process)
        self.sim.schedule_event(3, 1, my_process)
        retval = self.sim.run(0.5)
        self.__time_process_event.assert_called_once_with('kick-on')
        self.assertEqual(retval, (0.5, 1))
        self.__time_process_event.reset_mock()

        self.sim.num_events = 0
        retval = self.sim.run()
        self.assertEqual(retval, (3.5, 3))
        calls = [call(1.5, 3), call(2.5, 2), call(3.5, 1),]
        self.__time_process_event.assert_has_calls(calls)
        retval = len(self.sim.time_queue)
        self.assertEqual(retval, 0)
        self.__time_process_event.reset_mock()

        self.sim.restart()
        self.sim.schedule_event(1, 3, my_process)
        self.sim.schedule_event(2, 2, my_process)
        self.sim.schedule_event(3, 1, my_process)
        retval = self.sim.run(2.5)
        self.assertEqual(retval, (2, 2))
        calls = [call(1, 3), call(2, 2),]
        self.__time_process_event.assert_has_calls(calls)
        num_events = len(self.sim.time_queue)
        self.assertEqual(num_events, 1)
        self.__time_process_event.reset_mock()


    def test8_run_producer(self):
        self.sim = DSSimulation()
        producer = SomeObj()
        producer.send = Mock()
        self.sim.schedule_event(1, 3, producer)
        self.sim.schedule_event(2, 2, producer)
        self.sim.schedule_event(3, 1, producer)
        retval = self.sim.run()
        self.assertEqual(retval, (3, 3))
        calls = [call(3), call(2), call(1),]
        producer.send.assert_has_calls(calls)
        num_events = len(self.sim.time_queue)
        self.assertEqual(num_events, 0)
        producer.send.reset_mock()

        self.sim.restart()
        self.sim.schedule_event(1, 3, producer)
        self.sim.schedule_event(2, 2, producer)
        self.sim.schedule_event(3, 1, producer)
        retval = self.sim.run(2.5)
        self.assertEqual(retval, (2, 2))
        calls = [call(3), call(2),]
        producer.send.assert_has_calls(calls)
        num_events = len(self.sim.time_queue)
        self.assertEqual(num_events, 1)


    def test9_waiting(self):
        self.sim = DSSimulation()
        # the following process will create events for the time queue process
        process = self.__my_wait_process()
        # those events are required to contain a producer
        producer = EventForwarder(self, process)
        self.sim.parent_process = process
        self.sim._kick(process)
        self.sim.schedule_event(1, {'producer': producer, 'data': 1}, process)
        self.sim.schedule_event(2, {'producer': producer, 'data': 2}, process)
        self.sim.schedule_event(3, {'producer': producer, 'data': 3}, process)
        retval = self.sim.run(5)
        self.assertEqual(retval, (3, 4))  # 3 events scheduled here + 1 event = the process finished itself
        # first event is dropped, because though it was taken by the time_process, the process condition was
        # to wait till timeout
        calls = [
            call(2, None),  # timeout logged
            call(2, producer=producer, data=2),  # real event logged
            call(3, producer=producer, data=3),  # real event logged after time
        ]
        self.__time_process_event.assert_has_calls(calls)

    def testA_return_cleanup(self):
        def my_process2(sim, alwaystrue=True):
            if alwaystrue:
                return 100
            yield from sim.gwait(1)
        sim = DSSimulation()
        process = DSProcess(my_process2(sim), sim=sim)
        sim.parent_process = process
        sim._kick(process)
        sim.schedule_event(1, {'data': 1}, process)
        sim.schedule_event(2, {'data': 2}, process)
        sim.schedule_event(3, {'data': 3}, process)
        retval = sim.run()
        self.assertEqual(retval, (1, 2))  # 2 events: first processed created a IterError, the second event = end of process

    def testB_timeout_cleanup(self):
        def my_process(sim):
            retval = yield from sim.gwait(1)
            yield  # wait here with no interaction to the time_queue

        sim = DSSimulation()
        process = DSProcess(my_process(sim), sim=sim)
        sim.parent_process = process
        sim.schedule_event(4, 'some_event', process=process)
        retval = process.send(None)  # go to the waiting
        self.assertTrue(len(sim.time_queue) == 2)
        retval = process.send('value')  # sending some event makes that the waiting timeout will be removed
        # ensure that the some_event scheduled in the future for the process is still in queue
        self.assertTrue(len(sim.time_queue) == 1)

    def testC_abort(self):
        self.sim = DSSimulation()
        # the following process will create events for the time queue process
        process = self.__my_wait_process()
        # those events are required to contain a producer
        producer = EventForwarder(self, process)
        self.sim.parent_process = process
        self.sim._kick(process)
        self.sim.schedule_event(1, {'producer': producer, 'data': 1})
        num_events = self.sim.run(2.5)
        # first event is dropped, because though it was taken by the time_process, the process condition was
        # to wait till timeout
        calls = [
            call(2, None),  # timeout logged
        ]
        self.__time_process_event.assert_has_calls(calls)
        self.assertEqual(len(self.sim.time_queue), 0)  # there is no event left from process
        self.sim.schedule_event(float('inf'), {'producer': producer, 'data': 2})
        num_events = self.sim.run(2.5)
        self.__time_process_event.assert_has_calls([])
        self.assertEqual(len(self.sim.time_queue), 1)  # there are still timeout event left from process
        self.sim.abort(process, testing=-1),  # abort after time
        self.assertEqual(len(self.sim.time_queue), 0)  # test if the timeout event was removed after abort

