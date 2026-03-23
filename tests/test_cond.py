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
"""Consolidated condition/circuit tests for endpoint-sinking strategy.

This file keeps legacy-applicable coverage from the original test_cond.py and
includes the new-strategy coverage in the same consolidated suite.
"""

import unittest

from dssim import DSFuture, DSProcess, DSSimulation
from dssim.pubsub.base import TestObject, AlwaysTrue
from dssim.pubsub.cond import DSCircuit, DSFilter


_f = DSFilter


class TestDSFilterApplicableLegacy(unittest.TestCase):
    def test1_init_value(self):
        sim = DSSimulation()
        fa = _f("a", sim=sim)
        self.assertEqual(fa.expression, _f.ONE_LINER)
        self.assertTrue(fa.positive)
        self.assertFalse(fa.reevaluate)
        self.assertFalse(fa.pulse)
        self.assertFalse(fa.forward_events)
        self.assertEqual(fa.cond, "a")
        self.assertEqual(fa.get_eps(), {fa._finish_tx})
        self.assertIsInstance(fa, DSFuture)
        self.assertEqual(str(fa), "DSFilter(a)")

        fb = _f("b", sigtype=_f.SignalType.REEVALUATE, sim=sim)
        self.assertTrue(fb.reevaluate)
        self.assertFalse(fb.pulse)

        fc = _f("c", sigtype=_f.SignalType.PULSED, sim=sim)
        self.assertTrue(fc.reevaluate)
        self.assertTrue(fc.pulse)

        fna = -fa
        self.assertIsNot(fna, fa)
        self.assertEqual(fna.expression, _f.ONE_LINER)
        self.assertFalse(fna.positive)
        self.assertTrue(fna.pulse)
        self.assertEqual(fna.get_eps(), {fna._finish_tx})
        self.assertIsInstance(fna, DSFuture)
        self.assertEqual(str(fna), "-DSFilter(a)")

        with self.assertRaises(ValueError):
            -fna

    def test2_init_lambda(self):
        sim = DSSimulation()
        l = lambda e: "A" in e
        fa = _f(l, sim=sim)
        self.assertEqual(fa.expression, _f.ONE_LINER)
        self.assertTrue(fa.positive)
        self.assertFalse(fa.reevaluate)
        self.assertFalse(fa.pulse)
        self.assertFalse(fa.forward_events)
        self.assertIs(fa.cond, l)
        self.assertEqual(fa.get_eps(), {fa._finish_tx})
        self.assertIsInstance(fa, DSFuture)

    def test3_init_future(self):
        sim = DSSimulation()
        fut = DSFuture(sim=sim)
        fa = _f(fut, sim=sim)
        self.assertEqual(fa.expression, _f.ONE_LINER)
        self.assertTrue(fa.positive)
        self.assertFalse(fa.reevaluate)
        self.assertFalse(fa.pulse)
        self.assertFalse(fa.forward_events)
        self.assertIs(fa.cond, fut)
        self.assertEqual(fa.get_eps(), {fa._finish_tx})
        self.assertIsInstance(fa, DSFuture)

    def test4_init_gen_wraps_process_and_does_not_forward(self):
        def gen():
            yield "hi"

        sim = DSSimulation()
        self.assertEqual(sim.time_queue.event_count(), 0)
        fa = _f(gen(), sim=sim)
        self.assertFalse(fa.forward_events)
        self.assertIsInstance(fa.cond, DSProcess)
        self.assertEqual(sim.time_queue.event_count(), 1)

        # Filter receive does not forward into wrapped process.
        self.assertFalse(fa("payload"))
        self.assertFalse(fa.cond.started())

    def test5_init_coro_wraps_process_and_does_not_forward(self):
        async def coro():
            class Awaitable:
                def __await__(self):
                    yield "hi"

            await Awaitable()

        sim = DSSimulation()
        self.assertEqual(sim.time_queue.event_count(), 0)
        fa = _f(coro(), sim=sim)
        self.assertFalse(fa.forward_events)
        self.assertIsInstance(fa.cond, DSProcess)
        self.assertEqual(sim.time_queue.event_count(), 1)
        self.assertFalse(fa("payload"))

        # Start the wrapped process to avoid dangling unstarted coroutine warnings.
        sim.run(1)

    def test6_init_process(self):
        def gen():
            yield "hi"

        sim = DSSimulation()
        p = DSProcess(gen(), sim=sim)
        fa = _f(p, sim=sim)
        self.assertEqual(fa.expression, _f.ONE_LINER)
        self.assertTrue(fa.positive)
        self.assertFalse(fa.reevaluate)
        self.assertFalse(fa.pulse)
        self.assertFalse(fa.forward_events)
        self.assertIs(fa.cond, p)
        self.assertEqual(fa.get_eps(), {fa._finish_tx})
        self.assertIsInstance(fa, DSFuture)

    def test7_feeding_value(self):
        sim = DSSimulation()
        fa = _f("a", sim=sim)
        self.assertFalse(fa.signaled)
        self.assertFalse(fa.finished())

        self.assertFalse(fa("0"))
        self.assertFalse(fa.signaled)

        self.assertTrue(fa("a"))
        self.assertTrue(fa.signaled)
        self.assertTrue(fa.finished())
        self.assertEqual(fa.value, "a")

        self.assertTrue(fa("b"))
        self.assertTrue(fa.signaled)
        self.assertEqual(fa.value, "a")

    def test8_feeding_lambda(self):
        sim = DSSimulation()
        fa = _f(lambda e: "A" in e, sim=sim)
        self.assertFalse(fa("0"))
        self.assertFalse(fa("Hello"))
        self.assertTrue(fa("Ahoy"))
        self.assertTrue(fa.signaled)
        self.assertEqual(fa.value, "Ahoy")
        self.assertTrue(fa("Ciao"))
        self.assertEqual(fa.value, "Ahoy")

    def test9_feeding_future(self):
        sim = DSSimulation()
        fut = DSFuture(sim=sim)
        fa = _f(fut, sim=sim)
        self.assertFalse(fa("Hi"))
        self.assertFalse(fa.finished())

        fut.finish("Ahoy")
        self.assertTrue(fa(fut))
        self.assertTrue(fa.finished())
        self.assertTrue(fut.finished())
        self.assertEqual(fa.value, "Ahoy")

        self.assertTrue(fa("Ciao"))
        self.assertEqual(fa.value, "Ahoy")

    def test10_wrapped_generator_is_not_event_forwarded(self):
        def gen():
            event = yield "First"
            return event

        sim = DSSimulation()
        fa = _f(gen(), sim=sim)
        p = fa.cond

        self.assertFalse(p.started())
        self.assertFalse(fa("boot"))
        self.assertFalse(p.started())
        self.assertFalse(p.finished())

    def test11_wrapped_coroutine_is_not_event_forwarded(self):
        async def coro():
            class Awaitable:
                def __await__(self):
                    event = yield "First"
                    return event

            return await Awaitable()

        sim = DSSimulation()
        fa = _f(coro(), sim=sim)
        p = fa.cond

        self.assertFalse(p.started())
        self.assertFalse(fa("boot"))
        self.assertFalse(p.started())
        self.assertFalse(p.finished())
        sim.run(1)

    def test12_wrapped_process_is_not_event_forwarded(self):
        def gen():
            event = yield "First"
            return event

        sim = DSSimulation()
        p = DSProcess(gen(), sim=sim)
        fa = _f(p, sim=sim)

        self.assertFalse(fa("Hi"))
        self.assertFalse(p.started())
        self.assertFalse(p.finished())

        p.send(None)
        p.get_cond().push(lambda e: True)
        self.assertEqual(sim.send_object(p, "Ahoy"), "Ahoy")
        self.assertTrue(p.finished())

        self.assertTrue(fa(p))
        self.assertTrue(fa.finished())

    def test13_feeding_value_reevaluate(self):
        sim = DSSimulation()
        fa = _f("a", sigtype=_f.SignalType.REEVALUATE, sim=sim)
        self.assertFalse(fa("0"))
        self.assertFalse(fa.signaled)

        self.assertTrue(fa("a"))
        self.assertTrue(fa.signaled)
        self.assertEqual(fa.value, "a")

        self.assertFalse(fa("b"))
        self.assertFalse(fa.signaled)
        self.assertEqual(fa.value, "a")

    def test13b_send_reevaluate_toggles_state(self):
        sim = DSSimulation()
        fa = _f(lambda e: e == "UP", sigtype=_f.SignalType.REEVALUATE, sim=sim)
        tx = sim.publisher(name="tx")
        tx.add_subscriber(fa, tx.Phase.PRE)

        sim.signal("UP", tx)
        sim.run(1)
        self.assertTrue(fa.signaled)
        self.assertEqual(fa.value, "UP")

        sim.signal("DOWN", tx)
        sim.run(2)
        self.assertFalse(fa.signaled)
        self.assertEqual(fa.value, "UP")

    def test13c_send_wakes_waiters_via_finish_tx(self):
        sim = DSSimulation()
        fa = _f(lambda e: e == "UP", sigtype=_f.SignalType.REEVALUATE, sim=sim)
        out = []

        async def waiter():
            t0 = sim.time
            got = await fa.wait(10)
            out.append((sim.time - t0, got, fa.signaled))

        async def sender():
            await sim.wait(3)
            fa.send("UP")

        sim.schedule(0, waiter())
        sim.schedule(0, sender())
        sim.run(20)
        self.assertEqual(out, [(3, "UP", True)])

    def test13d_check_testobject_is_non_destructive_for_reevaluate(self):
        sim = DSSimulation()
        fa = _f(lambda e: e == "UP", sigtype=_f.SignalType.REEVALUATE, sim=sim)

        signaled, value = fa.check(TestObject)
        self.assertFalse(signaled)
        self.assertIsNone(value)
        self.assertFalse(fa.signaled)

        fa.check("UP")
        self.assertTrue(fa.signaled)
        signaled, value = fa.check(TestObject)
        self.assertTrue(signaled)
        self.assertEqual(value, "UP")
        self.assertTrue(fa.signaled)

    def test13f_send_testobject_does_not_wake_waiters(self):
        sim = DSSimulation()
        fa = _f(lambda e: e == "UP", sigtype=_f.SignalType.REEVALUATE, sim=sim)
        out = []

        async def waiter():
            t0 = sim.time
            got = await fa.wait(2)
            out.append((sim.time - t0, got, fa.signaled))

        async def sender():
            await sim.wait(1)
            fa.send(TestObject)

        sim.schedule(0, waiter())
        sim.schedule(0, sender())
        sim.run(10)
        self.assertEqual(out, [(2, None, False)])

    def test13g_circuit_wait_survives_async_filter_finish_event(self):
        sim = DSSimulation()
        f_link = _f(lambda e: e == "UP", sigtype=_f.SignalType.REEVALUATE, sim=sim)
        f_credits = _f(lambda e: e == "CREDITS", sim=sim)
        circuit = DSCircuit(all, [f_link, f_credits], sim=sim)
        out = []

        async def waiter():
            t0 = sim.time
            got = await circuit.wait(5)
            out.append((sim.time - t0, got, f_link.signaled, f_credits.signaled))

        async def feeder():
            await sim.wait(1)
            f_link.send("UP")
            await sim.wait(1)
            f_credits.finish("ok")

        sim.schedule(0, waiter())
        sim.schedule(0, feeder())
        sim.run(20)

        self.assertEqual(len(out), 1)
        self.assertEqual(out[0][0], 2)
        self.assertEqual(out[0][1], {f_link: "UP", f_credits: "ok"})
        self.assertTrue(out[0][2])
        self.assertTrue(out[0][3])

    def test13h_pulsed_send_wakes_waiters_immediately(self):
        sim = DSSimulation()
        fa = _f(lambda e: e == "UP", sigtype=_f.SignalType.PULSED, sim=sim)
        out = []

        async def waiter():
            t0 = sim.time
            got = await fa.wait(5)
            out.append((sim.time - t0, got, fa.signaled))

        async def sender():
            await sim.wait(1)
            fa.send("UP")

        sim.schedule(0, waiter())
        sim.schedule(0, sender())
        sim.run(20)
        self.assertEqual(out, [(1, "UP", False)])

    def test14_feeding_lambda_reevaluate(self):
        sim = DSSimulation()
        fa = _f(lambda e: "A" in e, sigtype=_f.SignalType.REEVALUATE, sim=sim)
        self.assertFalse(fa("0"))
        self.assertFalse(fa("Hello"))
        self.assertTrue(fa("Ahoy"))
        self.assertTrue(fa.signaled)
        self.assertEqual(fa.value, "Ahoy")
        self.assertFalse(fa("Ciao"))
        self.assertFalse(fa.signaled)
        self.assertEqual(fa.value, "Ahoy")

    def test15_feeding_future_reevaluate(self):
        sim = DSSimulation()
        fut = DSFuture(sim=sim)
        fa = _f(fut, sigtype=_f.SignalType.REEVALUATE, sim=sim)

        self.assertFalse(fa("Hi"))
        self.assertFalse(fa.finished())

        fut.finish("Ahoy")
        self.assertTrue(fa(fut))
        self.assertTrue(fa.finished())
        self.assertTrue(fut.finished())

        # reevaluate + finished future remains signaled
        self.assertTrue(fa("Ciao"))
        self.assertTrue(fa.finished())

    def test19_feeding_value_pulsed(self):
        sim = DSSimulation()
        fa = _f("a", sigtype=_f.SignalType.PULSED, sim=sim)

        self.assertFalse(fa("0"))
        self.assertFalse(fa.signaled)
        self.assertFalse(fa.finished())

        self.assertTrue(fa("a"))
        self.assertFalse(fa.signaled)
        self.assertFalse(fa.finished())
        self.assertEqual(fa.value, "a")

        self.assertFalse(fa("b"))
        self.assertFalse(fa.signaled)

    def test20_feeding_lambda_pulsed(self):
        sim = DSSimulation()
        fa = _f(lambda e: "A" in e, sigtype=_f.SignalType.PULSED, sim=sim)

        self.assertFalse(fa("0"))
        self.assertFalse(fa("Hello"))
        self.assertTrue(fa("Ahoy"))
        self.assertFalse(fa.signaled)
        self.assertEqual(fa.value, "Ahoy")

        self.assertFalse(fa("Ciao"))
        self.assertFalse(fa.signaled)
        self.assertEqual(fa.value, "Ahoy")

    def test21_feeding_future_pulsed(self):
        sim = DSSimulation()
        fut = DSFuture(sim=sim)
        fa = _f(fut, sigtype=_f.SignalType.PULSED, sim=sim)

        self.assertFalse(fa("Hi"))
        fut.finish("Ahoy")
        self.assertTrue(fa(fut))
        self.assertFalse(fa.signaled)
        self.assertFalse(fa.finished())
        self.assertTrue(fut.finished())

        self.assertFalse(fa("Ciao"))
        self.assertFalse(fa.signaled)

    def test25_cond_gwait_waits_without_precheck(self):
        sim = DSSimulation()
        flt = _f("ready", sim=sim)
        flt.check("ready")
        out = []

        def waiter():
            t0 = sim.time
            got = yield from flt.gwait(5)
            out.append((sim.time - t0, got))

        sim.schedule(0, waiter())
        sim.run(10)

        # wait()/gwait() intentionally do not precheck signaled state.
        self.assertEqual(out, [(5, "ready")])

    def test26_cond_wait_waits_without_precheck(self):
        sim = DSSimulation()
        flt = _f("ready", sim=sim)
        flt.check("ready")
        out = []

        async def waiter():
            t0 = sim.time
            got = await flt.wait(5)
            out.append((sim.time - t0, got))

        sim.schedule(0, waiter())
        sim.run(10)

        # wait()/gwait() intentionally do not precheck signaled state.
        self.assertEqual(out, [(5, "ready")])

    def test27_precheck_probe_evaluates_unsignaled_callable(self):
        sim = DSSimulation()
        flt = _f(lambda _e: True, sim=sim)
        signaled, value = flt.check(TestObject)
        self.assertTrue(signaled)
        self.assertIs(value, TestObject)
        self.assertTrue(flt.signaled)

    def test28_cond_check_and_gwait_fastpath_when_signaled(self):
        sim = DSSimulation()
        flt = _f("ready", sim=sim)
        flt.check("ready")
        out = []

        def waiter():
            t0 = sim.time
            got = yield from flt.check_and_gwait(5)
            out.append((sim.time - t0, got))

        sim.schedule(0, waiter())
        sim.run(10)
        self.assertEqual(out, [(0, "ready")])

    def test29_cond_check_and_wait_fastpath_when_signaled(self):
        sim = DSSimulation()
        flt = _f("ready", sim=sim)
        flt.check("ready")
        out = []

        async def waiter():
            t0 = sim.time
            got = await flt.check_and_wait(5)
            out.append((sim.time - t0, got))

        sim.schedule(0, waiter())
        sim.run(10)
        self.assertEqual(out, [(0, "ready")])


