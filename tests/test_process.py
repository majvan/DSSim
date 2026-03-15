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
Tests for DSProcess and related classes (DSSchedulable, DSSubscriberContextManager,
DSTimeoutContext).  These tests exercise the process / context-manager objects
directly — they do not run a full simulation loop (sim.run()).
'''
import unittest
from unittest.mock import Mock, MagicMock, call
from dssim import DSSimulation, DSAbortException
from dssim import DSSchedulable, DSProcess
from dssim.pubsub.process import DSSubscriberContextManager, DSTimeoutContext, DSTimeoutContextError
from dssim import DSPub
from dssim.pubsub.base import StackedCond

def _peek_timequeue_event(time_queue):
    return time_queue.get_first_time(), time_queue._queue[0][1][0]

def _pop_timequeue_event(time_queue):
    t = time_queue.get_first_time()
    bucket = time_queue.pop_first_bucket()
    event = bucket.popleft()
    if bucket:
        time_queue.insertleft(t, bucket)
    return t, event


class FutureMock(Mock):
    def get_eps(self):
        return {self,}

class SomeObj:
    pass


# ---------------------------------------------------------------------------
# DSSchedulable decorator
# ---------------------------------------------------------------------------

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

    def test1_schedulable_fcn(self):
        process = self.__fcn()
        try:
            process.send(None)
        except StopIteration as e:
            retval = e.value
        self.assertEqual(retval, 'Success')

    def test2_schedulable_fcn_as_process(self):
        sim = DSSimulation()
        process = DSProcess(self.__fcn(), sim=sim).schedule(0)
        try:
            process.send(None)
        except StopIteration as e:
            retval = e.value
        self.assertEqual(retval, 'Success')

        process = DSProcess(self.__fcn(), sim=sim).schedule(0)
        process.get_cond().push(lambda e:True)
        retval = sim.send_object(process, None)
        self.assertEqual(retval, 'Success')
        self.assertEqual(process.value, 'Success')

    def test3_generator_as_process(self):
        sim = DSSimulation()
        process = DSProcess(self.__generator(), sim=sim).schedule(0)
        retval = process.send(None)
        self.assertEqual(retval, 'First return')
        retval = process.send(None)
        self.assertEqual(retval, 'Second return')
        try:
            process.send(None)
        except StopIteration as e:
            retval = e.value
        self.assertEqual(retval, 'Success')

        process = DSProcess(self.__generator(), sim=sim)
        retval = process.send(None)
        self.assertEqual(retval, 'First return')
        retval = process.send(None)
        self.assertEqual(retval, 'Second return')
        process.get_cond().push(lambda e:True)
        retval = sim.send_object(process, None)
        self.assertEqual(retval, 'Success')
        self.assertEqual(process.value, 'Success')

    def test4_send_abort_to_generator(self):
        process = self.__loopback_generator()
        retval = next(process)
        retval = process.send('from_test0')
        self.assertEqual(retval, 'from_test0')
        retval = process.send(DSAbortException(publisher='test'))
        self.assertTrue(isinstance(retval, DSAbortException))

    def test5_send_abort_to_generator_as_process(self):
        class MyExc(Exception):
            pass
        def my_wait(sim):
            i = 0
            while True:
                i = i + 1
                yield from sim.gwait(cond=lambda c: True, val=i)

        sim = DSSimulation()
        process = DSProcess(my_wait(sim), sim=sim)
        process.get_cond().push(lambda e:True)
        sim._parent_process = process  # needed because after kick the process will gwait
        retval = process.send(None)
        retval = process.send('from_test0')
        self.assertEqual(retval, 2)
        self.assertEqual(process.value, 2)
        self.assertEqual(process.exc, None)
        process.abort()
        self.assertTrue(isinstance(process.exc, DSAbortException))
        self.assertEqual(process.value, 2)

        process = DSProcess(my_wait(sim), sim=sim)
        process.get_cond().push(lambda e:True)
        retval = process.send(None)
        process.abort(MyExc())
        self.assertTrue(isinstance(process.exc, MyExc))
        self.assertEqual(process.value, 1)

    def test6_scheduled_start_ignores_non_none_bootstrap_event(self):
        def gen():
            event = yield 'booted'
            return event

        sim = DSSimulation()
        process = DSProcess(gen(), sim=sim).schedule(0)

        # First payload is ignored in scheduled-start mode and used only to kick startup.
        retval = sim.send_object(process, 'ignored-first')
        self.assertEqual(retval, 'booted')
        self.assertTrue(process.started())
        self.assertFalse(process.finished())

        # Allow non-timeout events after startup and verify normal delivery resumes.
        process.get_cond().push(lambda e: True)
        retval = sim.send_object(process, 'accepted-second')
        self.assertEqual(retval, 'accepted-second')
        self.assertTrue(process.finished())


# ---------------------------------------------------------------------------
# Exception propagation inside generators / processes
# ---------------------------------------------------------------------------

class TestException(unittest.TestCase):

    def __my_buggy_code(self):
        yield 'First is ok'
        a = 10 / 0
        return 'Second unreachable'

    def __first_cyclic(self, sim):
        process2 = yield 'Kick-on first'
        yield
        sim.send_object(process2, 'Signal from first process')
        yield 'After signalling first'
        return 'Done first'

    def __second_cyclic(self, sim):
        process1 = yield 'Kick-on second'
        yield
        sim.send_object(process1, 'Signal from second process')
        yield 'After signalling second'
        return 'Done second'

    def test1_exception_usercode_generator(self):
        sim = DSSimulation()
        process = DSProcess(self.__my_buggy_code()).schedule(0)
        process.send(None)  # kick the process
        process.get_cond().push(lambda e:True)  # Accept all events
        try:
            retval = sim.send_object(process, 'My data')
            self.assertTrue(1 == 2)
        except ZeroDivisionError as exc:
            self.assertTrue('generator already executing' not in str(exc))

    def test2_exception_usercode_process(self):
        sim = DSSimulation()
        process1 = DSProcess(self.__first_cyclic(sim), name="First cyclic", sim=sim).schedule(0)
        sim.send_object(process1, None)  # initialize via send_object so _started is set correctly
        process1.meta.cond.push(lambda e:True)  # accept any event
        process2 = DSProcess(self.__second_cyclic(sim), name="Second cyclic", sim=sim).schedule(0)
        sim.send_object(process2, None)  # initialize via send_object so _started is set correctly
        process2.meta.cond.push(lambda e:True)  # accept any event
        sim.send_object(process1, process2)  # Inform processes about the other process
        sim.send_object(process2, process1)
        try:
            sim.send_object(process1, 'My data')
            self.assertTrue(1 == 2)
        except ValueError as exc:
            self.assertTrue('generator already executing' in str(exc))


# ---------------------------------------------------------------------------
# Condition / metadata storage inside DSProcess
# ---------------------------------------------------------------------------

class TestConditionChecking(unittest.TestCase):

    def __my_process(self):
        while True:
            yield 1

    def test1_check_storing_cond_in_metadata(self):
        ''' By calling wait, the metadata.cond should be stored '''
        sim = DSSimulation()
        waitable = DSProcess(sim.gwait(cond='condition'), sim=sim).schedule(0)
        sim._parent_process = waitable
        meta = waitable.meta = Mock()
        cond = meta.cond = Mock()
        cond.push, cond.pop = Mock(), Mock()
        cond.check = Mock(return_value=(True, 'return event'))
        cond.cond_value = lambda: 'condition value result'
        waitable._starter.send(None)  # kick the process
        cond.push.assert_has_calls([call(None), call('condition'),])
        try:
            retval = sim.send_object(waitable, 'something')
        except StopIteration as e:
            retval = e.value
        self.assertTrue(retval == 'return event')

    def test2_check_one_cond(self):
        ''' Test all types of conditions - see _check_cond '''
        exception = Exception('error')
        stack = StackedCond()
        for cond, event, expected_result in (
            (lambda e:False, None, (False, None)),
            (lambda e:True, None, (True, None)),
            ('abc', None, (False, None)),
            (None, None, (True, None)),
            (lambda e:False, exception, (True, exception)),
            (lambda e:True, exception, (True, exception)),
            ('abc', exception, (True, exception)),
            (exception, exception, (True, exception)),
            (lambda e:False, 'def', (False, 'def')),
            (lambda e:True, 'def', (True, 'def')),
            ('abc', 'def', (False, 'def')),
            ('def', 'def', (True, 'def')),
        ):
            stack.push(cond)
            retval = stack.check(event)
            self.assertEqual(retval, expected_result)
            stack.pop()
            self.assertTrue(len(stack.conds) == 0)

    def test3_check_one_cond_and_timeout(self):
        ''' Test all types of conditions with default None timeout '''
        exception = Exception('error')
        stack = StackedCond()
        stack.push(None)
        for cond, event, expected_result in (
            (lambda e:False, None, (True, None)),
            (lambda e:True, None, (True, None)),
            ('abc', None, (True, None)),
            (None, None, (True, None)),
            (lambda e:False, exception, (True, exception)),
            (lambda e:True, exception, (True, exception)),
            ('abc', exception, (True, exception)),
            (exception, exception, (True, exception)),
            (lambda e:False, 'def', (False, 'def')),
            (lambda e:True, 'def', (True, 'def')),
            ('abc', 'def', (False, 'def')),
            ('def', 'def', (True, 'def')),
        ):
            stack.push(cond)
            retval = stack.check(event)
            self.assertEqual(retval, expected_result)
            stack.pop()
            self.assertTrue(len(stack.conds) == 1)

    def test4_check_condition(self):
        ''' The check_condition should retrieve cond from the metadata and then call _check_cond '''
        sim = DSSimulation()
        p = DSProcess(self.__my_process(), sim=sim).schedule(0)
        p._starter.send(None)  # initialize the generator before replacing meta
        p.meta = SomeObj()
        p.meta.cond = MagicMock()
        p.meta.cond.check = Mock(return_value=(True, 'abc'))
        retval = sim.send_object(p, 'test')
        p.meta.cond.check.assert_called_once()
        self.assertEqual(retval, True)


# ---------------------------------------------------------------------------
# DSSubscriberContextManager construction
# ---------------------------------------------------------------------------

class TestSubscriberContext(unittest.TestCase):

    def __process(self):
        yield 1

    def test1_init_add_remove_producer(self):
        sim = DSSimulation()
        p = DSProcess(self.__process(), sim=sim)
        a, b, c, d, e = DSPub(), DSPub(), DSPub(), DSPub(), DSPub()
        cm = DSSubscriberContextManager(p, DSPub.Phase.PRE, (a, b, c))
        self.assertTrue((len(cm.pre), len(cm.consume), len(cm.postp), len(cm.postn)) == (3, 0, 0, 0))
        cm = DSSubscriberContextManager(p, DSPub.Phase.CONSUME, (a, b, c, d))
        self.assertTrue((len(cm.pre), len(cm.consume), len(cm.postp), len(cm.postn)) == (0, 4, 0, 0))
        cm = DSSubscriberContextManager(p, DSPub.Phase.POST_HIT, (a, b, c, d, e))
        self.assertTrue((len(cm.pre), len(cm.consume), len(cm.postp), len(cm.postn)) == (0, 0, 5, 0))
        cm = DSSubscriberContextManager(p, DSPub.Phase.POST_MISS, (c, d, e))
        self.assertTrue((len(cm.pre), len(cm.consume), len(cm.postp), len(cm.postn)) == (0, 0, 0, 3))
        cm = cm + DSSubscriberContextManager(p, DSPub.Phase.CONSUME, (a, b, c))
        self.assertTrue((len(cm.pre), len(cm.consume), len(cm.postp), len(cm.postn)) == (0, 3, 0, 3))
        cm = cm + DSSubscriberContextManager(p, DSPub.Phase.CONSUME, (d,))
        self.assertTrue((len(cm.pre), len(cm.consume), len(cm.postp), len(cm.postn)) == (0, 4, 0, 3))
        cm = cm + DSSubscriberContextManager(p, DSPub.Phase.CONSUME, (c,))
        self.assertTrue((len(cm.pre), len(cm.consume), len(cm.postp), len(cm.postn)) == (0, 4, 0, 3))

    def test2_init_add_remove_future(self):
        sim = DSSimulation()
        p = DSProcess(self.__process(), sim=sim)
        a, b, c, d, e = sim.future(), sim.future(), sim.future(), sim.future(), sim.future()
        cm = DSSubscriberContextManager(p, DSPub.Phase.PRE, (a, b, c))
        self.assertTrue((len(cm.pre), len(cm.consume), len(cm.postp), len(cm.postn)) == (3, 0, 0, 0))
        cm = DSSubscriberContextManager(p, DSPub.Phase.CONSUME, (a, b, c, d))
        self.assertTrue((len(cm.pre), len(cm.consume), len(cm.postp), len(cm.postn)) == (0, 4, 0, 0))
        cm = DSSubscriberContextManager(p, DSPub.Phase.POST_HIT, (a, b, c, d, e))
        self.assertTrue((len(cm.pre), len(cm.consume), len(cm.postp), len(cm.postn)) == (0, 0, 5, 0))
        cm = DSSubscriberContextManager(p, DSPub.Phase.POST_MISS, (c, d, e))
        self.assertTrue((len(cm.pre), len(cm.consume), len(cm.postp), len(cm.postn)) == (0, 0, 0, 3))
        cm = cm + DSSubscriberContextManager(p, DSPub.Phase.CONSUME, (a, b, c))
        self.assertTrue((len(cm.pre), len(cm.consume), len(cm.postp), len(cm.postn)) == (0, 3, 0, 3))
        cm = cm + DSSubscriberContextManager(p, DSPub.Phase.CONSUME, (d,))
        self.assertTrue((len(cm.pre), len(cm.consume), len(cm.postp), len(cm.postn)) == (0, 4, 0, 3))
        cm = cm + DSSubscriberContextManager(p, DSPub.Phase.CONSUME, (c,))
        self.assertTrue((len(cm.pre), len(cm.consume), len(cm.postp), len(cm.postn)) == (0, 4, 0, 3))

    def test3_enter_exit(self):
        sim = DSSimulation()
        p = DSProcess(self.__process(), sim=sim)
        a, b, c, d, e, f = (FutureMock(), FutureMock(), FutureMock(), FutureMock(), FutureMock(), FutureMock())
        cm = (DSSubscriberContextManager(p, DSPub.Phase.POST_MISS, (f,))
              + DSSubscriberContextManager(p, DSPub.Phase.PRE, (a, c))
              + DSSubscriberContextManager(p, DSPub.Phase.POST_HIT, (b,))
              + DSSubscriberContextManager(p, DSPub.Phase.CONSUME, (e,)))
        cm.__enter__()
        a.add_subscriber.assert_called_once_with(p, DSPub.Phase.PRE)
        c.add_subscriber.assert_called_once_with(p, DSPub.Phase.PRE)
        b.add_subscriber.assert_called_once_with(p, DSPub.Phase.POST_HIT)
        f.add_subscriber.assert_called_once_with(p, DSPub.Phase.POST_MISS)
        d.add_subscriber.assert_not_called()
        e.add_subscriber.assert_called_once_with(p, DSPub.Phase.CONSUME)
        _ = a.reset_mock(), b.reset_mock(), c.reset_mock(), d.reset_mock()
        cm.__exit__(None, None, None)
        a.remove_subscriber.assert_called_once_with(p, DSPub.Phase.PRE)
        c.remove_subscriber.assert_called_once_with(p, DSPub.Phase.PRE)
        b.remove_subscriber.assert_called_once_with(p, DSPub.Phase.POST_HIT)
        f.remove_subscriber.assert_called_once_with(p, DSPub.Phase.POST_MISS)
        d.remove_subscriber.assert_not_called()
        e.remove_subscriber.assert_called_once_with(p, DSPub.Phase.CONSUME)


# ---------------------------------------------------------------------------
# DSTimeoutContext construction and rescheduling
# ---------------------------------------------------------------------------

class TestTimeoutContext(unittest.TestCase):

    def test1_init(self):
        from unittest.mock import call
        sim = Mock()
        cm = DSTimeoutContext(None, sim=sim)
        self.assertTrue(cm.time is None)
        self.assertTrue(cm.sim is sim)
        sim.schedule_event.assert_not_called()

        sim = Mock()
        cm = DSTimeoutContext(0, sim=sim)
        self.assertTrue(cm.time == 0)
        self.assertTrue(cm.sim is sim)
        sim.schedule_event.assert_has_calls([call(0, cm.exc),])

        sim = Mock()
        event = DSTimeoutContextError()
        cm = DSTimeoutContext(0, event, sim=sim)
        self.assertTrue(cm.time == 0)
        self.assertTrue(cm.sim is sim)
        sim.schedule_event.assert_has_calls([call(0, event),])

    def test2_reschedule(self):
        sim = DSSimulation()
        sim._parent_process = 'process'
        cm = DSTimeoutContext(None, 'hello', sim=sim)
        self.assertTrue(sim.time_queue.event_count() == 0)
        cm.reschedule(2)
        self.assertTrue(sim.time_queue.event_count() == 1)
        self.assertTrue(_peek_timequeue_event(sim.time_queue) == (2, ('process', 'hello')))
        cm.reschedule(1)
        self.assertTrue(sim.time_queue.event_count() == 1)
        self.assertTrue(_peek_timequeue_event(sim.time_queue) == (1, ('process', 'hello')))

        sim = DSSimulation()
        sim._parent_process = 'process'
        cm = DSTimeoutContext(0, 'hi', sim=sim)
        self.assertTrue(sim.time_queue.event_count() == 1)
        self.assertTrue(_peek_timequeue_event(sim.time_queue) == (0, ('process', 'hi')))
        cm.reschedule(2)
        self.assertTrue(sim.time_queue.event_count() == 1)
        self.assertTrue(_peek_timequeue_event(sim.time_queue) == (2, ('process', 'hi')))
        cm.reschedule(1)
        self.assertTrue(sim.time_queue.event_count() == 1)
        self.assertTrue(_peek_timequeue_event(sim.time_queue) == (1, ('process', 'hi')))

        event = 'hi'
        cm = DSTimeoutContext(3, 'bye', sim=sim)
        self.assertTrue(sim.time_queue.event_count() == 2)
        self.assertTrue(_peek_timequeue_event(sim.time_queue) == (1, ('process', 'hi')))
        cm.reschedule(0)
        self.assertTrue(sim.time_queue.event_count() == 2)
        self.assertTrue(_peek_timequeue_event(sim.time_queue) == (0, ('process', 'bye')))
        cm.reschedule(3)
        self.assertTrue(sim.time_queue.event_count() == 2)
        self.assertTrue(_pop_timequeue_event(sim.time_queue) == (1, ('process', 'hi')))
        self.assertTrue(_pop_timequeue_event(sim.time_queue) == (3, ('process', 'bye')))


# ---------------------------------------------------------------------------
# DSProcess.abort() — unstarted process (no sim.run())
# ---------------------------------------------------------------------------

class TestDSProcessAbort(unittest.TestCase):
    '''Tests for DSProcess.abort() for a process not yet started (no sim.run()).'''

    def _waiting_gen(self, ran):
        ran.append('started')
        yield from self.sim.gwait(100)

    def test1_unstarted_abort_removes_startup_event_from_time_queue(self):
        self.sim = DSSimulation()
        ran = []
        process = self.sim.schedule(5, self._waiting_gen(ran))
        self.assertFalse(process.started())

        process.abort()

        process_entries = sum(
            1 for _, (consumer, _) in
            [_pop_timequeue_event(self.sim.time_queue) for _ in range(self.sim.time_queue.event_count())]
            if consumer is process
        )
        self.assertEqual(process_entries, 0)
        self.assertFalse(ran)

    def test2_unstarted_abort_sets_default_exception(self):
        self.sim = DSSimulation()
        process = self.sim.schedule(5, self._waiting_gen([]))

        process.abort()

        self.assertIsInstance(process.exc, DSAbortException)

    def test3_unstarted_abort_sets_custom_exception(self):
        class _MyExc(Exception):
            pass

        self.sim = DSSimulation()
        process = self.sim.schedule(5, self._waiting_gen([]))

        process.abort(_MyExc())

        self.assertIsInstance(process.exc, _MyExc)


if __name__ == '__main__':
    unittest.main()
