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
Tests for LiteResource / LitePriorityResource (LiteLayer2-only components).
'''
import unittest

from dssim.simulation import DSSimulation, LiteLayer2
from dssim.lite.components.literesource import LiteResource, LitePriorityResource


def _make(amount=0, capacity=float('inf')):
    sim = DSSimulation(layer2=LiteLayer2)
    r = LiteResource(amount=amount, capacity=capacity, sim=sim)
    return sim, r


def _make_prio(amount=0, capacity=float('inf'), preemptive=False):
    sim = DSSimulation(layer2=LiteLayer2)
    r = LitePriorityResource(amount=amount, capacity=capacity, preemptive=preemptive, sim=sim)
    return sim, r


class TestLiteResourceNowait(unittest.TestCase):
    def test1_put_get_nowait(self):
        _, r = _make(amount=1, capacity=3)
        self.assertEqual(r.put_nowait(), 1)
        self.assertEqual(r.amount, 2)
        self.assertEqual(r.get_nowait(), 1)
        self.assertEqual(r.amount, 1)

    def test2_nowait_respects_capacity_and_amount(self):
        _, r = _make(amount=1, capacity=1)
        self.assertEqual(r.put_nowait(), 0)  # full
        self.assertEqual(r.get_n_nowait(2), 0)  # insufficient amount


class TestLiteResourceBlockingGenerators(unittest.TestCase):
    def test1_gget_blocks_and_wakes_on_put(self):
        sim, r = _make(amount=0, capacity=1)
        out = []

        def consumer():
            got = yield from r.gget()
            out.append((sim.time, got))

        def producer():
            yield from sim.gwait(5)
            out.append((sim.time, r.put_nowait()))

        sim.schedule(0, consumer())
        sim.schedule(0, producer())
        sim.run(20)
        self.assertEqual(out, [(5, 1), (5, 1)])

    def test2_gput_blocks_when_full_then_wakes_after_get(self):
        sim, r = _make(amount=1, capacity=1)
        out = []

        def producer():
            put = yield from r.gput(timeout=10)
            out.append((sim.time, put))

        def consumer():
            yield from sim.gwait(3)
            out.append((sim.time, (yield from r.gget())))

        sim.schedule(0, producer())
        sim.schedule(0, consumer())
        sim.run(20)
        self.assertEqual(out, [(3, 1), (3, 1)])

    def test3_gget_timeout_returns_zero(self):
        sim, r = _make(amount=0, capacity=1)
        out = []

        def consumer():
            got = yield from r.gget(timeout=4)
            out.append((sim.time, got))

        sim.schedule(0, consumer())
        sim.run(20)
        self.assertEqual(out, [(4, 0)])

    def test4_gput_timeout_returns_zero(self):
        sim, r = _make(amount=1, capacity=1)
        out = []

        def producer():
            put = yield from r.gput(timeout=4)
            out.append((sim.time, put))

        sim.schedule(0, producer())
        sim.run(20)
        self.assertEqual(out, [(4, 0)])


class TestLiteResourceAsync(unittest.TestCase):
    def test1_async_get_waits_for_put(self):
        sim, r = _make(amount=0, capacity=1)
        out = []

        async def consumer():
            got = await r.get(timeout=10)
            out.append((sim.time, got))

        def producer():
            yield from sim.gwait(2)
            r.put_nowait()

        sim.schedule(0, consumer())
        sim.schedule(0, producer())
        sim.run(20)
        self.assertEqual(out, [(2, 1)])


class TestLitePriorityResource(unittest.TestCase):
    def test1_priority_serves_lower_numeric_first(self):
        sim, r = _make_prio(amount=0, capacity=2)
        out = []

        def waiter(label, prio):
            got = yield from r.gget(priority=prio)
            out.append((label, got, sim.time))

        def feeder():
            yield from sim.gwait(1)
            r.put_n_nowait(2)

        sim.schedule(0, waiter('low-prio', 5))
        sim.schedule(0, waiter('high-prio', 1))
        sim.schedule(0, feeder())
        sim.run(20)
        self.assertEqual(out[0][:2], ('high-prio', 1))
        self.assertEqual(out[1][:2], ('low-prio', 1))
        self.assertEqual(out[0][2], 1)
        self.assertEqual(out[1][2], 1)

    def test2_same_priority_is_fifo(self):
        sim, r = _make_prio(amount=0, capacity=2)
        out = []

        def waiter(label):
            got = yield from r.gget(priority=2)
            out.append((label, got, sim.time))

        def feeder():
            yield from sim.gwait(1)
            r.put_n_nowait(2)

        sim.schedule(0, waiter('a'))
        sim.schedule(0, waiter('b'))
        sim.schedule(0, feeder())
        sim.run(20)
        self.assertEqual([x[0] for x in out], ['a', 'b'])

    def test3_preemptive_interrupts_lower_priority_holder(self):
        sim, r = _make_prio(amount=1, capacity=1)
        out = []

        def low():
            got = yield from r.gget(priority=5, preempt=True)
            self.assertEqual(got, 1)
            out.append(('low_start', sim.time))
            try:
                yield from sim.gwait(10)
                out.append(('low_no_preempt', sim.time))
                r.put_nowait()
            except LitePriorityResource.Preempted as exc:
                out.append(('low_preempted', sim.time, exc.amount))
                got2 = yield from r.gget(priority=5, preempt=False)
                self.assertEqual(got2, 1)
                out.append(('low_resumed', sim.time))
                yield from sim.gwait(2)
                r.put_nowait()
                out.append(('low_done', sim.time))

        def high():
            yield from sim.gwait(3)
            got = yield from r.gget(priority=1, preempt=True)
            self.assertEqual(got, 1)
            out.append(('high_start', sim.time))
            yield from sim.gwait(2)
            r.put_nowait()
            out.append(('high_done', sim.time))

        sim.schedule(0, low())
        sim.schedule(0, high())
        sim.run(20)
        self.assertEqual(out, [
            ('low_start', 0),
            ('high_start', 3),
            ('low_preempted', 3, 1),
            ('high_done', 5),
            ('low_resumed', 5),
            ('low_done', 7),
        ])
        self.assertEqual(r.amount, 1)

    def test4_preempt_false_waits_without_interrupt(self):
        sim, r = _make_prio(amount=1, capacity=1)
        out = []

        def low():
            got = yield from r.gget(priority=5, preempt=True)
            self.assertEqual(got, 1)
            out.append(('low_start', sim.time))
            yield from sim.gwait(4)
            r.put_nowait()
            out.append(('low_done', sim.time))

        def high():
            yield from sim.gwait(1)
            got = yield from r.gget(priority=1, preempt=False)
            self.assertEqual(got, 1)
            out.append(('high_start', sim.time))
            r.put_nowait()
            out.append(('high_done', sim.time))

        sim.schedule(0, low())
        sim.schedule(0, high())
        sim.run(20)
        self.assertEqual(out, [
            ('low_start', 0),
            ('low_done', 4),
            ('high_start', 4),
            ('high_done', 4),
        ])
        self.assertEqual(r.amount, 1)


class TestSimLiteResourceMixin(unittest.TestCase):
    def test1_resource_factory(self):
        sim = DSSimulation(layer2=LiteLayer2)
        r = sim.resource(amount=2, capacity=3)
        self.assertIsInstance(r, LiteResource)
        self.assertEqual(r.amount, 2)
        self.assertEqual(r.capacity, 3)
        self.assertIs(r.sim, sim)

    def test2_priority_resource_factory(self):
        sim = DSSimulation(layer2=LiteLayer2)
        r = sim.priority_resource(amount=1, capacity=4)
        self.assertIsInstance(r, LitePriorityResource)
        self.assertIs(r.sim, sim)

    def test3_wrong_sim_raises(self):
        sim1 = DSSimulation(layer2=LiteLayer2)
        sim2 = DSSimulation(layer2=LiteLayer2)
        with self.assertRaises(ValueError):
            sim1.resource(sim=sim2)
        with self.assertRaises(ValueError):
            sim1.priority_resource(sim=sim2)

    def test4_old_lite_factory_names_not_available(self):
        sim = DSSimulation(layer2=LiteLayer2)
        self.assertFalse(hasattr(sim, 'lite_resource'))
        self.assertFalse(hasattr(sim, 'lite_priority_resource'))


if __name__ == '__main__':
    unittest.main()