class TestDSCircuitApplicableLegacy(unittest.TestCase):
    def test1_build(self):
        sim = DSSimulation()
        fa, fb, fc, fd = _f("a", sim=sim), _f("b", sim=sim), _f("c", sim=sim), _f("d", sim=sim)

        c = fa | fb
        self.assertIsInstance(c, DSFuture)
        self.assertEqual(c.expression, any)
        self.assertTrue(c.positive)
        self.assertEqual(c.get_eps(), {c._finish_tx})
        self.assertEqual(str(c), "(DSFilter(a) | DSFilter(b))")
        self.assertEqual((c.setters, c.resetters), ([fa, fb], []))

        d = fa | fb | fc
        self.assertEqual(d.expression, any)
        self.assertTrue(d.positive)
        self.assertEqual(d.get_eps(), {d._finish_tx})
        self.assertEqual(str(d), "(DSFilter(a) | DSFilter(b) | DSFilter(c))")
        self.assertEqual((d.setters, d.resetters), ([fa, fb, fc], []))

        c = fa & fb
        self.assertEqual(c.expression, all)
        self.assertTrue(c.positive)
        self.assertEqual(c.get_eps(), {c._finish_tx})
        self.assertEqual(str(c), "(DSFilter(a) & DSFilter(b))")
        self.assertEqual((c.setters, c.resetters), ([fa, fb], []))

        d = fa & fb & fc
        self.assertEqual(d.expression, all)
        self.assertTrue(d.positive)
        self.assertEqual(d.get_eps(), {d._finish_tx})
        self.assertEqual(str(d), "(DSFilter(a) & DSFilter(b) & DSFilter(c))")
        self.assertEqual((d.setters, d.resetters), ([fa, fb, fc], []))

        # priorities
        c = fa & fb | fc
        self.assertEqual(c.expression, any)
        self.assertTrue(c.positive)
        self.assertEqual(str(c), "((DSFilter(a) & DSFilter(b)) | DSFilter(c))")

        c = fa | fb & fc
        self.assertEqual(c.expression, any)
        self.assertTrue(c.positive)
        self.assertEqual(str(c), "(DSFilter(a) | (DSFilter(b) & DSFilter(c)))")

        # heterogeneous flattening
        c = fa | fb & fc
        d = c | fd
        self.assertIs(d, c)
        self.assertEqual(d.expression, any)
        self.assertTrue(d.positive)
        self.assertEqual(str(d), "(DSFilter(a) | (DSFilter(b) & DSFilter(c)) | DSFilter(d))")

        c = fa & (fb | fc)
        d = c & fd
        self.assertIs(d, c)
        self.assertEqual(d.expression, all)
        self.assertTrue(d.positive)
        self.assertEqual(str(d), "(DSFilter(a) & (DSFilter(b) | DSFilter(c)) & DSFilter(d))")

        c = -(fa & fb)
        self.assertEqual(c.expression, all)
        self.assertFalse(c.positive)
        self.assertEqual(str(c), "-(DSFilter(a) & DSFilter(b))")
        self.assertEqual((len(c.setters), len(c.resetters)), (2, 0))

    def test2_build_with_reseters(self):
        sim = DSSimulation()
        fa, fb, fc, fd = _f("a", sim=sim), _f("b", sim=sim), _f("c", sim=sim), _f("d", sim=sim)
        fna, fnb = -fa, -fb

        c = fna | fb
        self.assertIsInstance(c, DSFuture)
        self.assertEqual(c.expression, any)
        self.assertEqual(c.get_eps(), {c._finish_tx})
        self.assertEqual(str(c), "(DSFilter(b) | -DSFilter(a))")
        self.assertEqual((c.setters, c.resetters), ([fb], [fna]))

        d = fna | fb | fc
        self.assertEqual(d.expression, any)
        self.assertEqual(str(d), "(DSFilter(b) | DSFilter(c) | -DSFilter(a))")
        self.assertEqual((d.setters, d.resetters), ([fb, fc], [fna]))

        d = fna | fc | fd | fnb
        self.assertEqual(d.expression, any)
        self.assertEqual(str(d), "(DSFilter(c) | DSFilter(d) | -DSFilter(a) | -DSFilter(b))")
        self.assertEqual((d.setters, d.resetters), ([fc, fd], [fna, fnb]))

        c = fna & fb
        self.assertEqual(c.expression, all)
        self.assertEqual(str(c), "(DSFilter(b) & -DSFilter(a))")
        self.assertEqual((c.setters, c.resetters), ([fb], [fna]))

        d = fna & fb & fc
        self.assertEqual(d.expression, all)
        self.assertEqual(str(d), "(DSFilter(b) & DSFilter(c) & -DSFilter(a))")
        self.assertEqual((d.setters, d.resetters), ([fb, fc], [fna]))

        d = fna & fc & fd & fnb
        self.assertEqual(d.expression, all)
        self.assertEqual(str(d), "(DSFilter(c) & DSFilter(d) & -DSFilter(a) & -DSFilter(b))")
        self.assertEqual((d.setters, d.resetters), ([fc, fd], [fna, fnb]))

        c = -(fa & fb) & fc
        self.assertEqual(c.expression, all)
        self.assertTrue(c.positive)
        self.assertEqual(str(c), "(DSFilter(c) & -(DSFilter(a) & DSFilter(b)))")
        self.assertEqual((len(c.setters), len(c.resetters)), (1, 1))

    def test3_precheck_probe_recomputes_reevaluate_circuit(self):
        sim = DSSimulation()
        f_link = _f(lambda e: e == "UP", sigtype=_f.SignalType.REEVALUATE, sim=sim)
        f_credits = _f(lambda e: isinstance(e, int) and e > 0, sigtype=_f.SignalType.REEVALUATE, sim=sim)
        c = f_link & f_credits

        f_link("UP")
        f_credits(1)
        self.assertFalse(c.signaled)

        signaled, value = c.check(TestObject)
        self.assertTrue(signaled)
        self.assertEqual(value, {f_link: "UP", f_credits: 1})
        self.assertTrue(c.signaled)

    def test4_check_and_wait_can_shortcut_from_existing_signaled_state(self):
        sim = DSSimulation()
        f_a = _f(lambda e: isinstance(e, dict) and bool(e.get("a")), sigtype=_f.SignalType.REEVALUATE, sim=sim)
        f_b = _f(lambda e: isinstance(e, dict) and bool(e.get("b")), sigtype=_f.SignalType.REEVALUATE, sim=sim)
        c = f_a & f_b

        signaled, payload = c.check({"a": True, "b": True})
        self.assertTrue(signaled)
        self.assertEqual(set(payload.keys()), {f_a, f_b})

        # Mutate one child out-of-band. check_and_wait() now prefers current
        # circuit signaled state as a fast-path.
        f_b.check({"a": True, "b": False})
        self.assertTrue(c.signaled)

        out = []

        async def consumer():
            t0 = sim.time
            got = await c.check_and_wait(5)
            out.append((sim.time - t0, got))

        sim.schedule(0, consumer())
        sim.run(10)

        self.assertEqual(len(out), 1)
        self.assertEqual(out[0][0], 0)
        self.assertEqual(set(out[0][1].keys()), {f_a, f_b})

    def test5_reevaluate_circuit_updates_payload_between_loop_cycles(self):
        sim = DSSimulation()
        pa = sim.publisher(name="pa")
        pb = sim.publisher(name="pb")
        p_other = sim.publisher(name="p_other")
        f_a = DSFilter(
            lambda e: isinstance(e, dict) and e.get("kind") == "A",
            sigtype=DSFilter.SignalType.REEVALUATE,
            eps=[pa],
            sim=sim,
        )
        f_b = DSFilter(
            lambda e: isinstance(e, dict) and e.get("kind") == "B",
            sigtype=DSFilter.SignalType.REEVALUATE,
            eps=[pb],
            sim=sim,
        )
        f_other = DSFilter(
            lambda e: e == "tick",
            sigtype=DSFilter.SignalType.REEVALUATE,
            eps=[p_other],
            sim=sim,
        )
        ready = DSCircuit(
            all,
            [f_a, f_b],
            sigtype=DSCircuit.SignalType.REEVALUATE,
            one_shot=False,
            sim=sim,
        )

        out = []

        async def worker():
            for cycle in range(2):
                got = await ready.check_and_wait(20)
                seqs = sorted(v["seq"] for v in got.values())
                out.append(("ready", cycle, sim.time, seqs))
                # Use wait() (not check_and_wait()) so this second await always
                # blocks for a new tick event in each cycle.
                _ = await f_other.wait(20)
                out.append(("other", cycle, sim.time))

        async def scenario():
            # First cycle signal
            await sim.wait(1)
            pa.signal({"kind": "A", "seq": 1})
            await sim.wait(1)
            pb.signal({"kind": "B", "seq": 1})

            # Re-signal while worker is blocked on the second await
            await sim.wait(1)
            pa.signal({"kind": "A", "seq": 2})
            await sim.wait(1)
            pb.signal({"kind": "B", "seq": 2})

            # Release the "other" await in both cycles
            await sim.wait(1)
            p_other.signal("tick")
            await sim.wait(1)
            p_other.signal("tick")

        sim.schedule(0, worker())
        sim.schedule(0, scenario())
        sim.run(30)

        self.assertEqual(out[0], ("ready", 0, 2, [1, 1]))
        self.assertEqual(out[1], ("other", 0, 5))
        # No third signal: cycle-2 first wait should return immediately at t=5,
        # and with the updated payload from the re-signal.
        self.assertEqual(out[2], ("ready", 1, 5, [2, 2]))
        self.assertEqual(out[3], ("other", 1, 6))

    def test6_latch_circuit_keeps_first_payload_between_loop_cycles(self):
        sim = DSSimulation()
        pa = sim.publisher(name="pa_latch")
        pb = sim.publisher(name="pb_latch")
        p_other = sim.publisher(name="p_other_latch")
        f_a = DSFilter(
            lambda e: isinstance(e, dict) and e.get("kind") == "A",
            sigtype=DSFilter.SignalType.LATCH,
            eps=[pa],
            sim=sim,
        )
        f_b = DSFilter(
            lambda e: isinstance(e, dict) and e.get("kind") == "B",
            sigtype=DSFilter.SignalType.LATCH,
            eps=[pb],
            sim=sim,
        )
        f_other = DSFilter(
            lambda e: e == "tick",
            sigtype=DSFilter.SignalType.LATCH,
            eps=[p_other],
            sim=sim,
        )
        ready = DSCircuit(
            all,
            [f_a, f_b],
            sigtype=DSCircuit.SignalType.LATCH,
            one_shot=False,
            sim=sim,
        )

        out = []

        async def worker():
            for cycle in range(2):
                got = await ready.check_and_wait(20)
                seqs = sorted(v["seq"] for v in got.values())
                out.append(("ready", cycle, sim.time, seqs))
                _ = await f_other.wait(20)
                out.append(("other", cycle, sim.time))

        async def scenario():
            # First cycle signal
            await sim.wait(1)
            pa.signal({"kind": "A", "seq": 1})
            await sim.wait(1)
            pb.signal({"kind": "B", "seq": 1})

            # Re-signal while worker is blocked on the second await
            await sim.wait(1)
            pa.signal({"kind": "A", "seq": 2})
            await sim.wait(1)
            pb.signal({"kind": "B", "seq": 2})

            # Release the "other" await in both cycles
            await sim.wait(1)
            p_other.signal("tick")
            await sim.wait(1)
            p_other.signal("tick")

        sim.schedule(0, worker())
        sim.schedule(0, scenario())
        sim.run(30)

        self.assertEqual(out[0], ("ready", 0, 2, [1, 1]))
        self.assertEqual(out[1], ("other", 0, 5))
        # LATCH+continuous returns immediately in cycle 2 as already signaled,
        # but payload remains the first latched values (no refresh to seq=2).
        self.assertEqual(out[2], ("ready", 1, 5, [1, 1]))
        # f_other is LATCH too: once signaled, later sends do not emit again
        # while it stays signaled, so wait() in cycle 2 times out.
        self.assertEqual(out[3], ("other", 1, 25))


