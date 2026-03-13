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
Tests for dssim.parity.simpy lightweight adapter.
'''
import unittest

from dssim.parity import simpy


class TestSimpyParityProcess(unittest.TestCase):
    def test_timeout_process_and_run_until_process(self):
        env = simpy.Environment()
        out = []

        def worker():
            out.append(('start', env.now))
            value = yield env.timeout(5, value='tick')
            out.append(('after_timeout', env.now, value))
            return 7

        proc = env.process(worker())
        env.run(until=proc)

        self.assertTrue(proc.triggered)
        self.assertTrue(proc.ok)
        self.assertEqual(proc.value, 7)
        self.assertEqual(out, [('start', 0), ('after_timeout', 5, 'tick')])

    def test_any_of_and_all_of(self):
        env = simpy.Environment()
        out = []

        def worker():
            e1 = env.timeout(5, value='a')
            e2 = env.timeout(7, value='b')
            got_any = yield env.any_of([e1, e2])
            out.append(('any', env.now, got_any[e1]))
            got_all = yield env.all_of([e1, e2])
            out.append(('all', env.now, (got_all[e1], got_all[e2])))

        env.process(worker())
        env.run(until=20)

        self.assertEqual(out, [
            ('any', 5, 'a'),
            ('all', 7, ('a', 'b')),
        ])


class TestSimpyParityResource(unittest.TestCase):
    def test_preemptive_resource_interrupt_cause(self):
        env = simpy.Environment()
        machine = simpy.PreemptiveResource(env, capacity=1)
        out = []

        def low():
            with machine.request(priority=5, preempt=True) as req:
                yield req
                out.append(('low_start', env.now))
                try:
                    yield env.timeout(10)
                except simpy.Interrupt as interrupt:
                    cause = interrupt.cause
                    out.append((
                        'low_preempted',
                        env.now,
                        isinstance(cause, simpy.Preempted),
                        cause.resource is machine,
                    ))

        def high():
            yield env.timeout(3)
            with machine.request(priority=1, preempt=True) as req:
                yield req
                out.append(('high_start', env.now))
                yield env.timeout(2)
                out.append(('high_done', env.now))

        env.process(low())
        env.process(high())
        env.run(until=20)

        self.assertEqual(out, [
            ('low_start', 0),
            ('low_preempted', 3, True, True),
            ('high_start', 3),
            ('high_done', 5),
        ])


class TestSimpyParityStore(unittest.TestCase):
    def test_store_put_get(self):
        env = simpy.Environment()
        store = simpy.Store(env)
        out = []

        def producer():
            yield env.timeout(2)
            yield store.put('x')
            yield env.timeout(1)
            yield store.put('y')

        def consumer():
            first = yield store.get()
            out.append(('first', env.now, first))
            second = yield store.get()
            out.append(('second', env.now, second))

        env.process(producer())
        env.process(consumer())
        env.run(until=20)

        self.assertEqual(out, [
            ('first', 2, 'x'),
            ('second', 3, 'y'),
        ])


if __name__ == '__main__':
    unittest.main()
