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
Integration tests: DSSimulation run loop with real DSPub / DSSub /
DSCallback objects.  These tests verify that the core scheduling and dispatch
machinery works correctly when the "consumer" side is a real pubsub object
rather than a plain mock.
'''
import unittest
from unittest.mock import Mock
from dssim import DSSimulation, DSPub, DSCallback, DSProcess


# ---------------------------------------------------------------------------
# now_queue drain with real DSCallback consumers
# ---------------------------------------------------------------------------

class TestScheduleEventNow(unittest.TestCase):
    ''' Tests for the now_queue drain behaviour in sim.run() using real
    DSCallback objects instead of plain mocks. '''

    def test1_now_queue_drained_after_each_timed_event(self):
        ''' Events appended to now_queue during a timed callback are dispatched
        before the next timed event fires, and at the same sim.time. '''
        sim = DSSimulation()
        log = []

        def sink(event):
            log.append(('sink', sim.time, event))
            return True

        sink_cb = DSCallback(sink, sim=sim)

        def burst(event):
            log.append(('burst', sim.time))
            sim.signal('a', sink_cb)
            sim.signal('b', sink_cb)
            return True

        burst_cb = DSCallback(burst, sim=sim)
        sim.schedule_event(1, None, burst_cb)
        sim.schedule_event(2, None, burst_cb)
        sim.run()

        self.assertEqual(log[0], ('burst', 1))
        self.assertEqual(log[1], ('sink',  1, 'a'))
        self.assertEqual(log[2], ('sink',  1, 'b'))
        self.assertEqual(log[3], ('burst', 2))
        self.assertEqual(log[4], ('sink',  2, 'a'))
        self.assertEqual(log[5], ('sink',  2, 'b'))

    def test2_now_queue_fifo_order(self):
        ''' Multiple events scheduled via signal are consumed in
        FIFO order. '''
        sim = DSSimulation()
        received = []

        def sink(event):
            received.append(event)
            return True

        sink_cb = DSCallback(sink, sim=sim)

        def burst(event):
            for i in range(5):
                sim.signal(i, sink_cb)
            return True

        burst_cb = DSCallback(burst, sim=sim)
        sim.schedule_event(0, None, burst_cb)
        sim.run()
        self.assertEqual(received, [0, 1, 2, 3, 4])

    def test3_now_queue_empty_after_run(self):
        ''' now_queue is fully drained by run() — nothing left afterwards. '''
        sim = DSSimulation()

        def sink(event):
            return True

        sink_cb = DSCallback(sink, sim=sim)

        def burst(event):
            sim.signal('x', sink_cb)
            sim.signal('y', sink_cb)
            return True

        burst_cb = DSCallback(burst, sim=sim)
        sim.schedule_event(1, None, burst_cb)
        sim.run()
        self.assertEqual(len(sim.now_queue), 0)


# ---------------------------------------------------------------------------
# sim.run() dispatch with real DSCallback / DSPub consumers
# ---------------------------------------------------------------------------

class TestProducerConsumerIntegration(unittest.TestCase):
    ''' Tests that verify the sim.run() dispatch path using real pubsub
    objects — equivalent of the mock-consumer tests in test_simulation. '''

    def test1_schedule_event_to_dscallback_runs_in_sim(self):
        ''' schedule_event to a DSCallback is dispatched by sim.run(). '''
        sim = DSSimulation()
        received = []

        def handler(event):
            received.append((sim.time, event))
            return True

        cb = DSCallback(handler, sim=sim)
        sim.schedule_event(1, 'ev1', cb)
        sim.schedule_event(2, 'ev2', cb)
        sim.schedule_event(3, 'ev3', cb)
        retval = sim.run()
        self.assertEqual(retval, (3, 3))
        self.assertEqual(received, [(1, 'ev1'), (2, 'ev2'), (3, 'ev3')])

    def test2_schedule_event_to_dscallback_respects_time_limit(self):
        ''' sim.run(up_to) stops before delivering events after the limit. '''
        sim = DSSimulation()
        received = []

        def handler(event):
            received.append(event)
            return True

        cb = DSCallback(handler, sim=sim)
        sim.schedule_event(1, 'ev1', cb)
        sim.schedule_event(2, 'ev2', cb)
        sim.schedule_event(3, 'ev3', cb)
        sim.run(2.5)
        self.assertEqual(received, ['ev1', 'ev2'])
        self.assertEqual(len(sim.time_queue), 1)

    def test3_producer_signal_dispatched_to_dscallback_subscriber(self):
        ''' DSPub.signal() in the run loop reaches a DSCallback subscriber. '''
        sim = DSSimulation()
        received = []

        def trigger(event):
            producer.signal('hello')
            return True

        def sink(event):
            received.append(event)
            return True

        producer = DSPub(name='prod', sim=sim)
        sink_cb = DSCallback(sink, sim=sim)
        producer.add_subscriber(sink_cb, DSPub.Phase.CONSUME)

        trigger_cb = DSCallback(trigger, sim=sim)
        sim.schedule_event(1, None, trigger_cb)
        sim.run()

        self.assertEqual(received, ['hello'])

    def test4_generator_receives_timed_event_via_gwait(self):
        ''' A scheduled generator receives a direct schedule_event via gwait(). '''
        sim = DSSimulation()
        received = []

        def my_gen():
            event = yield from sim.gwait(cond=lambda _: True)
            received.append(event)

        proc = DSProcess(my_gen(), sim=sim).schedule(0)
        sim.schedule_event(1, 'hello', proc)
        sim.run()
        self.assertEqual(received, ['hello'])

    def test5_dsprocess_receives_events_from_dsproducer_via_run(self):
        ''' A DSProcess subscribed to a DSPub receives its events through
        sim.run(). '''
        sim = DSSimulation()
        received = []

        producer = DSPub(name='source', sim=sim)

        def consumer_gen():
            with sim.consume(producer):
                event = yield from sim.gwait(cond=lambda e: True)
                received.append(event)

        proc = DSProcess(consumer_gen(), sim=sim).schedule(0)

        def trigger(event):
            producer.signal('payload')
            return True

        trigger_cb = DSCallback(trigger, sim=sim)
        sim.schedule_event(1, None, trigger_cb)
        sim.run(5)

        self.assertEqual(received, ['payload'])

    def test6_producer_phase_pre_fires_before_consume(self):
        ''' PRE-phase subscriber is notified before the CONSUME-phase subscriber. '''
        sim = DSSimulation()
        order = []

        def pre_handler(event):
            order.append('pre')
            return True

        def consume_handler(event):
            order.append('consume')
            return True

        producer = DSPub(name='p', sim=sim)
        pre_cb = DSCallback(pre_handler, sim=sim)
        consume_cb = DSCallback(consume_handler, sim=sim)
        producer.add_subscriber(pre_cb, DSPub.Phase.PRE)
        producer.add_subscriber(consume_cb, DSPub.Phase.CONSUME)

        def trigger(event):
            producer.signal('ev')
            return True

        trigger_cb = DSCallback(trigger, sim=sim)
        sim.schedule_event(1, None, trigger_cb)
        sim.run()

        self.assertEqual(order, ['pre', 'consume'])


if __name__ == '__main__':
    unittest.main()