class TestCondNewStrategyMerged(unittest.TestCase):
    def test_filter_is_endpoint_driven_default_latches(self):
        sim = DSSimulation()
        ep = sim.publisher(name="ep")
        flt = DSFilter(lambda e: e == "ok", eps=[ep], sim=sim).attach()

        ep.signal("ok")
        sim.run(1)
        self.assertTrue(flt.signaled)
        self.assertEqual(flt.cond_value(), "ok")

        ep.signal("nope")
        sim.run(2)
        self.assertTrue(flt.signaled)

    def test_filter_close_unsubscribes_endpoint(self):
        sim = DSSimulation()
        ep = sim.publisher(name="ep")
        flt = DSFilter(lambda e: True, eps=[ep], sim=sim).attach()

        self.assertTrue(ep.has_subscribers())
        flt.detach()
        self.assertFalse(ep.has_subscribers())
        flt.detach()
        self.assertFalse(ep.has_subscribers())

        flt.attach()
        self.assertTrue(ep.has_subscribers())
        flt.reset()
        self.assertTrue(ep.has_subscribers())

    def test_filter_reevaluate_recomputes(self):
        sim = DSSimulation()
        ep = sim.publisher(name="ep")
        flt = DSFilter(
            lambda e: e == "ok",
            sigtype=DSFilter.SignalType.REEVALUATE,
            eps=[ep],
            sim=sim,
            one_shot=False,
        ).attach()

        ep.signal("ok")
        sim.run(1)
        self.assertTrue(flt.signaled)

        ep.signal("nope")
        sim.run(2)
        self.assertFalse(flt.signaled)

    def test_filter_default_signals_only_on_rising_edge(self):
        sim = DSSimulation()
        ep = sim.publisher(name="ep")
        flt = DSFilter(lambda e: e == "ok", eps=[ep], sim=sim).attach()
        observed = []

        sink = sim.callback(lambda e: observed.append(e))
        flt._finish_tx.add_subscriber(sink, flt._finish_tx.Phase.PRE)

        ep.signal("ok")
        sim.run(1)
        ep.signal("ok")
        sim.run(2)
        ep.signal("nope")
        sim.run(3)

        self.assertTrue(flt.signaled)
        self.assertEqual(observed, [TestObject])

    def test_filter_default_auto_detaches_after_first_match(self):
        sim = DSSimulation()
        ep = sim.publisher(name="ep")
        flt = DSFilter(lambda e: e == "ok", eps=[ep], sim=sim).attach()

        self.assertTrue(flt.is_attached())
        self.assertTrue(ep.has_subscribers())

        ep.signal("ok")
        sim.run(1)

        self.assertFalse(flt.is_attached())
        self.assertFalse(ep.has_subscribers())

    def test_filter_pulsed_passes_event_without_latching(self):
        sim = DSSimulation()
        ep = sim.publisher(name="ep")
        flt = DSFilter(lambda e: e == "go", sigtype=DSFilter.SignalType.PULSED, eps=[ep], sim=sim)
        out = []

        async def waiter():
            got = await flt.wait(timeout=5)
            out.append((sim.time, got))

        def scenario():
            yield from sim.gwait(1)
            ep.signal("go")

        sim.schedule(0, waiter())
        sim.schedule(0, scenario())
        sim.run(10)

        self.assertEqual(len(out), 1)
        self.assertEqual(out[0][0], 1)
        self.assertEqual(out[0][1], "go")
        self.assertFalse(flt.signaled)

    def test_a_nested_circuit_two_pulses_same_endpoint_one_shot_payload(self):
        sim = DSSimulation()
        ep = sim.publisher(name="shared")

        a = DSFilter(lambda e: e == "go", sigtype=DSFilter.SignalType.PULSED, eps=[ep], sim=sim)
        b = DSFilter(lambda e: e == "other", sigtype=DSFilter.SignalType.REEVALUATE, eps=[ep], sim=sim)
        c = DSFilter(lambda e: e == "go", sigtype=DSFilter.SignalType.PULSED, eps=[ep], sim=sim)
        ready = (a | b) & c
        out = []

        async def waiter():
            got = await ready.wait(timeout=10)
            out.append((sim.time, got))

        def scenario():
            yield from sim.gwait(1)
            ep.signal("go")
            yield from sim.gwait(1)
            ep.signal("noop")

        sim.schedule(0, waiter())
        sim.schedule(0, scenario())
        sim.run(20)

        self.assertEqual(len(out), 1)
        self.assertEqual(out[0][0], 1)
        payload = out[0][1]
        self.assertIn(a, payload)
        self.assertIn(c, payload)
        self.assertEqual(payload[a], "go")
        self.assertEqual(payload[c], "go")
        self.assertTrue(ready.signaled)
        self.assertFalse(ready.is_attached())

    def test_pulsed_leaf_in_and_circuit_does_not_detach_before_parent_signals(self):
        sim = DSSimulation()
        pa = sim.publisher(name="pa")
        pb = sim.publisher(name="pb")

        fa = DSFilter(lambda e: e == "A", sigtype=DSFilter.SignalType.PULSED, eps=[pa], sim=sim)
        fb = DSFilter(lambda e: e == "B", sigtype=DSFilter.SignalType.REEVALUATE, eps=[pb], sim=sim)
        ready = fa & fb
        out = []

        async def waiter():
            got = await ready.wait(timeout=10)
            out.append((sim.time, got))

        def scenario():
            yield from sim.gwait(1)
            pa.signal("A")   # pulse arrives before fb is ready; circuit must not fire yet
            self.assertTrue(fa.is_attached())  # regression: fa used to detach here
            self.assertTrue(ready.is_attached())
            yield from sim.gwait(1)
            pb.signal("B")   # now fb is ready, but pulse from t=1 is already gone
            self.assertTrue(fa.is_attached())
            yield from sim.gwait(1)
            pa.signal("A")   # second pulse should satisfy (fa & fb)

        sim.schedule(0, waiter())
        sim.schedule(0, scenario())
        sim.run(20)

        self.assertEqual(out, [(3, {fa: "A", fb: "B"})])
        self.assertFalse(fa.is_attached())
        self.assertFalse(fb.is_attached())
        self.assertFalse(ready.is_attached())

    def test_filter_eps_binds_filter_to_endpoint(self):
        sim = DSSimulation()
        ep = sim.publisher(name="ep")

        flt = DSFilter(lambda e: e == "go", sigtype=DSFilter.SignalType.PULSED, eps=[ep], sim=sim)
        out = []

        async def waiter():
            got = await flt.wait(timeout=5)
            out.append(got)

        def scenario():
            yield from sim.gwait(1)
            ep.signal("go")

        sim.schedule(0, waiter())
        sim.schedule(0, scenario())
        sim.run(5)

        self.assertEqual(out, ["go"])

    def test_filter_with_eps_and_always_true_condition(self):
        sim = DSSimulation()
        ep = sim.publisher(name="ep")

        flt = DSFilter(cond=lambda _e: True, sigtype=DSFilter.SignalType.PULSED, eps=[ep], sim=sim)
        out = []

        async def waiter():
            got = await flt.wait(timeout=5)
            out.append(got)

        def scenario():
            yield from sim.gwait(1)
            ep.signal({"any": "payload"})

        sim.schedule(0, waiter())
        sim.schedule(0, scenario())
        sim.run(5)

        self.assertEqual(out, [{"any": "payload"}])

    def test_no_event_forwarding_to_wrapped_process(self):
        def gen():
            event = yield "boot"
            return event

        sim = DSSimulation()
        ep = sim.publisher(name="ep")
        proc = DSProcess(gen(), sim=sim)
        flt = DSFilter(proc, sigtype=DSFilter.SignalType.REEVALUATE, eps=[ep], sim=sim)

        ep.signal("x")
        sim.run()

        self.assertFalse(proc.started())
        self.assertFalse(proc.finished())
        self.assertFalse(flt.signaled)

    def test_external_finish_triggers_filter_wait(self):
        sim = DSSimulation()

        def long_process():
            yield from sim.gwait(10)
            return "hello"

        proc = DSProcess(long_process(), sim=sim).schedule(0)
        flt = DSFilter(proc, sim=sim)
        out = []

        def complete_filter():
            yield from sim.gwait(2)
            flt.finish("Signal!")

        async def waiter():
            out.append(await flt)

        sim.schedule(0, complete_filter())
        sim.schedule(0, waiter())
        sim.run(20)

        self.assertEqual(out, ["Signal!"])

    def test_circuit_can_signal_before_waiter_and_precheck_returns_immediately(self):
        sim = DSSimulation()
        ep = sim.publisher(name="ep")

        a = DSFilter(lambda e: e == "go", eps=[ep], sim=sim).attach()
        b = DSFilter(lambda e: e == "go", eps=[ep], sim=sim).attach()
        ready = a & b
        ready.attach()

        ep.signal("go")
        sim.run(1)

        self.assertTrue(ready.signaled)
        self.assertEqual(ready.cond_value(), {a: "go", b: "go"})

        out = []

        async def waiter():
            t0 = sim.time
            got = await ready.check_and_wait(timeout=5)
            out.append((sim.time - t0, got))

        sim.schedule(0, waiter())
        sim.run(2)

        self.assertEqual(len(out), 1)
        self.assertEqual(out[0][0], 0)
        self.assertEqual(out[0][1], {a: "go", b: "go"})

    def test_circuit_close_recursively_unsubscribes_nested_filters(self):
        sim = DSSimulation()
        ep0 = sim.publisher(name="ep0")
        ep1 = sim.publisher(name="ep1")

        a = DSFilter(lambda e: e == "a", eps=[ep0], sim=sim).attach()
        b = DSFilter(lambda e: e == "b", eps=[ep0], sim=sim).attach()
        c = DSFilter(lambda e: e == "c", eps=[ep1], sim=sim).attach()
        ready = (a | b) & c
        ready.attach()

        self.assertTrue(ep0.has_subscribers())
        self.assertTrue(ep1.has_subscribers())
        self.assertGreater(len(a._listeners), 0)
        self.assertGreater(len(c._listeners), 0)

        ready.detach()

        self.assertFalse(ep0.has_subscribers())
        self.assertFalse(ep1.has_subscribers())
        self.assertEqual(len(a._listeners), 0)
        self.assertEqual(len(b._listeners), 0)
        self.assertEqual(len(c._listeners), 0)
        ready.detach()

        ready.attach()
        self.assertTrue(ep0.has_subscribers())
        self.assertTrue(ep1.has_subscribers())
        ready.reset()
        self.assertTrue(ep0.has_subscribers())
        self.assertTrue(ep1.has_subscribers())

    def test_circuit_wait_auto_opens_when_closed_and_does_not_auto_close(self):
        sim = DSSimulation()
        ep = sim.publisher(name="ep")

        a = DSFilter(lambda e: e == "go", eps=[ep], sim=sim, one_shot=False)
        b = DSFilter(lambda e: e == "go", eps=[ep], sim=sim, one_shot=False)
        ready = DSCircuit(all, [a, b], sim=sim, one_shot=False)

        self.assertFalse(a.is_attached())
        self.assertFalse(b.is_attached())
        self.assertFalse(ready.is_attached())
        self.assertFalse(ep.has_subscribers())

        out = []

        async def waiter():
            got = await ready.wait(timeout=5)
            out.append(got)

        def scenario():
            yield from sim.gwait(1)
            self.assertTrue(a.is_attached())
            self.assertTrue(b.is_attached())
            self.assertTrue(ready.is_attached())
            self.assertTrue(ep.has_subscribers())
            ep.signal("go")

        sim.schedule(0, waiter())
        sim.schedule(0, scenario())
        sim.run(10)

        self.assertEqual(out, [{a: "go", b: "go"}])
        self.assertTrue(a.is_attached())
        self.assertTrue(b.is_attached())
        self.assertTrue(ready.is_attached())
        self.assertTrue(ep.has_subscribers())

    def test_circuit_builder_set_one_shot_false_propagates_to_children(self):
        sim = DSSimulation()
        ep = sim.publisher(name="ep")

        a = DSFilter(lambda e: e == "go", eps=[ep], sim=sim).attach()
        b = DSFilter(lambda e: e == "go", eps=[ep], sim=sim).attach()
        ready = (a & b).set_one_shot(False)
        ready.attach()

        self.assertFalse(ready.one_shot)
        self.assertFalse(a.one_shot)
        self.assertFalse(b.one_shot)

        ep.signal("go")
        sim.run(1)

        self.assertTrue(ready.is_attached())
        self.assertTrue(a.is_attached())
        self.assertTrue(b.is_attached())
        self.assertTrue(ep.has_subscribers())

    def test_circuit_rejects_pulsed_sigtype(self):
        sim = DSSimulation()
        a = DSFilter("a", sim=sim)
        b = DSFilter("b", sim=sim)
        with self.assertRaises(ValueError):
            DSCircuit(all, [a, b], sigtype=DSCircuit.SignalType.PULSED, sim=sim)


