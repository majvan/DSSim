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
from dssim.simulation import DSSimulation, DSProcess, DSFuture, DSAbortException
from dssim.cond import DSFilter as _f, DSFilterAggregated
from contextlib import contextmanager

class TestDSFilter(unittest.TestCase):

    def test0_init_value(self):
        sim = DSSimulation()
        fa = _f('a', sim=sim)
        self.assertTrue(fa.expression == _f.ONE_LINER)
        self.assertTrue(fa.positive)
        self.assertFalse(fa.reevaluate)
        self.assertFalse(fa.pulse)
        self.assertFalse(fa.forward_events)
        self.assertTrue(fa.cond == 'a')
        self.assertTrue(fa.get_future_eps() == {fa._finish_tx,})
        self.assertTrue(isinstance(fa, DSFuture))
        self.assertEqual(str(fa), "DSFilter(a)")

        fb = _f('b', sigtype=_f.SignalType.REEVALUATE, sim=sim)
        self.assertTrue(fb.expression == _f.ONE_LINER)
        self.assertTrue(fb.positive)
        self.assertTrue(fb.reevaluate)
        self.assertFalse(fb.pulse)
        self.assertFalse(fb.forward_events)
        self.assertTrue(fb.cond == 'b')
        self.assertTrue(fb.get_future_eps() == {fb._finish_tx,})
        self.assertTrue(isinstance(fb, DSFuture))
        self.assertEqual(str(fb), "DSFilter(b)")

        fc = _f('c', sigtype=_f.SignalType.PULSED, sim=sim)
        self.assertTrue(fc.expression == _f.ONE_LINER)
        self.assertTrue(fc.positive)
        self.assertTrue(fc.reevaluate)
        self.assertTrue(fc.pulse)
        self.assertFalse(fc.forward_events)
        self.assertTrue(fc.cond == 'c')
        self.assertTrue(fc.get_future_eps() == {fc._finish_tx,})
        self.assertTrue(isinstance(fc, DSFuture))
        self.assertEqual(str(fc), "DSFilter(c)")

        fna = -fa
        self.assertTrue(fna is not fa)  # a copy is created instead of extension
        self.assertTrue(fna.expression == _f.ONE_LINER)
        self.assertFalse(fna.positive)
        self.assertTrue(fna.pulse)
        self.assertTrue(fna.get_future_eps() == {fna._finish_tx,})
        self.assertTrue(isinstance(fna, DSFuture))
        self.assertEqual(str(fna), "-DSFilter(a)")

        with self.assertRaises(ValueError):
            -fna  # once a filter is negative (reseter), it cannot be negated again


    def test1_init_lambda(self):
        sim = DSSimulation()
        l = lambda e: 'A' in e
        fa = _f(l, sim=sim)
        self.assertTrue(fa.expression == _f.ONE_LINER)
        self.assertTrue(fa.positive)
        self.assertFalse(fa.reevaluate)
        self.assertFalse(fa.pulse)
        self.assertFalse(fa.forward_events)
        self.assertTrue(fa.cond == l)
        self.assertTrue(fa.get_future_eps() == {fa._finish_tx})
        self.assertTrue(isinstance(fa, DSFuture))
        self.assertEqual(str(fa), f"DSFilter({l})")

        l = lambda e: 'B' in e
        fb = _f(l, sigtype=_f.SignalType.REEVALUATE, sim=sim)
        self.assertTrue(fb.expression == _f.ONE_LINER)
        self.assertTrue(fb.positive)
        self.assertTrue(fb.reevaluate)
        self.assertFalse(fb.pulse)
        self.assertFalse(fb.forward_events)
        self.assertTrue(fb.cond == l)
        self.assertTrue(fb.get_future_eps() == {fb._finish_tx})
        self.assertTrue(isinstance(fb, DSFuture))
        self.assertEqual(str(fb), f"DSFilter({l})")

        l = lambda e: 'C' in e
        fc = _f(l, sigtype=_f.SignalType.PULSED, sim=sim)
        self.assertTrue(fc.expression == _f.ONE_LINER)
        self.assertTrue(fc.positive)
        self.assertTrue(fc.reevaluate)
        self.assertTrue(fc.pulse)
        self.assertFalse(fc.forward_events)
        self.assertTrue(fc.cond == l)
        self.assertTrue(fc.get_future_eps() == {fc._finish_tx})
        self.assertTrue(isinstance(fc, DSFuture))
        self.assertEqual(str(fc), f"DSFilter({l})")

        fna = -fa
        self.assertTrue(fna is not fa)  # a copy is created instead of extension
        self.assertTrue(fna.expression == _f.ONE_LINER)
        self.assertFalse(fna.positive)
        self.assertTrue(fna.pulse)
        self.assertTrue(fna.get_future_eps() == {fna._finish_tx,})
        self.assertTrue(isinstance(fna, DSFuture))
        self.assertEqual(str(fna), f"-DSFilter({fa.cond})")

        with self.assertRaises(ValueError):
            -fna  # once a filter is negative (reseter), it cannot be negated again


    def test2_init_future(self):
        sim = DSSimulation()
        fut = DSFuture(sim=sim)
        fa = _f(fut, sim=sim)
        self.assertTrue(fa.expression == _f.ONE_LINER)
        self.assertTrue(fa.positive)
        self.assertFalse(fa.reevaluate)
        self.assertFalse(fa.pulse)
        self.assertFalse(fa.forward_events)
        self.assertTrue(fa.cond == fut)
        self.assertTrue(fa.get_future_eps() == {fa._finish_tx, fut._finish_tx})
        self.assertTrue(isinstance(fa, DSFuture))
        self.assertEqual(str(fa), f"DSFilter({fut})")

        fut = DSFuture(sim=sim)
        fb = _f(fut, sigtype=_f.SignalType.REEVALUATE, sim=sim)
        self.assertTrue(fb.expression == _f.ONE_LINER)
        self.assertTrue(fb.positive)
        self.assertTrue(fb.reevaluate)
        self.assertFalse(fb.pulse)
        self.assertFalse(fb.forward_events)
        self.assertTrue(fb.cond == fut)
        self.assertTrue(fb.get_future_eps() == {fb._finish_tx, fut._finish_tx})
        self.assertTrue(isinstance(fb, DSFuture))
        self.assertEqual(str(fb), f"DSFilter({fut})")

        fut = DSFuture(sim=sim)
        fc = _f(fut, sigtype=_f.SignalType.PULSED, sim=sim)
        self.assertTrue(fc.expression == _f.ONE_LINER)
        self.assertTrue(fc.positive)
        self.assertTrue(fc.reevaluate)
        self.assertTrue(fc.pulse)
        self.assertFalse(fc.forward_events)
        self.assertTrue(fc.cond == fut)
        self.assertTrue(fc.get_future_eps() == {fc._finish_tx, fut._finish_tx})
        self.assertTrue(isinstance(fc, DSFuture))
        self.assertEqual(str(fc), f"DSFilter({fut})")

        fna = -fa
        self.assertTrue(fna is not fa)  # a copy is created instead of extension
        self.assertTrue(fna.expression == _f.ONE_LINER)
        self.assertFalse(fna.positive)
        self.assertTrue(fna.pulse)
        self.assertTrue(fna.get_future_eps() == {fna._finish_tx, fna.cond._finish_tx})
        self.assertTrue(isinstance(fna, DSFuture))
        self.assertEqual(str(fna), f"-DSFilter({fa.cond})")

        with self.assertRaises(ValueError):
            -fna  # once a filter is negative (reseter), it cannot be negated again


    def test3_init_gen(self):
        def gen():
            yield 'hi'

        sim = DSSimulation()
        g = gen()
        fa = _f(g, sim=sim)
        self.assertTrue(fa.expression == _f.ONE_LINER)
        self.assertTrue(fa.positive)
        self.assertFalse(fa.reevaluate)
        self.assertFalse(fa.pulse)
        self.assertTrue(fa.forward_events)
        self.assertTrue(fa.cond.generator == g)
        self.assertTrue(fa.get_future_eps() == {fa._finish_tx, fa.cond._finish_tx})
        self.assertTrue(isinstance(fa, DSFuture))
        self.assertEqual(str(fa), f"DSFilter({fa.cond})")

        g = gen()
        fb = _f(g, sigtype=_f.SignalType.REEVALUATE, sim=sim)
        self.assertTrue(fb.expression == _f.ONE_LINER)
        self.assertTrue(fb.positive)
        self.assertTrue(fb.reevaluate)
        self.assertFalse(fb.pulse)
        self.assertTrue(fb.forward_events)
        self.assertTrue(fb.cond.generator == g)
        self.assertTrue(fb.get_future_eps() == {fb._finish_tx, fb.cond._finish_tx})
        self.assertTrue(isinstance(fb, DSFuture))
        self.assertEqual(str(fb), f"DSFilter({fb.cond})")

        g = gen()
        fc = _f(g, sigtype=_f.SignalType.PULSED, sim=sim)
        self.assertTrue(fc.expression == _f.ONE_LINER)
        self.assertTrue(fc.positive)
        self.assertTrue(fc.reevaluate)
        self.assertTrue(fc.pulse)
        self.assertTrue(fc.forward_events)
        self.assertTrue(fc.cond.generator == g)
        self.assertTrue(fc.get_future_eps() == {fc._finish_tx, fc.cond._finish_tx})
        self.assertTrue(isinstance(fc, DSFuture))
        self.assertEqual(str(fc), f"DSFilter({fc.cond})")

        fna = -fa
        self.assertTrue(fna is not fa)  # a copy is created instead of extension
        self.assertTrue(fna.expression == _f.ONE_LINER)
        self.assertFalse(fna.positive)
        self.assertTrue(fna.pulse)
        self.assertTrue(fna.get_future_eps() == {fna._finish_tx, fna.cond._finish_tx})
        self.assertTrue(isinstance(fna, DSFuture))
        self.assertEqual(str(fna), f"-DSFilter({fa.cond})")

        with self.assertRaises(ValueError):
            -fna  # once a filter is negative (reseter), it cannot be negated again

        sim = DSSimulation()
        g = gen()
        self.assertTrue(len(sim.time_queue) == 0)
        fd = _f(g, sim=sim)
        self.assertTrue(len(sim.time_queue) == 1)  # the gen() was scheduled as a new process
        scheduled = sim.time_queue.pop()
        self.assertTrue(len(sim.time_queue) == 0)

    def test4_init_coro(self):
        async def coro():
            class Awaitable:
                def __await__(self):
                    yield 'hi'
            await Awaitable()

        sim = DSSimulation()
        g = coro()
        fa = _f(g, sim=sim)
        self.assertTrue(fa.expression == _f.ONE_LINER)
        self.assertTrue(fa.positive)
        self.assertFalse(fa.reevaluate)
        self.assertFalse(fa.pulse)
        self.assertTrue(fa.forward_events)
        self.assertTrue(fa.cond.generator == g)
        self.assertTrue(fa.get_future_eps() == {fa._finish_tx, fa.cond._finish_tx})
        self.assertTrue(isinstance(fa, DSFuture))
        self.assertEqual(str(fa), f"DSFilter({fa.cond})")

        g = coro()
        fb = _f(g, sigtype=_f.SignalType.REEVALUATE, sim=sim)
        self.assertTrue(fb.expression == _f.ONE_LINER)
        self.assertTrue(fb.positive)
        self.assertTrue(fb.reevaluate)
        self.assertFalse(fb.pulse)
        self.assertTrue(fb.forward_events)
        self.assertTrue(fb.cond.generator == g)
        self.assertTrue(fb.get_future_eps() == {fb._finish_tx, fb.cond._finish_tx})
        self.assertTrue(isinstance(fb, DSFuture))
        self.assertEqual(str(fb), f"DSFilter({fb.cond})")

        g = coro()
        fc = _f(g, sigtype=_f.SignalType.PULSED, sim=sim)
        self.assertTrue(fc.expression == _f.ONE_LINER)
        self.assertTrue(fc.positive)
        self.assertTrue(fc.reevaluate)
        self.assertTrue(fc.pulse)
        self.assertTrue(fc.forward_events)
        self.assertTrue(fc.cond.generator == g)
        self.assertTrue(fc.get_future_eps() == {fc._finish_tx, fc.cond._finish_tx})
        self.assertTrue(isinstance(fc, DSFuture))
        self.assertEqual(str(fc), f"DSFilter({fc.cond})")

        fna = -fa
        self.assertTrue(fna is not fa)  # a copy is created instead of extension
        self.assertTrue(fna.expression == _f.ONE_LINER)
        self.assertFalse(fna.positive)
        self.assertTrue(fna.pulse)
        self.assertTrue(fna.get_future_eps() == {fna._finish_tx, fna.cond._finish_tx})
        self.assertTrue(isinstance(fna, DSFuture))
        self.assertEqual(str(fna), f"-DSFilter({fa.cond})")

        with self.assertRaises(ValueError):
            -fna  # once a filter is negative (reseter), it cannot be negated again

        sim = DSSimulation()
        self.assertTrue(len(sim.time_queue) == 0)
        fd = _f(coro(), sim=sim)
        self.assertTrue(len(sim.time_queue) == 1)  # the coro() was scheduled as a new process
        scheduled = sim.time_queue.pop()
        self.assertTrue(len(sim.time_queue) == 0)

    def test5_init_process(self):
        def gen():
            yield 'hi'

        sim = DSSimulation()
        p = DSProcess(gen(), sim=sim)
        fa = _f(p, sim=sim)
        self.assertTrue(fa.expression == _f.ONE_LINER)
        self.assertTrue(fa.positive)
        self.assertFalse(fa.reevaluate)
        self.assertFalse(fa.pulse)
        self.assertFalse(fa.forward_events)  # process is like future and does not forward events unless explicitly requested
        self.assertTrue(fa.cond == p)
        self.assertTrue(fa.get_future_eps() == {fa._finish_tx, p._finish_tx})
        self.assertTrue(isinstance(fa, DSFuture))
        self.assertEqual(str(fa), f"DSFilter({p})")

        p = DSProcess(gen(), sim=sim)
        fb = _f(p, sigtype=_f.SignalType.REEVALUATE, sim=sim)
        self.assertTrue(fb.expression == _f.ONE_LINER)
        self.assertTrue(fb.positive)
        self.assertTrue(fb.reevaluate)
        self.assertFalse(fb.pulse)
        self.assertFalse(fb.forward_events)  # process is like future and does not forward events unless explicitly requested
        self.assertTrue(fb.cond == p)
        self.assertTrue(fb.get_future_eps() == {fb._finish_tx, p._finish_tx})
        self.assertTrue(isinstance(fb, DSFuture))
        self.assertEqual(str(fb), f"DSFilter({p})")

        p = DSProcess(gen(), sim=sim)
        fc = _f(p, sigtype=_f.SignalType.PULSED, sim=sim)
        self.assertTrue(fc.expression == _f.ONE_LINER)
        self.assertTrue(fc.positive)
        self.assertTrue(fc.reevaluate)
        self.assertTrue(fc.pulse)
        self.assertFalse(fc.forward_events)  # process is like future and does not forward events unless explicitly requested
        self.assertTrue(fc.cond == p)
        self.assertTrue(fc.get_future_eps() == {fc._finish_tx, p._finish_tx})
        self.assertTrue(isinstance(fc, DSFuture))
        self.assertEqual(str(fc), f"DSFilter({p})")

        fna = -fa
        self.assertTrue(fna is not fa)  # a copy is created instead of extension
        self.assertTrue(fna.expression == _f.ONE_LINER)
        self.assertFalse(fna.positive)
        self.assertTrue(fna.pulse)
        self.assertTrue(fna.get_future_eps() == {fna._finish_tx, fna.cond._finish_tx})
        self.assertTrue(isinstance(fna, DSFuture))
        self.assertEqual(str(fna), f"-DSFilter({fa.cond})")

        with self.assertRaises(ValueError):
            -fna  # once a filter is negative (reseter), it cannot be negated again

        sim = DSSimulation()
        self.assertTrue(len(sim.time_queue) == 0)
        p = DSProcess(gen(), sim=sim)
        self.assertTrue(len(sim.time_queue) == 0)
        fd = _f(p, sim=sim)
        self.assertTrue(len(sim.time_queue) == 1)  # the process was scheduled
        scheduled = sim.time_queue.pop()
        self.assertTrue(scheduled == (0, (p, None)))
        self.assertTrue(len(sim.time_queue) == 0)

        p = DSProcess(gen(), sim=sim).schedule(0)
        self.assertTrue(len(sim.time_queue) == 1)  # the process is scheduled explicitly
        fe = _f(p, sim=sim)
        self.assertTrue(len(sim.time_queue) == 1)
        scheduled = sim.time_queue.pop()
        self.assertTrue(scheduled == (0, (p, None)))
        self.assertTrue(len(sim.time_queue) == 0)


    def test6_feeding_value(self):
        sim = DSSimulation()
        fa = _f('a', sim=sim)
        self.assertTrue(fa.signaled == False)
        self.assertTrue(fa.finished() == False)
        retval = fa('0')
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        retval = fa('a')
        self.assertTrue((retval, fa.signaled) == (True, True))
        self.assertTrue(fa.finished() == True)
        self.assertTrue(fa.value == 'a')
        retval = fa('b')
        self.assertTrue((retval, fa.signaled) == (True, True))
        self.assertTrue(fa.finished() == True)
        self.assertTrue(fa.value == 'a')

    def test7_feeding_lambda(self):
        sim = DSSimulation()
        fa = _f(lambda e: 'A' in e, sim=sim)
        self.assertTrue(fa.signaled == False)
        self.assertTrue(fa.finished() == False)
        retval = fa('0')
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        retval = fa('Hello')
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        retval = fa('Ahoy')
        self.assertTrue((retval, fa.signaled) == (True, True))
        self.assertTrue(fa.finished() == True)
        self.assertTrue(fa.value == 'Ahoy')
        retval = fa('Ciao')
        self.assertTrue((retval, fa.signaled) == (True, True))
        self.assertTrue(fa.finished() == True)
        self.assertTrue(fa.value == 'Ahoy')

    def test8_feeding_future(self):
        sim = DSSimulation()
        fut = DSFuture(sim=sim)
        fa = _f(fut, sim=sim)
        self.assertTrue(fa.signaled == False)
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fut.finished() == False)
        retval = fa('Hi')
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fut.finished() == False)
        fut.finish('Ahoy')
        retval = fa(fut)  # When waiting for a future in a condition, a process registers the future notification which is then sent to the process
        self.assertTrue((retval, fa.signaled) == (True, True))
        self.assertTrue(fa.finished() == True)
        self.assertTrue(fut.finished() == True)
        retval = fa('Ciao')
        self.assertTrue((retval, fa.signaled) == (True, True))
        self.assertTrue(fa.finished() == True)
        self.assertTrue(fut.finished() == True)

    def test9_feeding_gen(self):
        def gen():
            yield 'First'
            return 'Return'

        sim = DSSimulation()
        fa = _f(gen(), sim=sim)
        self.assertTrue(fa.signaled == False)
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fa.cond.finished() == False)
        retval = fa('Hi')
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fa.cond.finished() == False)
        retval = fa('Ahoy')
        self.assertTrue((retval, fa.signaled) == (True, True))
        self.assertTrue(fa.finished() == True)
        self.assertTrue(fa.cond.finished() == True)
        retval = fa('Ciao')
        self.assertTrue((retval, fa.signaled) == (True, True))
        self.assertTrue(fa.finished() == True)
        self.assertTrue(fa.cond.finished() == True)

    def test10_feeding_coro(self):
        async def coro():
            class Awaitable:
                def __await__(self):
                    yield 'First'
                    return 'Return'
            await Awaitable()
        
        sim = DSSimulation()
        fa = _f(coro(), sim=sim)
        self.assertTrue(fa.signaled == False)
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fa.cond.finished() == False)
        retval = fa('Hi')
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fa.cond.finished() == False)
        retval = fa('Ahoy')
        self.assertTrue((retval, fa.signaled) == (True, True))
        self.assertTrue(fa.finished() == True)
        self.assertTrue(fa.cond.finished() == True)
        retval = fa('Ciao')
        self.assertTrue((retval, fa.signaled) == (True, True))
        self.assertTrue(fa.finished() == True)
        self.assertTrue(fa.cond.finished() == True)

    def test11_feeding_process(self):
        def gen():
            yield 'First'
            return 'Return'
        
        sim = DSSimulation()
        p = DSProcess(gen(), sim=sim)
        fa = _f(p, sim=sim)
        self.assertTrue(fa.signaled == False)
        self.assertTrue(fa.finished() == False)
        retval = fa('Hi')  # This will NOT forward the event to the process
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(p.finished() == False)
        retval = fa('Ahoy')  # The event is not forwarded => no finish
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(p.finished() == False)
        retval = fa('Ciao')  # Last check
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(p.finished() == False)
        # Try again, but now the process will be iterating
        retval = sim.send(p, 'Hi')
        self.assertTrue((retval, fa.signaled) == ('First', False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(p.finished() == False)
        retval = sim.send(p, 'Ahoy')
        self.assertTrue((retval, fa.signaled) == ('Return', False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(p.finished() == True)
        retval = fa(p)  # When waiting for a future in a condition, a process registers the future notification which is then sent to the process
        self.assertTrue((retval, fa.signaled) == (True, True))
        self.assertTrue(fa.finished() == True)
        self.assertTrue(p.finished() == True)
        retval = fa('Ciao')  # Last check
        self.assertTrue((retval, fa.signaled) == (True, True))
        self.assertTrue(fa.finished() == True)
        self.assertTrue(p.finished() == True)

    def test12_feeding_value_reevaluate(self):
        sim = DSSimulation()
        fa = _f('a', sigtype=_f.SignalType.REEVALUATE, sim=sim)
        self.assertTrue(fa.signaled == False)
        self.assertTrue(fa.finished() == False)
        retval = fa('0')
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        retval = fa('a')
        self.assertTrue((retval, fa.signaled) == (True, True))
        self.assertTrue(fa.finished() == True)
        self.assertTrue(fa.value == 'a')
        retval = fa('b')
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fa.value == 'a')

    def test13_feeding_lambda_reevaluate(self):
        sim = DSSimulation()
        fa = _f(lambda e: 'A' in e, sigtype=_f.SignalType.REEVALUATE, sim=sim)
        self.assertTrue(fa.signaled == False)
        self.assertTrue(fa.finished() == False)
        retval = fa('0')
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        retval = fa('Hello')
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        retval = fa('Ahoy')
        self.assertTrue((retval, fa.signaled) == (True, True))
        self.assertTrue(fa.finished() == True)
        self.assertTrue(fa.value == 'Ahoy')
        retval = fa('Ciao')
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fa.value == 'Ahoy')

    def test14_feeding_future_reevaluate(self):
        sim = DSSimulation()
        fut = DSFuture(sim=sim)
        fa = _f(fut, sigtype=_f.SignalType.REEVALUATE, sim=sim)
        self.assertTrue(fa.signaled == False)
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fut.finished() == False)
        retval = fa('Hi')
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fut.finished() == False)
        fut.finish('Ahoy')
        retval = fa(fut)  # When waiting for a future in a condition, a process registers the future notification which is then sent to the process
        self.assertTrue((retval, fa.signaled) == (True, True))
        self.assertTrue(fa.finished() == True)
        self.assertTrue(fut.finished() == True)
        retval = fa('Ciao')
        self.assertTrue((retval, fa.signaled) == (True, True))
        self.assertTrue(fa.finished() == True)
        self.assertTrue(fut.finished() == True)

    def test15_feeding_gen_reevaluate(self):
        def gen():
            yield 'First'
            return 'Return'

        sim = DSSimulation()
        fa = _f(gen(), sigtype=_f.SignalType.REEVALUATE, sim=sim)
        self.assertTrue(fa.signaled == False)
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fa.cond.finished() == False)
        retval = fa('Hi')
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fa.cond.finished() == False)
        retval = fa('Ahoy')
        self.assertTrue((retval, fa.signaled) == (True, True))
        self.assertTrue(fa.finished() == True)
        self.assertTrue(fa.cond.finished() == True)
        retval = fa('Ciao')
        self.assertTrue((retval, fa.signaled) == (True, True))
        self.assertTrue(fa.finished() == True)
        self.assertTrue(fa.cond.finished() == True)

    def test16_feeding_coro_reevaluate(self):
        async def coro():
            class Awaitable:
                def __await__(self):
                    yield 'First'
                    return 'Return'
            await Awaitable()
        
        sim = DSSimulation()
        fa = _f(coro(), sigtype=_f.SignalType.REEVALUATE, sim=sim)
        self.assertTrue(fa.signaled == False)
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fa.cond.finished() == False)
        retval = fa('Hi')
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fa.cond.finished() == False)
        retval = fa('Ahoy')
        self.assertTrue((retval, fa.signaled) == (True, True))
        self.assertTrue(fa.finished() == True)
        self.assertTrue(fa.cond.finished() == True)
        retval = fa('Ciao')
        self.assertTrue((retval, fa.signaled) == (True, True))
        self.assertTrue(fa.finished() == True)
        self.assertTrue(fa.cond.finished() == True)

    def test17_feeding_process_reevaluate(self):
        def gen():
            yield 'First'
            return 'Return'
        
        sim = DSSimulation()
        p = DSProcess(gen(), sigtype=_f.SignalType.REEVALUATE, sim=sim)
        fa = _f(p, sim=sim)
        self.assertTrue(fa.signaled == False)
        self.assertTrue(fa.finished() == False)
        retval = fa('Hi')  # This will NOT forward the event to the process
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(p.finished() == False)
        retval = fa('Ahoy')  # The event is not forwarded => no finish
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(p.finished() == False)
        retval = fa('Ciao')  # Last check
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(p.finished() == False)
        # Try again, but now the process will be iterating
        retval = sim.send(p, 'Hi')
        self.assertTrue((retval, fa.signaled) == ('First', False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(p.finished() == False)
        retval = sim.send(p, 'Ahoy')
        self.assertTrue((retval, fa.signaled) == ('Return', False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(p.finished() == True)
        retval = fa(p)  # When waiting for a future in a condition, a process registers the future notification which is then sent to the process
        self.assertTrue((retval, fa.signaled) == (True, True))
        self.assertTrue(fa.finished() == True)
        self.assertTrue(p.finished() == True)
        retval = fa('Ciao')  # Last check
        self.assertTrue((retval, fa.signaled) == (True, True))
        self.assertTrue(fa.finished() == True)
        self.assertTrue(p.finished() == True)


    def test18_feeding_value_pulsed(self):
        sim = DSSimulation()
        fa = _f('a', sigtype=_f.SignalType.PULSED, sim=sim)
        self.assertTrue(fa.signaled == False)
        self.assertTrue(fa.finished() == False)
        retval = fa('0')
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        retval = fa('a')
        self.assertTrue((retval, fa.signaled) == (True, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fa.value == 'a')
        retval = fa('b')
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fa.value == 'a')

    def test19_feeding_lambda_pulsed(self):
        sim = DSSimulation()
        fa = _f(lambda e: 'A' in e, sigtype=_f.SignalType.PULSED, sim=sim)
        self.assertTrue(fa.signaled == False)
        self.assertTrue(fa.finished() == False)
        retval = fa('0')
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        retval = fa('Hello')
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        retval = fa('Ahoy')
        self.assertTrue((retval, fa.signaled) == (True, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fa.value == 'Ahoy')
        retval = fa('Ciao')
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fa.value == 'Ahoy')

    def test20_feeding_future_pulsed(self):
        sim = DSSimulation()
        fut = DSFuture(sim=sim)
        fa = _f(fut, sigtype=_f.SignalType.PULSED, sim=sim)
        self.assertTrue(fa.signaled == False)
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fut.finished() == False)
        retval = fa('Hi')
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fut.finished() == False)
        fut.finish('Ahoy')
        retval = fa(fut)  # When waiting for a future in a condition, a process registers the future notification which is then sent to the process
        self.assertTrue((retval, fa.signaled) == (True, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fut.finished() == True)
        retval = fa('Ciao')
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fut.finished() == True)

    def test21_feeding_gen_pulsed(self):
        def gen():
            yield 'First'
            return 'Return'

        sim = DSSimulation()
        fa = _f(gen(), sigtype=_f.SignalType.PULSED, sim=sim)
        self.assertTrue(fa.signaled == False)
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fa.cond.finished() == False)
        retval = fa('Hi')
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fa.cond.finished() == False)
        retval = fa('Ahoy')
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fa.cond.finished() == True)
        retval = fa(fa.cond)  # When waiting for a condition, typically this event is sent to the process after gen is finished
        self.assertTrue((retval, fa.signaled) == (True, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fa.cond.finished() == True)
        retval = fa('Ciao')
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fa.cond.finished() == True)

    def test22_feeding_coro_pulsed(self):
        async def coro():
            class Awaitable:
                def __await__(self):
                    yield 'First'
                    return 'Return'
            await Awaitable()
        
        sim = DSSimulation()
        fa = _f(coro(), sigtype=_f.SignalType.PULSED, sim=sim)
        self.assertTrue(fa.signaled == False)
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fa.cond.finished() == False)
        retval = fa('Hi')
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fa.cond.finished() == False)
        retval = fa('Ahoy')
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fa.cond.finished() == True)
        retval = fa(fa.cond)  # When waiting for a condition, typically this event is sent to the process after gen is finished
        self.assertTrue((retval, fa.signaled) == (True, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fa.cond.finished() == True)
        retval = fa('Ciao')
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(fa.cond.finished() == True)

    def test23_feeding_process_pulsed(self):
        def gen():
            yield 'First'
            return 'Return'
        
        sim = DSSimulation()
        p = DSProcess(gen(), sigtype=_f.SignalType.PULSED, sim=sim)
        fa = _f(p, sim=sim)
        self.assertTrue(fa.signaled == False)
        self.assertTrue(fa.finished() == False)
        retval = fa('Hi')  # This will NOT forward the event to the process
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(p.finished() == False)
        retval = fa('Ahoy')  # The event is not forwarded => no finish
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(p.finished() == False)
        retval = fa('Ciao')  # Last check
        self.assertTrue((retval, fa.signaled) == (False, False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(p.finished() == False)
        # Try again, but now the process will be iterating
        retval = sim.send(p, 'Hi')
        self.assertTrue((retval, fa.signaled) == ('First', False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(p.finished() == False)
        retval = sim.send(p, 'Ahoy')
        self.assertTrue((retval, fa.signaled) == ('Return', False))
        self.assertTrue(fa.finished() == False)
        self.assertTrue(p.finished() == True)
        retval = fa(p)  # When waiting for a future in a condition, a process registers the future notification which is then sent to the process
        self.assertTrue((retval, fa.signaled) == (True, True))
        self.assertTrue(fa.finished() == True)
        self.assertTrue(p.finished() == True)
        retval = fa('Ciao')  # Last check
        self.assertTrue((retval, fa.signaled) == (True, True))
        self.assertTrue(fa.finished() == True)
        self.assertTrue(p.finished() == True)


    def test24_cond_gwait(self):
        pass

    def test25_cond_wait(self):
        pass


    '''
    The second part is for agregated 
    '''

class TestDSFilterAggregated(unittest.TestCase):

    def test0_build(self):
        sim = DSSimulation()
        fa, fb, fc, fd = _f('a', sim=sim), _f('b', sim=sim), _f('c', sim=sim), _f('d', sim=sim)
        c = fa | fb
        self.assertTrue(isinstance(c, DSFuture))
        self.assertTrue(c.expression == any)
        self.assertTrue(c.positive)
        self.assertTrue(c.get_future_eps() == {fa._finish_tx, fb._finish_tx,})
        self.assertEqual(repr(c), "<class 'dssim.cond.DSFilterAggregated'>0")
        self.assertEqual(str(c), "(DSFilter(a) | DSFilter(b))")
        self.assertTrue((c.setters, c.resetters) == ([fa, fb], []))
        d = fa | fb | fc
        self.assertTrue(isinstance(d, DSFuture))
        self.assertTrue(d.expression == any)
        self.assertTrue(d.positive)
        self.assertTrue(d.get_future_eps() == {fa._finish_tx, fb._finish_tx, fc._finish_tx,})
        self.assertEqual(repr(d), "<class 'dssim.cond.DSFilterAggregated'>1")
        self.assertEqual(str(d), "(DSFilter(a) | DSFilter(b) | DSFilter(c))")
        self.assertTrue((d.setters, d.resetters) == ([fa, fb, fc], []))

        c = fa & fb
        self.assertTrue(isinstance(c, DSFuture))
        self.assertTrue(c.expression == all)
        self.assertTrue(c.positive)
        self.assertTrue(c.get_future_eps() == {fa._finish_tx, fb._finish_tx,})
        self.assertEqual(repr(c), "<class 'dssim.cond.DSFilterAggregated'>2")
        self.assertEqual(str(c), "(DSFilter(a) & DSFilter(b))")
        self.assertTrue((c.setters, c.resetters) == ([fa, fb], []))
        d = fa & fb & fc
        self.assertTrue(isinstance(d, DSFuture))
        self.assertTrue(d.expression == all)
        self.assertTrue(d.positive)
        self.assertTrue(d.get_future_eps() == {fa._finish_tx, fb._finish_tx, fc._finish_tx,})
        self.assertEqual(repr(d), "<class 'dssim.cond.DSFilterAggregated'>3")
        self.assertEqual(str(d), "(DSFilter(a) & DSFilter(b) & DSFilter(c))")
        self.assertTrue((d.setters, d.resetters) == ([fa, fb, fc], []))

        # Test priorities
        c = fa & fb | fc
        self.assertTrue(c.expression == any)
        self.assertTrue(c.positive)
        self.assertTrue(c.get_future_eps() == {fa._finish_tx, fb._finish_tx, fc._finish_tx,})
        self.assertEqual(str(c), "((DSFilter(a) & DSFilter(b)) | DSFilter(c))")
        self.assertTrue((len(c.setters), len(c.resetters)) == (2, 0))
        c = fa | fb & fc
        self.assertTrue(c.expression == any)
        self.assertTrue(c.positive)
        self.assertTrue(d.get_future_eps() == {fa._finish_tx, fb._finish_tx, fc._finish_tx,})
        self.assertEqual(str(c), "(DSFilter(a) | (DSFilter(b) & DSFilter(c)))")
        self.assertTrue((len(c.setters), len(c.resetters)) == (2, 0))

        # Test heterogenous combinations
        c = fa | fb & fc
        self.assertTrue(c.expression == any)
        self.assertTrue(c.positive)
        self.assertTrue(c.get_future_eps() == {fa._finish_tx, fb._finish_tx, fc._finish_tx,})
        self.assertEqual(str(c), "(DSFilter(a) | (DSFilter(b) & DSFilter(c)))")
        self.assertTrue((len(c.setters), len(c.resetters)) == (2, 0))
        d = c | fd
        self.assertTrue(d is c)  # the filter was just updated with a new expression
        self.assertTrue(d.expression == any)
        self.assertTrue(d.positive)
        self.assertTrue(d.get_future_eps() == {fa._finish_tx, fb._finish_tx, fc._finish_tx, fd._finish_tx})
        self.assertEqual(str(d), "(DSFilter(a) | (DSFilter(b) & DSFilter(c)) | DSFilter(d))")
        self.assertTrue((len(d.setters), len(d.resetters)) == (3, 0))
        c = fa | fb & fc
        d = fd | c
        self.assertTrue(d is c)  # the filter was just updated with a new expression
        self.assertTrue(d.expression == any)
        self.assertTrue(d.positive)
        self.assertTrue(d.get_future_eps() == {fa._finish_tx, fb._finish_tx, fc._finish_tx, fd._finish_tx})
        self.assertEqual(str(d), "(DSFilter(a) | (DSFilter(b) & DSFilter(c)) | DSFilter(d))")
        self.assertTrue((len(d.setters), len(d.resetters)) == (3, 0))

        c = fa & (fb | fc)
        self.assertTrue(c.expression == all)
        self.assertTrue(c.positive)
        self.assertTrue(c.get_future_eps() == {fa._finish_tx, fb._finish_tx, fc._finish_tx,})
        self.assertEqual(str(c), "(DSFilter(a) & (DSFilter(b) | DSFilter(c)))")
        self.assertTrue((len(c.setters), len(c.resetters)) == (2, 0))
        d = c & fd
        self.assertTrue(d is c)  # the filter was just updated with a new expression
        self.assertTrue(d.expression == all)
        self.assertTrue(d.positive)
        self.assertTrue(d.get_future_eps() == {fa._finish_tx, fb._finish_tx, fc._finish_tx, fd._finish_tx})
        self.assertEqual(str(d), "(DSFilter(a) & (DSFilter(b) | DSFilter(c)) & DSFilter(d))")
        self.assertTrue((len(d.setters), len(d.resetters)) == (3, 0))
        c = fa & (fb | fc)
        d = fd & c
        self.assertTrue(d is c)  # the filter was just updated with a new expression
        self.assertTrue(d.expression == all)
        self.assertTrue(d.positive)
        self.assertTrue(d.get_future_eps() == {fa._finish_tx, fb._finish_tx, fc._finish_tx, fd._finish_tx})
        self.assertEqual(str(d), "(DSFilter(a) & (DSFilter(b) | DSFilter(c)) & DSFilter(d))")
        self.assertTrue((len(d.setters), len(d.resetters)) == (3, 0))

        c = -(fa & fb)
        self.assertTrue(c.expression == all)
        self.assertTrue(not c.positive)
        self.assertTrue(c.get_future_eps() == {fa._finish_tx, fb._finish_tx})
        self.assertEqual(str(c), "-(DSFilter(a) & DSFilter(b))")
        self.assertTrue((len(c.setters), len(c.resetters)) == (2, 0))

    def test1_build_with_reseters(self):
        sim = DSSimulation()
        fa, fb, fc, fd = _f('a', sim=sim), _f('b', sim=sim), _f('c', sim=sim), _f('d', sim=sim)
        fna, fnb = -fa, -fb

        c = fna | fb
        self.assertTrue(isinstance(c, DSFuture))
        self.assertTrue(c.expression == any)
        self.assertTrue(c.get_future_eps() == {fna._finish_tx, fb._finish_tx})
        self.assertEqual(str(c), "(DSFilter(b) | -DSFilter(a))")
        self.assertTrue((c.setters, c.resetters) == ([fb], [fna]))
        d = fna | fb | fc
        self.assertTrue(isinstance(d, DSFuture))
        self.assertTrue(d.expression == any)
        self.assertTrue(d.get_future_eps() == {fna._finish_tx, fb._finish_tx, fc._finish_tx})
        self.assertEqual(str(d), "(DSFilter(b) | DSFilter(c) | -DSFilter(a))")
        self.assertTrue((d.setters, d.resetters) == ([fb, fc], [fna]))
        d = fna | fc | fd | fnb
        self.assertTrue(isinstance(d, DSFuture))
        self.assertTrue(d.expression == any)
        self.assertTrue(d.get_future_eps() == {fna._finish_tx, fc._finish_tx, fd._finish_tx, fnb._finish_tx})
        self.assertEqual(str(d), "(DSFilter(c) | DSFilter(d) | -DSFilter(a) | -DSFilter(b))")
        self.assertTrue((d.setters, d.resetters) == ([fc, fd], [fna, fnb]))

        c = fna & fb
        self.assertTrue(isinstance(c, DSFuture))
        self.assertTrue(c.expression == all)
        self.assertTrue(c.get_future_eps() == {fna._finish_tx, fb._finish_tx,})
        self.assertEqual(str(c), "(DSFilter(b) & -DSFilter(a))")
        self.assertTrue((c.setters, c.resetters) == ([fb], [fna]))
        d = fna & fb & fc
        self.assertTrue(isinstance(d, DSFuture))
        self.assertTrue(d.expression == all)
        self.assertTrue(d.get_future_eps() == {fna._finish_tx, fb._finish_tx, fc._finish_tx})
        self.assertEqual(str(d), "(DSFilter(b) & DSFilter(c) & -DSFilter(a))")
        self.assertTrue((d.setters, d.resetters) == ([fb, fc], [fna]))
        d = fna & fc & fd & fnb
        self.assertTrue(isinstance(d, DSFuture))
        self.assertTrue(d.expression == all)
        self.assertTrue(d.get_future_eps() == {fna._finish_tx, fc._finish_tx, fd._finish_tx, fnb._finish_tx})
        self.assertEqual(str(d), "(DSFilter(c) & DSFilter(d) & -DSFilter(a) & -DSFilter(b))")
        self.assertTrue((d.setters, d.resetters) == ([fc, fd], [fna, fnb]))

        c = -(fa & fb) & fc
        self.assertTrue(c.expression == all)
        self.assertTrue(c.positive)
        self.assertTrue(c.get_future_eps() == {fa._finish_tx, fb._finish_tx, fc._finish_tx})
        self.assertEqual(str(c), "(DSFilter(c) & -(DSFilter(a) & DSFilter(b)))")
        self.assertTrue((len(c.setters), len(c.resetters)) == (1, 1))