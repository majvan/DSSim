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
from dssim.simulation import DSSimulation, DSAbortException, DSSchedulable, DSProcess, sim

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

    def signal(self, **data):
        self.testunit.sim.signal(self.receiving_process, **data)

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
        process = DSProcess(self.__fcn())
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
        process = DSProcess(self.__generator())
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
        process = DSProcess(self.__generator())
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
        process = DSProcess(self.__loopback_generator())
        retval = next(process)
        retval = process.send('from_test0')
        self.assertEqual(retval, 'from_test0')
        retval = process.abort('some_data')
        self.assertTrue(isinstance(retval, DSAbortException))
        self.assertTrue(isinstance(process.value, DSAbortException))

    def test8_joining_process(self):
        process = DSProcess(self.__generator())
        process.join = MagicMock()
        process.join.return_value = iter(['Join called',])
        process_waiting = DSProcess(self.__waiting_for_join(process))
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
        self.sim.signal(self.process2, data='Signal from first process')
        yield 'After signalling first'
        return 'Done first'

    def __second_cyclic(self):
        yield 'Kick-on second'
        self.sim.signal(self.process1, data='Signal from second process')
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
            self.sim.signal(process, data='My data')
            # we should not get here, exception is expected
            self.assertTrue(1 == 2)
        except ZeroDivisionError as exc:
            self.assertTrue('generator already executing' not in str(exc))

    def test1_exception_usercode_generators(self):
        self.process1 = self.__first_cyclic()
        self.process2 = self.__second_cyclic()
        sim._kick(self.process1)
        sim._kick(self.process2)
        try:
            self.sim.signal(self.process1, data='My data')
            # we should not get here, exception is expected
            self.assertTrue(1 == 2)
        except ValueError as exc:
            self.assertTrue('generator already executing' in str(exc))

    def test2_exception_usercode_process(self):
        self.process1 = DSProcess(self.__first_cyclic(), name="First cyclic", sim=self.sim)
        self.process2 = DSProcess(self.__second_cyclic(), name="Second cyclic", sim=self.sim)
        sim._kick(self.process1)
        sim._kick(self.process2)
        try:
            self.sim.signal(self.process1, data='My data')
            # we should not get here, exception is expected
            self.assertTrue(1 == 2)
        except ValueError as exc:
            self.assertTrue('generator already executing' in str(exc))

class TestConditionChecking(unittest.TestCase):
    ''' Test the processing of the events by the simulation '''
    def __my_process(self):
        while True:
            yield 1

    def test1_process_metadata(self):
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

    def test2_check_storing_cond_in_metadata(self):
        ''' By calling wait, the metadata.cond should be stored '''
        def my_process(event):
            if True:
                return 100
            yield 101

        sim = DSSimulation()
        sim._wait_for_event = my_process
        process = DSProcess(self.__my_process())
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

    def test3_check_cond(self):
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

    def test4_check_condition(self):
        ''' The check_condition should retrieve cond from the metadata and then call _check_cond '''
        sim = DSSimulation()
        p = DSProcess(self.__my_process(), sim=sim)
        p.meta = SomeObj()
        p.meta.cond = Mock(return_value='abc')
        retval = sim.check_condition(p, 'test')
        p.meta.cond.assert_called_once()
        self.assertEqual(retval, True)
    
    def test5_early_check(self):
        ''' Test if signal calls first check_condition and then signal_object '''
        sim = DSSimulation()
        sim.check_condition = Mock(return_value=False)  # it will not allow to accept the event
        sim.signal_object = Mock()
        # sim.check_condition.side_effect = lambda *a, **kw: call_order.append(call(*a, **kw))
        # sim.signal_object.side_effect = lambda *a, **kw: call_order.append(call(*a, **kw))
        sim.signal('process1', obj=None)
        sim.check_condition.assert_called_once()
        sim.signal_object.assert_not_called()

        call_order = []
        sim=DSSimulation()
        def add_to_call_order(fcn_name, *args, **kwargs):
            call_order.append(call(fcn_name, *args, **kwargs))
            return True
        sim.check_condition = Mock(side_effect=lambda *a, **kw: add_to_call_order('check_condition', *a, **kw))  # it will allow to accept the event
        sim.signal_object = Mock(side_effect=lambda *a, **kw: add_to_call_order('signal_object', *a, **kw))
        # sim.check_condition.side_effect = 
        # sim.signal_object.side_effect = lambda *a, **kw: call_order.append(call(*a, **kw))
        sim.signal('process2', obj=None)
        sim.check_condition.assert_called_once()
        sim.signal_object.assert_called_once()
        self.assertEqual(call_order, [call('check_condition', 'process2', {'obj': None}), call('signal_object', 'process2', {'obj': None})])

    def test6_check_and_wait(self):
        ''' Test check_and_wait function. First it should call check and if check does not pass, it should call wait '''
        def always_true(event):
            return True

        sim = DSSimulation()
        retval = 'abc'
        retval = next(sim.check_and_wait(cond=lambda c:False))
        self.assertIsNone(retval)
        try:
            retval = next(sim.check_and_wait(cond=lambda c:True))
        except StopIteration as e:
            retval = e.value
        self.assertIsNotNone(retval)

        condition = SomeCallableObj()
        condition.cond_value = lambda e: 'condition value was computed in lambda'
        condition.cond_cleanup = Mock()
        try:
            retval = next(sim.check_and_wait(cond=condition))
        except StopIteration as e:
            retval = e.value
        self.assertTrue(retval == 'condition value was computed in lambda')
        condition.cond_cleanup.assert_called_once()


