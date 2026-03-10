# Copyright 2020 NXP Semiconductors
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
Tests for the core DSSimulation layer using only plain ISubscriber mocks.
No DSProcess, DSProducer or DSConsumer objects are used here.
'''
import unittest
from unittest.mock import Mock, call
from dssim import DSAbsTime, DSSimulation, DSSchedulable, TinyLayer2
from dssim.simulation import VoidSubscriber, void_subscriber


class SomeObj:
    pass


# ---------------------------------------------------------------------------
# Core DSSimulation behaviour — pure ISubscriber / mock consumers
# ---------------------------------------------------------------------------

class TestSim(unittest.TestCase):
    ''' Tests for the core DSSimulation time-queue and dispatch machinery. '''

    def test1_time_conversion(self):
        sim = DSSimulation()
        sim._simtime = 5
        t = sim.to_abs_time(10)
        self.assertEqual(t.value, 15)
        self.assertEqual(t.to_number(), 15)
        self.assertTrue(isinstance(t.to_number(), int))
        sim._simtime = 5.0
        t = sim.to_abs_time(10)
        self.assertEqual(t.value, 15)
        self.assertEqual(t.to_number(), 15)
        self.assertTrue(isinstance(t.to_number(), float))

    def test2_scheduling_events(self):
        ''' Assert working with time queue when pushing events '''
        sim = DSSimulation()
        sim.time_queue.add_element = Mock()
        sim._parent_process = 123456
        event_obj = {'producer': None, 'data': 1}
        sim.schedule_event(10, event_obj)
        sim.time_queue.add_element.assert_called_once_with(10, (123456, event_obj))
        sim.time_queue.add_element.reset_mock()
        sim.schedule_event(0, event_obj)
        sim.time_queue.add_element.assert_called_once_with(0, (123456, event_obj))
        sim.time_queue.add_element.reset_mock()
        with self.assertRaises(ValueError):
            sim.schedule_event(-0.5, event_obj)

    def test3_cleanup(self):
        ''' Assert deleting from time queue when deleting events '''
        sim = DSSimulation()
        sim.time_queue.delete_cond = Mock()
        consumer = Mock()
        sim.cleanup(consumer)
        sim.time_queue.delete_cond.assert_called_once()
        args, kwargs = sim.time_queue.delete_cond.call_args
        lambda_fcn = args[0]
        self.assertTrue(lambda_fcn((consumer,)))
        self.assertFalse(lambda_fcn((1,)))
        self.assertEqual(kwargs, {})

    def test4_scheduling(self):
        ''' send_object delivers the event to a plain duck-typed ISubscriber. '''
        self.sim = DSSimulation()
        producer = SomeObj()
        producer.send = Mock()
        event_obj = SomeObj()
        retval = self.sim.send_object(producer, event_obj)
        producer.send.assert_called_once_with(event_obj)

    def test5_run_producer(self):
        ''' sim.run() dispatches scheduled events to a mock ISubscriber. '''
        self.sim = DSSimulation()
        consumer = Mock()
        consumer.meta.cond.check = lambda e:(True, e)  # Accept any event
        consumer.send = Mock()
        consumer.get_cond = lambda: consumer.meta.cond
        consumer.try_send = lambda e: consumer.send(e)
        self.sim.schedule_event(1, 3, consumer)
        self.sim.schedule_event(2, 2, consumer)
        self.sim.schedule_event(3, 1, consumer)
        retval = self.sim.run()
        self.assertEqual(retval, (3, 3))
        calls = [call(3), call(2), call(1),]
        consumer.send.assert_has_calls(calls)
        num_events = len(self.sim.time_queue)
        self.assertEqual(num_events, 0)
        consumer.send.reset_mock()

        self.sim.restart()
        self.sim.schedule_event(1, 3, consumer)
        self.sim.schedule_event(2, 2, consumer)
        self.sim.schedule_event(3, 1, consumer)
        retval = self.sim.run(2.5)
        self.assertEqual(retval, (2, 2))
        calls = [call(3), call(2),]
        consumer.send.assert_has_calls(calls)
        num_events = len(self.sim.time_queue)
        self.assertEqual(num_events, 1)

    def test6_run_dispatches_without_consumer_try_send(self):
        ''' run() dispatches via simulation send_object path, not consumer.try_send. '''
        self.sim = DSSimulation()
        consumer = Mock()
        consumer.meta.cond.check = lambda e: (True, e)
        consumer.get_cond = lambda: consumer.meta.cond
        consumer.send = Mock()
        consumer.try_send = Mock(side_effect=AssertionError('run() should not call consumer.try_send'))
        self.sim.schedule_event(1, 'hello', consumer)
        retval = self.sim.run()
        self.assertEqual(retval, (1, 1))
        consumer.send.assert_called_once_with('hello')
        consumer.try_send.assert_not_called()

    def test7_run_still_checks_condition_before_send(self):
        ''' run() must preserve condition gating semantics for consumers. '''
        self.sim = DSSimulation()
        consumer = Mock()
        consumer.meta.cond.check = Mock(return_value=(False, 'ignored'))
        consumer.get_cond = lambda: consumer.meta.cond
        consumer.send = Mock()
        consumer.try_send = Mock(side_effect=AssertionError('run() should not call consumer.try_send'))
        self.sim.schedule_event(1, 'hello', consumer)
        retval = self.sim.run()
        self.assertEqual(retval, (1, 1))
        consumer.meta.cond.check.assert_called_once_with('hello')
        consumer.send.assert_not_called()
        consumer.try_send.assert_not_called()


# ---------------------------------------------------------------------------
# schedule_event_now and the now_queue — pure mock consumers
# ---------------------------------------------------------------------------

class TestScheduleEventNow(unittest.TestCase):
    ''' Tests for DSSimulation.schedule_event_now() and the now_queue, using
    plain Mock consumers (no DSCallback / DSProcess). '''

    def test1_appends_to_now_queue(self):
        ''' schedule_event_now appends a (consumer, event) tuple to now_queue. '''
        sim = DSSimulation()
        consumer = Mock()
        sim.schedule_event_now('ev', consumer)
        self.assertEqual(len(sim.now_queue), 1)
        c, e = sim.now_queue[0]
        self.assertIs(c, consumer)
        self.assertEqual(e, 'ev')

    def test2_default_consumer_is_parent_process(self):
        ''' When consumer is omitted, _parent_process is used as the target. '''
        sim = DSSimulation()
        sentinel = object()
        sim._parent_process = sentinel
        sim.schedule_event_now('ev')
        c, e = sim.now_queue[0]
        self.assertIs(c, sentinel)

    def test3_restart_clears_now_queue(self):
        ''' restart() resets the now_queue to empty. '''
        sim = DSSimulation()
        consumer = Mock()
        sim.schedule_event_now('ev1', consumer)
        sim.schedule_event_now('ev2', consumer)
        self.assertEqual(len(sim.now_queue), 2)
        sim.restart()
        self.assertEqual(len(sim.now_queue), 0)

    def test4_cleanup_removes_consumer_events_from_now_queue(self):
        ''' cleanup(consumer) filters that consumer's events out of now_queue. '''
        sim = DSSimulation()
        ca = Mock()
        ca.meta.cond = Mock()
        cb = Mock()
        cb.meta.cond = Mock()
        sim.schedule_event_now('ev_a1', ca)
        sim.schedule_event_now('ev_b',  cb)
        sim.schedule_event_now('ev_a2', ca)
        self.assertEqual(len(sim.now_queue), 3)
        sim.cleanup(ca)
        self.assertEqual(len(sim.now_queue), 1)
        c, e = sim.now_queue[0]
        self.assertIs(c, cb)
        self.assertEqual(e, 'ev_b')


