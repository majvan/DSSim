# Copyright 2020- majvan (majvan@gmail.com)
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
Tests for SimProcessMixin methods (sim.schedule, sim.gwait, sim.wait,
sim.timeout, sim.observe_pre, sim.consume, etc.) exercised through
a running simulation loop.
'''
import unittest
from unittest.mock import Mock, call
from dssim import DSAbsTime, DSSimulation, DSAbortException
from dssim import DSSchedulable, DSProcess, DSCallback
from dssim.process import DSSubscriberContextManager, DSTimeoutContext, DSTimeoutContextError
from dssim import DSProducer


# ---------------------------------------------------------------------------
# sim.schedule() input-type routing
# ---------------------------------------------------------------------------

class TestScheduleRouting(unittest.TestCase):
    ''' Tests that sim.schedule() correctly wraps different input types. '''

    def test1_generator_returns_dsprocess(self):
        ''' Passing a generator to sim.schedule() wraps it in a DSProcess. '''
        sim = DSSimulation()
        def my_gen():
            yield
        result = sim.schedule(0, my_gen())
        self.assertIsInstance(result, DSProcess)

    def test2_coroutine_returns_dsprocess(self):
        ''' Passing a coroutine to sim.schedule() wraps it in a DSProcess. '''
        sim = DSSimulation()
        async def my_coro():
            pass
        result = sim.schedule(0, my_coro())
        self.assertIsInstance(result, DSProcess)
        sim.run()

    def test3_dsschedulable_returns_dsprocess(self):
        ''' A DSSchedulable-decorated function call returns a DSProcess. '''
        sim = DSSimulation()
        @DSSchedulable
        def my_fn():
            return 'done'
        result = sim.schedule(0, my_fn())
        self.assertIsInstance(result, DSProcess)

    def test4_dsprocess_returned_as_is(self):
        ''' Passing an existing DSProcess returns that same object. '''
        sim = DSSimulation()
        def my_gen():
            yield
        process = DSProcess(my_gen(), sim=sim)
        result = sim.schedule(0, process)
        self.assertIs(result, process)

    def test5_callable_returns_dscallback(self):
        ''' Passing a plain callable wraps it in a DSCallback. '''
        sim = DSSimulation()
        result = sim.schedule(0, Mock())
        self.assertIsInstance(result, DSCallback)

    def test6_isubscriber_schedules_event(self):
        ''' Passing a non-DSProcess ISubscriber schedules a None event. '''
        sim = DSSimulation()
        cb = DSCallback(Mock(), sim=sim)
        result = sim.schedule(1, cb)
        self.assertIs(result, cb)
        self.assertEqual(len(sim.time_queue), 1)

    def test7_negative_time_raises_value_error(self):
        ''' Negative scheduling time raises ValueError. '''
        sim = DSSimulation()
        def my_gen():
            yield
        with self.assertRaises(ValueError):
            sim.schedule(-1, my_gen())


class EventForwarder:
    ''' Minimal ISubscriber-duck that forwards events into a waiting process. '''
    def __init__(self, test_unit_running_sim, receiving_process):
        self.testunit = test_unit_running_sim
        self.receiving_process = receiving_process

    def send(self, **data):
        self.testunit.sim.send(self.receiving_process, **data)


# ---------------------------------------------------------------------------
# DSSchedulable + sim.run()
# ---------------------------------------------------------------------------

class TestDSSchedulable(unittest.TestCase):

    def __generator(self):
        yield 'First return'
        yield 'Second return'
        return 'Success'

    @DSSchedulable
    def __waiting_for_join(self, process, sim):
        yield from sim.gwait(cond=process)
        yield "After process finished"

    def test1_send_to_process(self):
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
        process.meta.cond.push(lambda e:True)  # accepting any event
        retval = sim.schedule_event(1, 'anything0', process)
        sim.run()
        self.assertEqual(process.value, 'Success')

    def test2_waiting_process(self):
        sim = DSSimulation()
        events = []

        def target():
            yield from sim.gwait(5)
            events.append('target_done')

        def waiter(t):
            yield from sim.gwait(cond=t)
            events.append('waiter_done')

        t = DSProcess(target(), sim=sim).schedule(0)
        w = DSProcess(waiter(t), sim=sim).schedule(0)
        sim.run(10)
        self.assertEqual(events, ['target_done', 'waiter_done'])


# ---------------------------------------------------------------------------
# Condition checking in a running simulation
# ---------------------------------------------------------------------------

class TestConditionChecking(unittest.TestCase):

    def test1_gwait_return(self):
        def my_process():
            yield 1
            yield from self.sim.gwait(cond=lambda e:True, val=2)
            return 3
        self.sim = DSSimulation()
        p = DSProcess(my_process(), sim=self.sim).schedule(0)
        retval = self.sim.send_object(p, None)  # kick the process
        retval = self.sim.send_object(p, None)
        self.assertTrue(retval == 2)
        try:
            retval = self.sim.send_object(p, None)
        except StopIteration as e:
            retval = e.value
        self.assertTrue(retval == 3)

        p = my_process()
        p = self.sim.schedule(0, p)
        retval = self.sim.send_object(p, None)  # kick the process
        self.assertTrue(retval == 1)
        retval = self.sim.send_object(p, None)
        self.assertTrue(retval == 2)
        try:
            retval = self.sim.send_object(p, None)
        except StopIteration as e:
            retval = e.value
        self.assertTrue(retval == 3)

        p = DSProcess(my_process(), sim=self.sim)
        p = self.sim.schedule(0, p)
        p.get_cond().push(lambda e:True)
        retval = p.try_send(None)
        self.assertTrue(retval == 1)
        retval = p.try_send(None)
        self.assertTrue(retval == 2)
        retval = p.try_send(None)
        self.assertTrue(retval == 3)

    def test2_wait_return(self):
        class SomeAwaitable:
            def __await__(self):
                yield 1
        async def my_process():
            await SomeAwaitable()
            await self.sim.wait(cond=lambda e:True, val=2)
            return 3
        self.sim = DSSimulation()
        p = DSProcess(my_process(), sim=self.sim).schedule(0)
        retval = self.sim.send_object(p, None)  # kick the process
        retval = self.sim.send_object(p, None)
        self.assertTrue(retval == 2)
        try:
            retval = self.sim.send_object(p, None)
        except StopIteration as e:
            retval = e.value
        self.assertTrue(retval == 3)

        p = my_process()
        p = self.sim.schedule(0, p)
        retval = self.sim.send_object(p, None)  # kick the process
        self.assertTrue(retval == 1)
        retval = self.sim.send_object(p, None)
        self.assertTrue(retval == 2)
        try:
            retval = self.sim.send_object(p, None)
        except StopIteration as e:
            retval = e.value
        self.assertTrue(retval == 3)

        p = DSProcess(my_process(), sim=self.sim)
        p = self.sim.schedule(0, p)
        p.get_cond().push(lambda e:True)
        retval = p.try_send(None)
        self.assertTrue(retval == 1)
        retval = p.try_send(None)
        self.assertTrue(retval == 2)
        retval = p.try_send(None)
        self.assertTrue(retval == 3)


# ---------------------------------------------------------------------------
# sim.observe_pre / sim.consume / sim.observe_consumed / sim.observe_unconsumed
# ---------------------------------------------------------------------------

class TestSubscriberContext(unittest.TestCase):

    def __process(self):
        yield 1

    def test1_sim_functions_producer(self):
        sim = DSSimulation()
        sim._parent_process = DSProcess(self.__process(), sim=sim)
        a, b, c, d = (DSProducer(), DSProducer(), DSProducer(), DSProducer(),)
        cm = sim.observe_pre(a, b, c)
        self.assertTrue(type(cm) == DSSubscriberContextManager)
        self.assertTrue(cm.pre == {a, b, c})
        self.assertTrue((len(cm.consume), len(cm.postp), len(cm.postn)) == (0, 0, 0))
        cm = sim.consume(a, c)
        self.assertTrue(type(cm) == DSSubscriberContextManager)
        self.assertTrue(cm.consume == {a, c})
        self.assertTrue((len(cm.pre), len(cm.postp), len(cm.postn)) == (0, 0, 0))
        cm = sim.observe_consumed(d)
        self.assertTrue(type(cm) == DSSubscriberContextManager)
        self.assertTrue(cm.postp == {d,})
        self.assertTrue((len(cm.pre), len(cm.consume), len(cm.postn)) == (0, 0, 0))
        cm = sim.observe_unconsumed(b)
        self.assertTrue(type(cm) == DSSubscriberContextManager)
        self.assertTrue(cm.postn == {b,})
        self.assertTrue((len(cm.pre), len(cm.consume), len(cm.postp)) == (0, 0, 0))
        cm = sim.observe_consumed(d) + sim.observe_pre(a) + sim.consume(b, c) + sim.observe_unconsumed(b)
        self.assertTrue(type(cm) == DSSubscriberContextManager)
        self.assertTrue(cm.pre == {a,})
        self.assertTrue(cm.consume == {b, c})
        self.assertTrue(cm.postp == {d,})
        self.assertTrue(cm.postn == {b,})

    def test2_sim_functions_future(self):
        sim = DSSimulation()
        sim._parent_process = DSProcess(self.__process(), sim=sim)
        a, b, c, d = (sim.future(), sim.future(), sim.future(), sim.future(),)
        cm = sim.observe_pre(a, b, c)
        self.assertTrue(type(cm) == DSSubscriberContextManager)
        self.assertTrue(cm.pre == a.get_future_eps() | b.get_future_eps() | c.get_future_eps())
        self.assertTrue((len(cm.consume), len(cm.postp), len(cm.postn)) == (0, 0, 0))
        cm = sim.consume(a, c)
        self.assertTrue(type(cm) == DSSubscriberContextManager)
        self.assertTrue(cm.consume == a.get_future_eps() | c.get_future_eps())
        self.assertTrue((len(cm.pre), len(cm.postp), len(cm.postn)) == (0, 0, 0))
        cm = sim.observe_consumed(d)
        self.assertTrue(type(cm) == DSSubscriberContextManager)
        self.assertTrue(cm.postp == d.get_future_eps())
        self.assertTrue((len(cm.pre), len(cm.consume), len(cm.postn)) == (0, 0, 0))
        cm = sim.observe_unconsumed(b)
        self.assertTrue(type(cm) == DSSubscriberContextManager)
        self.assertTrue(cm.postn == b.get_future_eps())
        self.assertTrue((len(cm.pre), len(cm.consume), len(cm.postp)) == (0, 0, 0))
        cm = sim.observe_consumed(d) + sim.observe_pre(a) + sim.consume(b, c) + sim.observe_unconsumed(b)
        self.assertTrue(type(cm) == DSSubscriberContextManager)
        self.assertTrue(cm.pre == a.get_future_eps())
        self.assertTrue(cm.consume == b.get_future_eps() | c.get_future_eps())
        self.assertTrue(cm.postp == d.get_future_eps())
        self.assertTrue(cm.postn == b.get_future_eps())


# ---------------------------------------------------------------------------
# sim.timeout() context manager in a running simulation
# ---------------------------------------------------------------------------

class TestTimeoutContext(unittest.TestCase):

    def test1_sim_timeout_positive(self):
        sim = DSSimulation()
        sim._parent_process = 'process'
        with sim.timeout(0) as cm:
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
            with sim.timeout(timeout) as cm:
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


# ---------------------------------------------------------------------------
# Simulation loop with processes (sim.schedule + sim.run)
# ---------------------------------------------------------------------------

class TestSim(unittest.TestCase):

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

    def setUp(self):
        self.__time_process_event = Mock()

    def test1_init_reset(self):
        sim = DSSimulation()
        self.assertEqual(len(sim.time_queue), 0)
        self.assertEqual(sim.time, 0)
        sim.schedule(0.5, self.__my_wait_process())
        sim.schedule(1.5, self.__my_wait_process())
        self.assertEqual(len(sim.time_queue), 2)
        sim.run(1)
        self.assertEqual(sim.time, 1)
        self.assertEqual(len(sim.time_queue), 1)
        sim.restart(0.9)
        self.assertEqual(len(sim.time_queue), 0)
        self.assertEqual(sim.time, 0.9)

    def test2_scheduling(self):
        ''' Assert the delay of scheduled process '''
        self.sim = DSSimulation()
        my_process = self.__my_time_process()
        with self.assertRaises(ValueError):
            _parent_process = self.sim.schedule(-0.5, my_process)
        _parent_process = self.sim.schedule(2, my_process)
        self.assertEqual(len(self.sim.time_queue), 1)

    def test3_scheduling_events(self):
        ''' Assert working with time queue when pushing events '''
        self.sim = DSSimulation()
        my_process = self.__my_time_process()
        with self.assertRaises(ValueError):
            self.sim.schedule(-0.5, my_process)

        _parent_process = self.sim.schedule(0, my_process)
        self.assertNotEqual(_parent_process, my_process)
        self.__time_process_event.assert_not_called()
        self.sim.run(0.5)
        self.__time_process_event.assert_called_once_with('kick-on')
        self.__time_process_event.reset_mock()
        with self.assertRaises(ValueError):
            self.sim.schedule_event(-0.5, {'producer': _parent_process, 'data': 1})

        self.assertEqual(self.sim.time, 0.5)
        event_obj = {'producer': _parent_process, 'data': 1}
        self.sim.schedule_event(2, event_obj, my_process)
        time, (process, event) = self.sim.time_queue.pop()
        self.assertEqual((time, process), (2.5, my_process))
        self.assertEqual(event, event_obj)
        self.sim.run(2.5)

        process = Mock()
        process.send = Mock()
        retval = _parent_process.abort(DSAbortException(testing=-1))
        self.__time_process_event.assert_called_once_with(2.5, {'abort': True, 'info': {'testing': -1}})
        self.__time_process_event.reset_mock()

    def test4_run_process(self):
        ''' Assert event loop behavior for process '''
        self.sim = DSSimulation()
        self.sim._parent_process = Mock()
        my_process = self.__my_time_process()
        _parent_process = self.sim.schedule(0, my_process)
        _parent_process.get_cond().push(lambda e:True)  # Accept any event

        self.sim.run(0.5)  # kick on the process
        self.sim.schedule_event(1, 3, _parent_process)
        self.sim.schedule_event(2, 2, _parent_process)
        self.sim.schedule_event(3, 1, _parent_process)
        retval = self.sim.run(0.5)
        self.__time_process_event.assert_called_once_with('kick-on')
        self.assertEqual(retval, (0.5, 1))
        self.__time_process_event.reset_mock()

        _parent_process.get_cond().push(lambda e:True)  # Accept any event
        self.sim.num_events = 0
        retval = self.sim.run()
        self.assertEqual(retval, (3.5, 3))
        calls = [call(1.5, 3), call(2.5, 2), call(3.5, 1),]
        self.__time_process_event.assert_has_calls(calls)
        retval = len(self.sim.time_queue)
        self.assertEqual(retval, 0)
        self.__time_process_event.reset_mock()

        self.sim.restart()
        self.sim.schedule_event(1, 3, _parent_process)
        self.sim.schedule_event(2, 2, _parent_process)
        self.sim.schedule_event(3, 1, _parent_process)
        retval = self.sim.run(2.5)
        self.assertEqual(retval, (2, 2))
        calls = [call(1, 3), call(2, 2),]
        self.__time_process_event.assert_has_calls(calls)
        num_events = len(self.sim.time_queue)
        self.assertEqual(num_events, 1)
        self.__time_process_event.reset_mock()

    def test5_waiting(self):
        self.sim = DSSimulation()
        process = DSProcess(self.__my_wait_process(), sim=self.sim).schedule(0)
        producer = EventForwarder(self, process)
        self.sim.schedule_event(1.5, {'producer': producer, 'data': 1}, process)
        self.sim.schedule_event(2.5, {'producer': producer, 'data': 2}, process)
        self.sim.schedule_event(3.5, {'producer': producer, 'data': 3}, process)
        retval = self.sim.run(5)
        self.assertEqual(retval, (3.5, 6))
        calls = [
            call(2, None),
            call(2.5, producer=producer, data=2),
            call(3.5, producer=producer, data=3),
        ]
        self.__time_process_event.assert_has_calls(calls)

    def test6_return_cleanup(self):
        def my_process2(sim, alwaystrue=True):
            if alwaystrue:
                return 100
            yield from sim.gwait(1)
        sim = DSSimulation()
        process = DSProcess(my_process2(sim), sim=sim).schedule(0)
        process.get_cond().push(lambda e:True)  # Accept any event
        sim.send_object(process, None)
        sim.schedule_event(1, {'data': 1}, process)
        sim.schedule_event(2, {'data': 2}, process)
        sim.schedule_event(3, {'data': 3}, process)
        retval = sim.run()
        self.assertEqual(retval, (3, 4))
        self.assertTrue(process.finished())

    def test7_timeout_cleanup(self):
        def my_process(sim):
            retval = yield from sim.gwait(1)
            yield  # wait here with no interaction to the time_queue

        sim = DSSimulation()
        process = DSProcess(my_process(sim), sim=sim).schedule(0)
        sim.send_object(process, None)  # go to the waiting
        sim.schedule_event(4, 'some_event', subscriber=process)
        self.assertTrue(len(sim.time_queue) == 3)
        retval = sim.send_object(process, 'value')
        self.assertTrue(retval is None)
        self.assertTrue(len(sim.time_queue) == 2)

    def test8_abort(self):
        self.sim = DSSimulation()
        process = self.sim.schedule(0, self.__my_wait_process())
        self.sim.schedule_event(1, {'data': 1}, process)
        num_events = self.sim.run(2.5)
        calls = [
            call(2, None),
        ]
        self.__time_process_event.assert_has_calls(calls)
        self.assertEqual(len(self.sim.time_queue), 0)
        self.sim.schedule_event(float('inf'), {'data': 2}, process)
        num_events = self.sim.run(2.5)
        self.__time_process_event.assert_has_calls([])
        self.assertEqual(len(self.sim.time_queue), 1)
        process.abort(DSAbortException(testing=-1)),
        num_events = self.sim.run(3)
        self.assertEqual(len(self.sim.time_queue), 0)


# ---------------------------------------------------------------------------
# DSProcess.abort() — started process (requires sim.run())
# ---------------------------------------------------------------------------

class TestDSProcessAbort(unittest.TestCase):

    def _waiting_gen(self, ran):
        ran.append('started')
        yield from self.sim.gwait(100)

    def _recording_gen(self, ran, tag='ran'):
        ran.append(tag)
        return
        yield

    def test1_unstarted_abort_generator_never_runs_after_sim_run(self):
        self.sim = DSSimulation()
        ran = []

        process = self.sim.schedule(1, self._recording_gen(ran))
        process.abort()
        self.sim.run(10)

        self.assertFalse(ran)

    def test2_unstarted_abort_other_processes_unaffected(self):
        self.sim = DSSimulation()
        ran = []

        proc_a = self.sim.schedule(1, self._recording_gen(ran, 'a'))
        proc_b = self.sim.schedule(2, self._recording_gen(ran, 'b'))

        proc_a.abort()
        self.sim.run(10)

        self.assertEqual(ran, ['b'])

    def test3_started_abort_raises_default_exception_in_generator(self):
        self.sim = DSSimulation()
        caught = []

        def my_gen():
            try:
                yield from self.sim.gwait(100)
            except DSAbortException as exc:
                caught.append(exc)

        process = self.sim.schedule(0, my_gen())
        self.sim.run(1)
        self.assertTrue(process.started())

        process.abort()

        self.assertEqual(len(caught), 1)
        self.assertIsInstance(caught[0], DSAbortException)

    def test4_started_abort_raises_custom_exception_in_generator(self):
        class _MyExc(Exception):
            pass

        self.sim = DSSimulation()
        caught = []

        def my_gen():
            try:
                yield from self.sim.gwait(100)
            except _MyExc as exc:
                caught.append(exc)

        process = self.sim.schedule(0, my_gen())
        self.sim.run(1)
        self.assertTrue(process.started())

        process.abort(_MyExc())

        self.assertEqual(len(caught), 1)
        self.assertIsInstance(caught[0], _MyExc)


if __name__ == '__main__':
    unittest.main()