class TestSourceScopedCircuitMerged(unittest.TestCase):
    def test_independent_reevaluate_and(self):
        sim = DSSimulation()

        temp_pub = sim.publisher(name="temp")
        pressure_pub = sim.publisher(name="pressure")

        f_temp = DSFilter(lambda e: e == "stable", sigtype=DSFilter.SignalType.REEVALUATE, eps=[temp_pub], sim=sim)
        f_pressure = DSFilter(lambda e: e == "ok", sigtype=DSFilter.SignalType.REEVALUATE, eps=[pressure_pub], sim=sim)

        ready = f_temp & f_pressure
        result = [None]

        def controller():
            result[0] = yield from ready.gwait(timeout=10)

        def scenario():
            yield from sim.gwait(1)
            temp_pub.signal("stable")
            yield from sim.gwait(1)
            pressure_pub.signal("ok")

        sim.schedule(0, controller())
        sim.schedule(0, scenario())
        sim.run()

        self.assertIsNotNone(result[0])

    def test_reevaluate_toggle_independence(self):
        sim = DSSimulation()

        temp_pub = sim.publisher(name="temp")
        pressure_pub = sim.publisher(name="pressure")

        f_temp = DSFilter(lambda e: e == "stable", sigtype=DSFilter.SignalType.REEVALUATE, eps=[temp_pub], sim=sim)
        f_pressure = DSFilter(lambda e: e == "ok", sigtype=DSFilter.SignalType.REEVALUATE, eps=[pressure_pub], sim=sim)

        ready = f_temp & f_pressure
        fire_times = []

        def controller():
            r = yield from ready.gwait(timeout=10)
            if r is not None:
                fire_times.append(sim.time)
            r = yield from ready.gwait(timeout=10)
            if r is not None:
                fire_times.append(sim.time)

        def scenario():
            yield from sim.gwait(1)
            temp_pub.signal("stable")

            yield from sim.gwait(1)
            pressure_pub.signal("ok")

            yield from sim.gwait(1)
            temp_pub.signal("drifted")

            yield from sim.gwait(1)
            pressure_pub.signal("ok")

            yield from sim.gwait(1)
            temp_pub.signal("stable")

        sim.schedule(0, controller())
        sim.schedule(0, scenario())
        sim.run()

        self.assertGreaterEqual(len(fire_times), 1)
        self.assertEqual(fire_times[0], 2)
        self.assertEqual(len(fire_times), 2)
        self.assertEqual(fire_times[1], 5)

    def test_pulsed_with_reevaluate(self):
        sim = DSSimulation()

        temp_pub = sim.publisher(name="temp")
        operator_pub = sim.publisher(name="operator")

        f_temp = DSFilter(lambda e: e == "stable", sigtype=DSFilter.SignalType.REEVALUATE, eps=[temp_pub], sim=sim)
        f_operator = DSFilter(lambda e: e == "go", sigtype=DSFilter.SignalType.PULSED, eps=[operator_pub], sim=sim)

        ready = f_temp & f_operator
        result = [None]

        def controller():
            result[0] = yield from ready.gwait(timeout=20)

        def scenario():
            yield from sim.gwait(1)
            operator_pub.signal("go")

            yield from sim.gwait(1)
            temp_pub.signal("stable")

            yield from sim.gwait(1)
            operator_pub.signal("go")

        sim.schedule(0, controller())
        sim.schedule(0, scenario())
        sim.run()

        self.assertIsNotNone(result[0])


