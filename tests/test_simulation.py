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
from dssim.simulation import DSSimulation, DSAbortException, DSSchedulable, DSProcess, DSSubscriberContextManager

class SomeObj:
    pass

class SomeCallableObj:
    def __call__(self, event):
        return True

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
        process = DSProcess(self.__fcn(), sim=DSSimulation())
        try:
            next(process)
        except StopIteration as e:
            retval = e.value
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
        process = DSProcess(self.__generator(), sim=DSSimulation())
        retval = next(process)
        self.assertEqual(retval, 'First return')
        retval = next(process)
        self.assertEqual(retval, 'Second return')
        try:
            next(process)
        except StopIteration as e:
            retval = e.value
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
        process = DSProcess(self.__generator(), sim=DSSimulation())
        retval = next(process)
        self.assertEqual(retval, 'First return')
        retval = process.send('anything0')
        self.assertEqual(retval, 'Second return')
        try:
            retval = process.send('anything1')
        except StopIteration as e:
            retval2 = e.value
        self.assertEqual(retval2, 'Success')
        self.assertEqual(process.value, 'Success')

        try:
            retval = process.send('anything2')
        except StopIteration as e:
            retval2 = e.value
        self.assertEqual(retval2, None)
        self.assertEqual(process.value, None)

    def test6_send_to_generator(self):
        process = self.__loopback_generator()
        retval = next(process)
        retval = process.send('from_test0')
        self.assertEqual(retval, 'from_test0')
        retval = process.send(DSAbortException(producer='test'))
        self.assertTrue(isinstance(retval, DSAbortException))

    def test7_send_to_generator_as_process(self):
        process = DSProcess(self.__loopback_generator(), sim=DSSimulation())
        retval = next(process)
        retval = process.send('from_test0')
        self.assertEqual(retval, 'from_test0')
        retval = process.abort('some_data')
        self.assertTrue(isinstance(retval, DSAbortException))
        self.assertTrue(isinstance(process.value, DSAbortException))

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
        self.assertEqual(process.value, 'Success')
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
        self.assertTrue(len(sim._process_metadata) == 0)
        p = DSProcess(self.__my_process(), sim=sim)
        p.meta = 'My meta'
        meta = sim.get_process_metadata(p)
        self.assertEqual(meta, p.meta)
        self.assertTrue(len(sim._process_metadata) == 0)

        p = self.__my_process()
        self.assertTrue(len(sim._process_metadata) == 0)
        meta = sim.get_process_metadata(p)
        self.assertIsNotNone(meta)
        self.assertTrue(len(sim._process_metadata) == 1)  # write the metadata of the generator into the simulation registry
        meta = sim.get_process_metadata(p)
        self.assertIsNotNone(meta)
        self.assertTrue(len(sim._process_metadata) == 1)  # the next retrieve does not increase the registry

    def test1_check_storing_cond_in_metadata(self):
        ''' By calling wait, the metadata.cond should be stored '''
        def my_process(value):
            if True:
                return 100
            yield 101

        sim = DSSimulation()
        sim._wait_for_event = my_process
        process = DSProcess(self.__my_process(), sim=sim)
        sim.parent_process = process
        try:
            retval = next(sim.wait(cond='condition'))
        except StopIteration as e:
            retval = e.value
        self.assertTrue(retval == 100)
        self.assertTrue(process.meta.cond == 'condition')

        condition = SomeObj()
        condition.cond_value = lambda e: 'condition value was computed in lambda'
        condition.cond_cleanup = Mock()
        try:
            retval = next(sim.wait(cond=condition))
        except StopIteration as e:
            retval = e.value
        self.assertTrue(process.meta.cond == condition)
        self.assertTrue(retval == 'condition value was computed in lambda')
        condition.cond_cleanup.assert_called_once()
    
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
            retval = sim._check_cond(cond, event)
            self.assertEqual(retval, expected_result)

    def test3_check_condition(self):
        ''' The check_condition should retrieve cond from the metadata and then call _check_cond '''
        sim = DSSimulation()
        p = DSProcess(self.__my_process(), sim=sim)
        p.meta = SomeObj()
        p.meta.cond = Mock(return_value='abc')
        retval = sim.check_condition(p, 'test')
        p.meta.cond.assert_called_once()
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

    def test5_check_and_wait(self):
        ''' Test check_and_wait function. First it should call check and if check does not pass, it should call wait '''
        sim = DSSimulation()
        retval = 'abc'
        # The generator sim.check_and_wait yields in the middle with the value back, which is by default "True"
        retval = next(sim.check_and_wait(cond=lambda c:False))
        self.assertTrue(retval == True)
        try:
            retval = next(sim.check_and_wait(cond=lambda c:True))
        except StopIteration as e:
            retval = e.value
        self.assertTrue(isinstance(retval, object)) # we get back the object which was created in the check_and_wait function

        condition = SomeCallableObj()
        condition.cond_value = lambda e: 'condition value was computed in lambda'
        condition.cond_cleanup = Mock()
        try:
            retval = next(sim.check_and_wait(cond=condition))
        except StopIteration as e:
            retval = e.value
        self.assertTrue(retval == 'condition value was computed in lambda')
        condition.cond_cleanup.assert_called_once()

    def test6_wait_return(self):
        def my_process():
            yield 1
            yield from self.sim.wait(cond=lambda e:True, val=2)
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

    def test0_init_add_remove(self):
        sim = DSSimulation()
        p = DSProcess(self.__process(), sim=sim)
        cm = DSSubscriberContextManager(p, 'pre', ('a', 'b', 'c'))
        self.assertTrue((len(cm.pre), len(cm.act), len(cm.post)) == (3, 0, 0))
        cm = DSSubscriberContextManager(p, 'act', ('a', 'b', 'c', 'd'))
        self.assertTrue((len(cm.pre), len(cm.act), len(cm.post)) == (0, 4, 0))
        cm = DSSubscriberContextManager(p, 'post', ('a', 'b', 'c', 'd', 'e'))
        self.assertTrue((len(cm.pre), len(cm.act), len(cm.post)) == (0, 0, 5))
        cm = cm + DSSubscriberContextManager(p, 'act', ('a', 'b', 'c'))
        self.assertTrue((len(cm.pre), len(cm.act), len(cm.post)) == (0, 3, 5))
        cm = cm + DSSubscriberContextManager(p, 'act', ('d'))
        self.assertTrue((len(cm.pre), len(cm.act), len(cm.post)) == (0, 4, 5))
        cm = cm + DSSubscriberContextManager(p, 'act', ('c'))
        self.assertTrue((len(cm.pre), len(cm.act), len(cm.post)) == (0, 4, 5))

    def test1_enter_exit(self):
        sim = DSSimulation()
        p = DSProcess(self.__process(), sim=sim)
        mock_a, mock_b, mock_c, mock_d, mock_e = (Mock(), Mock(), Mock(), Mock(), Mock())
        cm = DSSubscriberContextManager(p, 'pre', (mock_a, mock_c)) + DSSubscriberContextManager(p, 'post', (mock_b,)) + DSSubscriberContextManager(p, 'act', (mock_e,))
        cm.__enter__()
        mock_a.add_subscriber.assert_called_once_with(p, 'pre')
        mock_c.add_subscriber.assert_called_once_with(p, 'pre')
        mock_b.add_subscriber.assert_called_once_with(p, 'post')
        mock_d.add_subscriber.assert_not_called()
        mock_e.add_subscriber.assert_called_once_with(p, 'act')
        _ = mock_a.reset_mock(), mock_b.reset_mock(), mock_c.reset_mock(), mock_d.reset_mock()
        cm.__exit__(None, None, None)
        mock_a.remove_subscriber.assert_called_once_with(p, 'pre')
        mock_c.remove_subscriber.assert_called_once_with(p, 'pre')
        mock_b.remove_subscriber.assert_called_once_with(p, 'post')
        mock_d.remove_subscriber.assert_not_called()
        mock_e.remove_subscriber.assert_called_once_with(p, 'act')

    def test2_proxy_function(self):
        sim = DSSimulation()
        sim.parent_process = DSProcess(self.__process(), sim=sim)
        cm = sim.observe_pre('a', 'b', 'c')
        self.assertTrue(type(cm) == DSSubscriberContextManager)
        self.assertTrue(cm.pre == {'a', 'b', 'c'})
        self.assertTrue((len(cm.act), len(cm.post)) == (0, 0))
        cm = sim.consume('a', 'c')
        self.assertTrue(type(cm) == DSSubscriberContextManager)
        self.assertTrue(cm.act == {'a', 'c'})
        self.assertTrue((len(cm.pre), len(cm.post)) == (0, 0))
        cm = sim.observe_post('d')
        self.assertTrue(type(cm) == DSSubscriberContextManager)
        self.assertTrue(cm.post == {'d',})
        self.assertTrue((len(cm.pre), len(cm.act)) == (0, 0))
        cm = sim.observe_post('d') + sim.observe_pre('a') + sim.consume('b', 'c')
        self.assertTrue(type(cm) == DSSubscriberContextManager)
        self.assertTrue(cm.pre == {'a',})
        self.assertTrue(cm.act == {'b', 'c'})
        self.assertTrue(cm.post == {'d',})


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
            event = yield from self.sim.wait(2)
            self.__time_process_event(self.sim.time, None)
            event = yield from self.sim.wait(cond=lambda e: 'data' in e)
            self.__time_process_event(self.sim.time, **event)
            event = yield from self.sim.wait(cond=lambda e: True)
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

    def test2_scheduling_events(self):
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

    def test3_deleting_events(self):
        ''' Assert deleting from time queue when deleting events '''
        sim = DSSimulation()
        sim.time_queue.delete = Mock()
        condition = lambda x: 'A' * x
        sim.delete(condition)
        sim.time_queue.delete.assert_called_once_with(condition)
        sim.time_queue.delete.reset_mock()

    def test4_scheduling(self):
        ''' Assert the delay of scheduled process '''
        self.sim = DSSimulation()
        my_process = self.__my_time_process()
        # schedule a process
        with self.assertRaises(ValueError):
            # scheduling with negative time delta
            parent_process = self.sim.schedule(-0.5, my_process)
        parent_process = self.sim.schedule(2, my_process)
        self.assertEqual(len(self.sim.time_queue), 1)

    def test5_scheduling(self):
        self.sim = DSSimulation()
        producer = SomeObj()
        producer.send = Mock()
        event_obj = SomeObj()
        retval = self.sim.send_object(producer, event_obj)
        producer.send.assert_called_once_with(event_obj)

    def test6_scheduling(self):
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

    def test7_schedulable_fcn(self):
        self.sim = DSSimulation()
        # The following has to pass without raising an error
        self.sim._kick(self.__my_schedulable_handler())

    def test8_run_process(self):
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


    def test9_run_producer(self):
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


    def test10_waiting(self):
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
        self.assertEqual(retval, (3, 4))  # 3 events scheduled here + 1 timeout scheduled by the __my_wait_process
        # first event is dropped, because though it was taken by the time_process, the process condition was
        # to wait till timeout
        calls = [
            call(2, None),  # timeout logged
            call(2, producer=producer, data=2),  # real event logged
            call(3, producer=producer, data=3),  # real event logged after time
        ]
        self.__time_process_event.assert_has_calls(calls)

    def test11_timeout_cleanup(self):
        def my_process(sim):
            retval = yield from sim.wait(1)
            yield  # wait here with no interaction to the time_queue

        sim = DSSimulation()
        process = DSProcess(my_process(sim), sim=sim)
        sim.parent_process = process
        sim.schedule_event(4, 'some_event', process=process)
        retval = process.send(None)  # go to the waiting
        self.assertTrue(len(sim.time_queue) == 2)
        retval = process.send('value')  # sending some event makesthat the waiting timeout will be removed
        # ensure that the some_event scheduled in the future for the process is still in queue
        self.assertTrue(len(sim.time_queue) == 1)

    def test12_abort(self):
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
        self.assertEqual(len(self.sim.time_queue), 0)  # test is the timeout event was removed after abort
