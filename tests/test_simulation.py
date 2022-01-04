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
from unittest.mock import Mock, call
from dssim.simulation import DSSimulation, DSAbortException, DSSchedulable, sim

class SomeObj:
    pass

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

    @DSSchedulable
    def __process(self):
        yield 'First return'
        yield 'Second return'
        return 'Success'

    @DSSchedulable
    def __loopback_process(self):
        data = yield
        while True:
            data = yield data

    def test0_fcn(self):
        process = self.__fcn()
        try:
            next(process)
        except StopIteration as e:
            retval = e.value
        self.assertEqual(retval, 'Success')
        self.assertEqual(process.value, 'Success')

    def test1_generator(self):
        process = self.__process()
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

    def test2_generator(self):
        process = self.__process()
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

    def test3_generator(self):
        process = self.__loopback_process()
        retval = next(process)
        retval = process.send('from_test0')
        self.assertEqual(retval, 'from_test0')
        retval = process.abort('some_data')
        self.assertTrue(isinstance(retval, DSAbortException))
        self.assertTrue(isinstance(process.value, DSAbortException))

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
        self.assertEqual(sim.time, 0.5)
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
        sim.time_process = self.__my_time_process()
        sim._kick(sim.time_process)  # kick on the time process
        self.__time_process_event.assert_called_once_with('kick-on')
        self.__time_process_event.reset_mock()
        sim.signal(sim.time_process, data=1)
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
        event_obj = {'producer': None, 'data': 1}
        sim.schedule_event(10, event_obj)
        sim.time_queue.add_element.assert_called_once_with(10, (sim.time_process, event_obj))
        sim.time_queue.add_element.reset_mock()
        sim.schedule_event(0, event_obj)
        sim.time_queue.add_element.assert_called_once_with(0, (sim.time_process, event_obj))
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

        parent_process = sim.schedule(0, my_process)
        self.assertNotEqual(parent_process, my_process)
        self.__time_process_event.assert_called_once_with('kick-on')
        self.__time_process_event.reset_mock()
        # schedule an event
        with self.assertRaises(ValueError):
            # negative time
            self.sim.schedule_event(-0.5, {'producer': parent_process, 'data': 1})
        with self.assertRaises(ValueError):
            # missing producer
            self.sim.schedule_event(1, {'data': 1})

        self.sim.schedule_event(2, {'producer': parent_process, 'data': 1})
        time, (process, event_obj) = self.sim.time_queue.pop()
        self.assertEqual((time, process), (2, self.sim.time_process))
        self.assertEqual(event_obj, {'producer': parent_process, 'data': 1})
        retval = self.sim._signal_object(event_obj['producer'], event_obj)
        self.__time_process_event.assert_called_once_with(2, producer=event_obj['producer'], data=1)
        self.__time_process_event.reset_mock()
        self.assertEqual(retval, True)

        retval = self.sim.abort(parent_process, testing=-1)
        self.__time_process_event.assert_called_once_with(2, abort=True, testing=-1)
        self.__time_process_event.reset_mock()
        self.assertEqual(retval, False)

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
        self.sim.schedule_event(1, {'producer': producer, 'data': 1})
        self.sim.schedule_event(2, {'producer': producer, 'data': 2})
        self.sim.schedule_event(3, {'producer': producer, 'data': 3})
        num_events = self.sim.run()
        self.assertEqual(num_events, 3)
        calls = [call(producer=producer, data=1), call(producer=producer, data=2), call(producer=producer, data=3),]
        producer.signal.assert_has_calls(calls)
        producer.signal.reset_mock()
        num_events = len(self.sim.time_queue)
        self.assertEqual(num_events, 0)

    def test9_run_finite_process(self):
        self.sim = DSSimulation()
        producer = SomeObj()
        producer.signal = Mock()
        self.sim.schedule_event(1, {'producer': producer, 'data': 1})
        self.sim.schedule_event(2, {'producer': producer, 'data': 2})
        self.sim.schedule_event(3, {'producer': producer, 'data': 3})
        num_events = self.sim.run(2.5)
        self.assertEqual(num_events, 2)
        calls = [call(producer=producer, data=1), call(producer=producer, data=2),]
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
        self.sim.schedule_event(1, {'producer': producer, 'data': 1})
        self.sim.schedule_event(2, {'producer': producer, 'data': 2})
        self.sim.schedule_event(3, {'producer': producer, 'data': 3})
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
