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
Tests for pubsub time components (Delay, Limiter, IntegralLimiter, Timer).
'''
import unittest

from dssim import DSSimulation
from dssim.pubsub.components.time import Delay, IntegralLimiter, Limiter, Timer


class TestSimTimeMixin(unittest.TestCase):
    def test1_factories_return_instances(self):
        sim = DSSimulation()
        delay = sim.delay(2)
        limiter = sim.limiter(5)
        ilimiter = sim.integral_limiter(throughput=5)
        timer = sim.timer(period=1)
        self.assertIsInstance(delay, Delay)
        self.assertIsInstance(limiter, Limiter)
        self.assertIsInstance(ilimiter, IntegralLimiter)
        self.assertIsInstance(timer, Timer)
        self.assertIs(delay.sim, sim)
        self.assertIs(limiter.sim, sim)
        self.assertIs(ilimiter.sim, sim)
        self.assertIs(timer.sim, sim)
        # Kick scheduled internal processes once to avoid unawaited-coro warnings.
        sim.run(1e-9)

    def test2_wrong_sim_raises(self):
        sim1 = DSSimulation()
        sim2 = DSSimulation(single_instance=False)
        with self.assertRaises(ValueError):
            sim1.delay(1, sim=sim2)
        with self.assertRaises(ValueError):
            sim1.limiter(1, sim=sim2)
        with self.assertRaises(ValueError):
            sim1.integral_limiter(throughput=1, sim=sim2)
        with self.assertRaises(ValueError):
            sim1.timer(sim=sim2)


class TestDelay(unittest.TestCase):
    def test1_forwards_with_delay(self):
        sim = DSSimulation()
        delay = Delay(3, name='delay', sim=sim)
        out = []
        sink = sim.callback(lambda e: out.append((sim.time, e)), name='sink')
        delay.tx.add_subscriber(sink)
        sim.schedule_event(1, 'hello', delay.rx)
        sim.run(10)
        self.assertEqual(out, [(4, 'hello')])


class TestLimiter(unittest.TestCase):
    def test1_limits_rate(self):
        sim = DSSimulation()
        limiter = Limiter(2, name='limiter', sim=sim)  # one event per 0.5 time units
        out = []
        sink = sim.callback(lambda e: out.append((sim.time, e)), name='sink')
        limiter.tx.add_subscriber(sink)
        for i in range(3):
            sim.signal(i, limiter.rx)
        sim.run(3)
        self.assertEqual([event for _, event in out], [0, 1, 2])
        self.assertEqual([t for t, _ in out], [0, 0.5, 1.0])


class TestIntegralLimiter(unittest.TestCase):
    def test1_non_accumulated_forwards_individual_events(self):
        sim = DSSimulation()
        limiter = IntegralLimiter(throughput=4, report_frequency=2, accumulated_report=False, name='il', sim=sim)
        out = []
        sink = sim.callback(lambda e: out.append((sim.time, e)), name='sink')
        limiter.tx.add_subscriber(sink)
        for i in range(5):
            sim.signal(i, limiter.rx)
        sim.run(2)
        self.assertEqual(out, [
            (0.5, 0), (0.5, 1),
            (1.0, 2), (1.0, 3),
            (1.5, 4),
        ])

    def test2_accumulated_reports_counts(self):
        sim = DSSimulation()
        limiter = IntegralLimiter(throughput=4, report_frequency=2, accumulated_report=True, name='il', sim=sim)
        out = []
        sink = sim.callback(lambda e: out.append((sim.time, e)), name='sink')
        limiter.tx.add_subscriber(sink)
        for i in range(5):
            sim.signal(i, limiter.rx)
        sim.run(1.6)
        self.assertEqual(out, [
            (0.5, {'num': 2}),
            (1.0, {'num': 2}),
            (1.5, {'num': 2}),
        ])


class TestTimer(unittest.TestCase):
    def test1_periodic_ticks(self):
        sim = DSSimulation()
        timer = Timer(period=1, repeats=3, name='timer', sim=sim)
        out = []
        sink = sim.callback(lambda e: out.append((sim.time, e)), name='sink')
        timer.tx.add_subscriber(sink)
        timer.start(repeats=3)
        sim.run(10)
        self.assertEqual(out, [(1, {'tick': 1}), (2, {'tick': 2}), (3, {'tick': 3})])

    def test2_pause_resume_keeps_remaining_time(self):
        sim = DSSimulation()
        timer = Timer(period=1, repeats=1, name='timer', sim=sim)
        out = []
        sink = sim.callback(lambda e: out.append((sim.time, e)), name='sink')
        timer.tx.add_subscriber(sink)

        def control():
            yield from sim.gwait(0.4)
            timer.pause()
            yield from sim.gwait(1.0)
            timer.resume()

        sim.schedule(0, control())
        timer.start(repeats=1)
        sim.run(5)
        self.assertEqual(out, [(2.0, {'tick': 1})])


if __name__ == '__main__':
    unittest.main()
