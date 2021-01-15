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
Tests for lite timer/delay/limiter components.
'''
import unittest

from dssim import DSTrackableEvent
from dssim.base import DSComponent, ISubscriber, EventType
from dssim.simulation import DSSimulation, LiteLayer2
from dssim.lite.components.litetime import DSLiteDelay, DSLiteLimiter, DSLiteTimer


class _Sink(DSComponent, ISubscriber):
    supports_direct_send: bool = True

    def __init__(self, out, **kwargs):
        super().__init__(**kwargs)
        self.out = out

    def send(self, event: EventType):
        self.out.append((self.sim.time, event))
        return True


class TestSimLiteTimeMixin(unittest.TestCase):
    def test1_factories_return_lite_instances(self):
        sim = DSSimulation(layer2=LiteLayer2)
        t = sim.timer()
        d = sim.delay(2)
        l = sim.limiter(5)
        self.assertIsInstance(t, DSLiteTimer)
        self.assertIsInstance(d, DSLiteDelay)
        self.assertIsInstance(l, DSLiteLimiter)
        self.assertIs(t.sim, sim)
        self.assertIs(d.sim, sim)
        self.assertIs(l.sim, sim)
        # Kick scheduled internal processes once to avoid unawaited-coro warnings.
        sim.run(1e-9)

    def test2_wrong_sim_raises(self):
        sim1 = DSSimulation(layer2=LiteLayer2)
        sim2 = DSSimulation(layer2=LiteLayer2)
        with self.assertRaises(ValueError):
            sim1.timer(sim=sim2)
        with self.assertRaises(ValueError):
            sim1.delay(1, sim=sim2)
        with self.assertRaises(ValueError):
            sim1.limiter(1, sim=sim2)


class TestLiteDelay(unittest.TestCase):
    def test1_forwards_with_delay(self):
        sim = DSSimulation(layer2=LiteLayer2)
        d = sim.delay(3, name='d')
        out = []
        sink = _Sink(out, name='sink', sim=sim)
        d.tx.add_subscriber(sink)
        sim.schedule_event(1, 'hello', d.rx)
        sim.run(10)
        self.assertEqual(out, [(4, 'hello')])

    def test2_accepts_trackable_event_without_hop_tracking(self):
        sim = DSSimulation(layer2=LiteLayer2)
        d = sim.delay(1, name='d')
        out = []
        sink = _Sink(out, name='sink', sim=sim)
        d.tx.add_subscriber(sink)

        event = DSTrackableEvent('payload')
        sim.schedule_event(0, event, d.rx)
        sim.run(2)

        self.assertEqual(out, [(1, event)])
        self.assertEqual(event.publishers, [])


class TestLiteLimiter(unittest.TestCase):
    def test1_limits_rate(self):
        sim = DSSimulation(layer2=LiteLayer2)
        l = sim.limiter(2, name='l')  # one event per 0.5 sim-time units
        out = []
        sink = _Sink(out, name='sink', sim=sim)
        l.tx.add_subscriber(sink)

        for i in range(3):
            sim.signal(i, l.rx)
        sim.run(3)

        self.assertEqual([event for _, event in out], [0, 1, 2])
        self.assertEqual([t for t, _ in out], [0, 0.5, 1.0])


class TestLiteTimer(unittest.TestCase):
    def test1_periodic_ticks(self):
        sim = DSSimulation(layer2=LiteLayer2)
        t = sim.timer(period=1, repeats=3, name='timer')
        out = []
        sink = _Sink(out, name='sink', sim=sim)
        t.tx.add_subscriber(sink)
        t.start(repeats=3)
        sim.run(10)
        self.assertEqual(out, [(1, {'tick': 1}), (2, {'tick': 2}), (3, {'tick': 3})])

    def test2_pause_resume_keeps_remaining_time(self):
        sim = DSSimulation(layer2=LiteLayer2)
        t = sim.timer(period=1, repeats=1, name='timer')
        out = []
        sink = _Sink(out, name='sink', sim=sim)
        t.tx.add_subscriber(sink)

        def control():
            yield from sim.gwait(0.4)
            t.pause()
            yield from sim.gwait(1.0)
            t.resume()

        sim.schedule(0, control())
        t.start(repeats=1)
        sim.run(5)

        self.assertEqual(out, [(2.0, {'tick': 1})])


if __name__ == '__main__':
    unittest.main()