# ---------------------------------------------------------------------------
# Scheduling plain generators, coroutines, and DSSchedulable functions
# ---------------------------------------------------------------------------

class TestSimScheduleGenerators(unittest.TestCase):
    ''' Tests that sim.schedule() correctly runs plain generators, coroutines,
    and DSSchedulable-decorated functions, verified by behavioral outcomes only.
    No DSProcess is imported or referenced directly. '''

    def test1_generator_starts_at_scheduled_time(self):
        ''' A plain generator only starts when its scheduled time is reached. '''
        sim = DSSimulation()
        log = []
        def my_gen():
            log.append(sim.time)
            yield
        sim.schedule(3, my_gen())
        self.assertEqual(log, [])
        sim.run()
        self.assertEqual(log, [3])

    def test2_coroutine_runs_to_completion(self):
        ''' An async coroutine scheduled via sim.schedule() runs in sim.run(). '''
        sim = DSSimulation()
        log = []
        async def my_coro():
            log.append('ran')
        sim.schedule(0, my_coro())
        sim.run()
        self.assertEqual(log, ['ran'])

    def test3_dsschedulable_runs_to_completion(self):
        ''' A DSSchedulable-decorated function runs when scheduled. '''
        sim = DSSimulation()
        log = []
        @DSSchedulable
        def my_fn():
            log.append('ran')
            return 'done'
        sim.schedule(0, my_fn())
        sim.run()
        self.assertEqual(log, ['ran'])

    def test4_two_generators_run_in_time_order(self):
        ''' Two generators scheduled at different times start in time order. '''
        sim = DSSimulation()
        log = []
        def gen(tag):
            log.append(tag)
            yield
        sim.schedule(2, gen('second'))
        sim.schedule(1, gen('first'))
        sim.run()
        self.assertEqual(log, ['first', 'second'])

    def test5_negative_time_raises_value_error(self):
        ''' sim.schedule() with negative time raises ValueError. '''
        sim = DSSimulation()
        def my_gen():
            yield
        with self.assertRaises(ValueError):
            sim.schedule(-1, my_gen())