class TestSim(unittest.TestCase):
    ''' Test the time queue class behavior '''

    def __my_time_process(self):
        self.__time_process_event('kick-on')
        while True:
            event = yield
            if isinstance(event, DSAbortException):
                self.__time_process_event(self.sim.time_queue.time, abort=True, **event.info)
                break
            else:
                # note: we cannot use self.sim.time because we are not running simulation
                # so self.sim.time is always 0
                self.__time_process_event(self.sim.time_queue.time, **event)

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
        self.assertIsNotNone(sim.time_process)
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
        self.assertIsNotNone(sim.time_process)
        self.assertEqual(sim.parent_process, None)
        self.assertEqual(len(sim.time_queue), 0)
        self.assertEqual(sim.time, 0.9)

    def test1_simple_event(self):
        ''' Assert kicking and pushing events '''
        self.sim = DSSimulation()
        self.assertIsNotNone(sim.time_process)
        self.sim.time_process = self.__my_time_process()
        self.sim._kick(self.sim.time_process)  # kick on the time process
        self.__time_process_event.assert_called_once_with('kick-on')
        self.__time_process_event.reset_mock()
        self.sim.signal(self.sim.time_process, data=1)
        self.__time_process_event.assert_called_once_with(0, data=1)
        self.__time_process_event.reset_mock()

    def test2_time_process(self):
        ''' Assert correct time process and pushing events to time process '''
        sim = DSSimulation()
        self.assertIsNotNone(sim.time_process)
        p = SomeObj()
        p.signal = Mock()
        sim.signal(sim.time_process, producer=p, data=1)
        p.signal.assert_called_once_with(producer=p, data=1)
        p.signal.reset_mock()

    def test3_scheduling_events(self):
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

    def test4_deleting_events(self):
        ''' Assert deleting from time queue when deleting events '''
        sim = DSSimulation()
        sim.time_queue.delete = Mock()
        condition = lambda x: 'A' * x
        sim.delete(condition)
        sim.time_queue.delete.assert_called_once_with(condition)
        sim.time_queue.delete.reset_mock()

    def test5_scheduling(self):
        ''' Assert working with time queue when pushing events '''
        self.sim = DSSimulation()
        my_process = self.__my_time_process()
        # schedule a process
        with self.assertRaises(ValueError):
            # negative time
            self.sim.schedule(-0.5, my_process)
        with self.assertRaises(ValueError):
            # missing producer
            self.sim.schedule(1, self.__my_handler())

        parent_process = self.sim.schedule(0, my_process)
        self.assertNotEqual(parent_process, my_process)
        self.__time_process_event.assert_not_called()
        self.sim.run(0.5)
        self.__time_process_event.called_once_with('kick-on')
        self.__time_process_event.reset_mock()
        # schedule an event
        with self.assertRaises(ValueError):
            # negative time
            self.sim.schedule_event(-0.5, {'producer': parent_process, 'data': 1})
        with self.assertRaises(ValueError):
            # missing producer
            self.sim.schedule_event(1, {'data': 1}, self.sim.time_process)

        self.sim.schedule_event(2, {'producer': parent_process, 'data': 1}, self.sim.time_process)
        time, (process, event_obj) = self.sim.time_queue.pop()
        self.assertEqual((time, process), (2, self.sim.time_process))
        self.assertEqual(event_obj, {'producer': parent_process, 'data': 1})
        #self.sim.run(2.5)
        retval = self.sim.signal_object(event_obj['producer'], event_obj)
        self.__time_process_event.assert_called_once_with(2, producer=event_obj['producer'], data=1)
        self.__time_process_event.reset_mock()

        retval = self.sim.abort(parent_process, testing=-1)
        self.__time_process_event.assert_called_once_with(2, abort=True, testing=-1)
        self.__time_process_event.reset_mock()

    def test6_scheduling(self):
        ''' Assert the delay of scheduled process '''
        self.sim = DSSimulation()
        my_process = self.__my_time_process()
        # schedule a process
        with self.assertRaises(ValueError):
            # scheduling with negative time delta
            parent_process = self.sim.schedule(-0.5, my_process)
        parent_process = self.sim.schedule(2, my_process)
        self.assertEqual(len(self.sim.time_queue), 1)

    def test7_schedulable_fcn(self):
        self.sim = DSSimulation()
        # The following has to pass without raising an error
        self.sim._kick(self.__my_schedulable_handler())

    def test8_run_infinite_process(self):
        ''' Assert event loop behavior '''
        self.sim = DSSimulation()
        producer = SomeObj()
        producer.signal = Mock()
        self.sim.parent_process = Mock()
        self.sim.schedule_event(1, {'producer': producer, 'data': 1}, self.sim.time_process)
        self.sim.schedule_event(2, {'producer': producer, 'data': 2}, self.sim.time_process)
        self.sim.schedule_event(3, {'producer': producer, 'data': 3}, self.sim.time_process)
        num_events = self.sim.run()
        self.assertEqual(num_events, 3)
        calls = [
            call(producer=producer, data=1),
            call(producer=producer, data=2),
            call(producer=producer, data=3),]
        producer.signal.assert_has_calls(calls)
        producer.signal.reset_mock()
        num_events = len(self.sim.time_queue)
        self.assertEqual(num_events, 0)

    def test9_run_finite_process(self):
        self.sim = DSSimulation()
        producer = SomeObj()
        producer.signal = Mock()
        self.sim.schedule_event(1, {'producer': producer, 'data': 1}, self.sim.time_process)
        self.sim.schedule_event(2, {'producer': producer, 'data': 2}, self.sim.time_process)
        self.sim.schedule_event(3, {'producer': producer, 'data': 3}, self.sim.time_process)
        num_events = self.sim.run(2.5)
        self.assertEqual(num_events, 2)
        calls = [
            call(producer=producer, data=1),
            call(producer=producer, data=2),]
        producer.signal.assert_has_calls(calls)
        producer.signal.reset_mock()
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
        self.sim.schedule_event(1, {'producer': producer, 'data': 1}, self.sim.time_process)
        self.sim.schedule_event(2, {'producer': producer, 'data': 2}, self.sim.time_process)
        self.sim.schedule_event(3, {'producer': producer, 'data': 3}, self.sim.time_process)
        num_events = self.sim.run(5)
        self.assertEqual(num_events, 4)
        # first event is dropped, because though it was taken by the time_process, the process condition was
        # to wait till timeout
        calls = [
            call(2, None),  # timeout logged
            call(2, producer=producer, data=2),  # real event logged
            call(3, producer=producer, data=3),  # real event logged after time
        ]
        self.__time_process_event.assert_has_calls(calls)

    def test11_abort(self):
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
        self.assertEqual(len(self.sim.time_queue), 1)  # there are still timeout event left from process
        self.sim.abort(process, testing=-1),  # abort after time
        self.assertEqual(len(self.sim.time_queue), 0)  # test is the timeout event was removed after abort