class TestFilterPolicy(unittest.TestCase):
    def test_filter_init_from_policy(self):
        sim = DSSimulation()
        ep = sim.publisher(name='ep')
        policy = {
            'cond': lambda e: e == 'ok',
            'sigtype': DSFilter.SignalType.PULSED,
            'eps': {ep: {'tier': ep.Phase.PRE, 'params': {'priority': 3}}},
            'one_shot': False,
        }
        f = DSFilter(policy=policy, sim=sim)
        self.assertIs(f._base_eps[ep]['tier'], ep.Phase.PRE)
        self.assertEqual(f._base_eps[ep]['params'], {'priority': 3})
        self.assertTrue(f.pulse)
        self.assertTrue(f.reevaluate)
        self.assertFalse(f.one_shot)

    def test_filter_init_from_policy_rejects_legacy_eps_mapping(self):
        sim = DSSimulation()
        ep = sim.publisher(name='ep')
        policy = {
            'cond': lambda e: e == 'ok',
            'eps': {ep: ep.Phase.PRE},
        }
        with self.assertRaises(TypeError):
            DSFilter(policy=policy, sim=sim)

    def test_policy_overrides_explicit_args(self):
        sim = DSSimulation()
        f = DSFilter(one_shot=False, policy={'one_shot': True}, sim=sim)
        self.assertTrue(f.one_shot)

    def test_policy_unknown_key_is_ignored(self):
        sim = DSSimulation()
        f = DSFilter(policy={'unknown': 1}, sim=sim)
        self.assertIs(f.cond, AlwaysTrue)


if __name__ == "__main__":
    unittest.main()