# ---------------------------------------------------------------------------
# VoidSubscriber
# ---------------------------------------------------------------------------

class TestVoidSubscriber(unittest.TestCase):
    ''' Tests for VoidSubscriber and the void_subscriber singleton. '''

    def test1_send_is_noop(self):
        ''' VoidSubscriber.send() silently ignores any event. '''
        vs = VoidSubscriber()
        vs.send(None)   # must not raise

    def test2_send_accepts_any_event(self):
        ''' No exception is raised regardless of the event value. '''
        vs = VoidSubscriber()
        for event in (0, 'hello', {}, object()):
            vs.send(event)  # must not raise

    def test3_default_name(self):
        ''' Default name is set when no name is provided. '''
        vs = VoidSubscriber()
        self.assertIsInstance(vs.name, str)
        self.assertTrue(len(vs.name) > 0)

    def test4_custom_name(self):
        ''' Custom name is stored on the instance. '''
        vs = VoidSubscriber(name='my-void')
        self.assertEqual(vs.name, 'my-void')

    def test5_singleton_is_void_subscriber_instance(self):
        ''' void_subscriber is an instance of VoidSubscriber. '''
        self.assertIsInstance(void_subscriber, VoidSubscriber)

    def test6_simulation_parent_process_defaults_to_void_subscriber(self):
        ''' After construction, sim._parent_process is the void_subscriber singleton. '''
        sim = DSSimulation(layer2=TinyLayer2)
        self.assertIs(sim._parent_process, void_subscriber)

    def test7_simulation_restart_restores_void_subscriber(self):
        ''' restart() resets _parent_process back to void_subscriber. '''
        sim = DSSimulation(layer2=TinyLayer2)
        sim._parent_process = Mock()
        sim.restart()
        self.assertIs(sim._parent_process, void_subscriber)


# ---------------------------------------------------------------------------
# SimWaitMixin — basic timeout-only gwait / wait
# SimProcessMixin is bypassed via _TestSim so SimWaitMixin's methods are
# actually under test (not the full condition-aware overrides).
# ---------------------------------------------------------------------------

class TestSimWaitMixin(unittest.TestCase):
    ''' Tests for SimWaitMixin.gwait / SimWaitMixin.wait.
    Uses a local _TestSim subclass that replaces gwait/wait/schedule with the
    SimWaitMixin / SimScheduleMixin versions, preventing SimProcessMixin from
    wrapping generators in DSProcess or overriding the wait methods. '''

    def _make_sim(self):
        ''' Minimal simulation: TinyLayer2 only (SimWaitMixin + SimScheduleMixin). '''
        return DSSimulation(layer2=TinyLayer2)

    def test1_gwait_returns_none_on_timeout(self):
        ''' gwait(timeout) returns None when the timeout fires with no prior event. '''
        sim = self._make_sim()
        result = []
        def my_gen():
            retval = yield from sim.gwait(5)
            result.append(retval)
        sim.schedule(0, my_gen())
        t, _ = sim.run()
        self.assertEqual(result, [None])
        self.assertEqual(t, 5)

    def test2_gwait_returns_event_before_timeout(self):
        ''' gwait(10) returns the event when one arrives before the timeout. '''
        sim = self._make_sim()
        result = []
        def my_gen():
            retval = yield from sim.gwait(10)
            result.append(retval)
        gen = my_gen()
        sim.schedule(0, gen)
        sim.schedule_event(3, 'hello', gen)
        t, _ = sim.run()
        self.assertEqual(result, ['hello'])
        self.assertEqual(t, 3)

    def test3_wait_returns_none_on_timeout(self):
        ''' wait(timeout) returns None when the timeout fires with no prior event. '''
        sim = self._make_sim()
        result = []
        async def my_coro():
            retval = await sim.wait(5)
            result.append(retval)
        sim.schedule(0, my_coro())
        t, _ = sim.run()
        self.assertEqual(result, [None])
        self.assertEqual(t, 5)

    def test4_wait_returns_event_before_timeout(self):
        ''' wait(10) returns the event delivered before timeout. '''
        sim = self._make_sim()
        result = []
        async def my_coro():
            retval = await sim.wait(10)
            result.append(retval)
        coro = my_coro()
        sim.schedule(0, coro)
        sim.schedule_event(3, 'hello', coro)
        t, _ = sim.run()
        self.assertEqual(result, ['hello'])
        self.assertEqual(t, 3)

    def test5_first_timeout_cleared_when_gwait_returns_early(self):
        ''' When gwait() is woken early by an external event, the pending timeout
        entry is removed from the time queue.  A subsequent gwait() must schedule
        a fresh timeout relative to the current time — not fire on the stale one. '''
        sim = self._make_sim()
        result = []
        def my_gen():
            r1 = yield from sim.gwait(5)
            result.append(('first', sim.time, r1))
            r2 = yield from sim.gwait(5)
            result.append(('second', sim.time, r2))
        gen = my_gen()
        sim.schedule(0, gen)
        sim.schedule_event(2, 'hello', gen)  # wake first gwait at t=2 (before t=5)
        sim.run()
        # first gwait returns 'hello' at t=2; second times out at t=2+5=7, not t=5
        self.assertEqual(result[0], ('first', 2, 'hello'))
        self.assertEqual(result[1], ('second', 7, None))
        self.assertEqual(len(sim.time_queue), 0)


# ---------------------------------------------------------------------------
# SimTinyQueueMixin — factory method available on TinyLayer2 simulations
# ---------------------------------------------------------------------------

class TestSimTinyQueueMixin(unittest.TestCase):
    ''' Tests for SimTinyQueueMixin.tiny_queue() factory. '''

    def test1_tiny_queue_returns_tiny_queue_instance(self):
        ''' sim.tiny_queue() returns a TinyQueue bound to the sim. '''
        from dssim.components.tinycontainer import TinyQueue
        sim = DSSimulation(layer2=TinyLayer2)
        q = sim.tiny_queue()
        self.assertIsInstance(q, TinyQueue)
        self.assertIs(q.sim, sim)

    def test2_tiny_queue_passes_capacity(self):
        ''' Capacity keyword argument is forwarded to TinyQueue. '''
        sim = DSSimulation(layer2=TinyLayer2)
        q = sim.tiny_queue(capacity=3)
        self.assertEqual(q.capacity, 3)

    def test3_tiny_queue_wrong_sim_raises(self):
        ''' Passing a different sim instance raises ValueError. '''
        sim1 = DSSimulation(layer2=TinyLayer2)
        sim2 = DSSimulation(layer2=TinyLayer2)
        with self.assertRaises(ValueError):
            sim1.tiny_queue(sim=sim2)

    def test4_tiny_queue_not_available_without_tiny_layer2(self):
        ''' tiny_queue() is not present on a default (PubSubLayer2) simulation. '''
        sim = DSSimulation()
        self.assertFalse(hasattr(sim, 'tiny_queue'))


if __name__ == '__main__':
    unittest.main()
