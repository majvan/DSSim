#!/usr/bin/env python3
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
Unit-resource benchmark (pubsub + lite).

Scenarios
---------
1. resource-uncontended : single process repeatedly acquires/releases unit resource
2. priority-dispatch    : K blocked waiters on priority resource, feeder wakes one item at a time
3. preemption-delivery  : low-priority holder repeatedly preempted by high-priority requester
4. resource-contention  : K workers contend for a single unit token
5. timed-contention     : timed contention on a single shared unit token
'''

import argparse
import os
import statistics
import sys
import time
from contextlib import contextmanager

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dssim import DSSimulation, LiteLayer2
from dssim import DSUnitResource, DSPriorityResource, DSLiteUnitResource, DSLitePriorityResource
from dssim import DSQueue, DSResourcePreempted
from dssim.timequeue import TQBinTree, TQBisect

simpy = None
salabim = None
ACTIVE_TQ_VARIANTS = [('TQBinTree', TQBinTree)]


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
N_EVENTS = 20_000
N_WAITERS = 100
N_CONTENTION_WORKERS = 16
N_TIMED_WORKERS = 16
REPEATS = 30
DELAY = 4e-9   # time outside resource hold
HOLD = 12e-9   # time while resource is held


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
@contextmanager
def _with_timequeue(tq_cls):
    '''Temporarily force DSSimulation default timequeue class in this module.'''
    global DSSimulation
    base_cls = DSSimulation

    class _DSSimulationWithTQ(base_cls):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault('timequeue', tq_cls)
            super().__init__(*args, **kwargs)

    DSSimulation = _DSSimulationWithTQ
    try:
        yield
    finally:
        DSSimulation = base_cls


def bench(fn, *args):
    times = []
    for _ in range(REPEATS):
        t0 = time.perf_counter()
        fn(*args)
        times.append(time.perf_counter() - t0)
    return min(times), statistics.mean(times), statistics.stdev(times), sum(times)


def report(label, n, min_t, mean_t, stdev_t, total_t):
    print(f'  {label:<32s}  {n/mean_t:>10,.0f} ev/s'
          f'  mean = {mean_t*1e3:7.2f} ± {stdev_t*1e3:3.2f} ms   min = {min_t*1e3:7.2f} ms'
          f'  total = {total_t:6.2f} s')


def report_dssim_tq(label, n, fn, *args):
    for tq_name, tq_cls in ACTIVE_TQ_VARIANTS:
        with _with_timequeue(tq_cls):
            report(f'{label} [{tq_name}]', n, *bench(fn, *args))


def _parse_args():
    parser = argparse.ArgumentParser(
        description='DSUnitResource benchmark (DSSim by default, optional SimPy/salabim via flags).',
    )
    parser.add_argument(
        '--scenario',
        choices=['all', 'resource-uncontended', 'priority-dispatch', 'preemption-delivery', 'resource-contention', 'timed-contention'],
        default='all',
        help='Run only a selected scenario (default: all).',
    )
    parser.add_argument('--with-simpy', action='store_true', help='Include SimPy rows.')
    parser.add_argument('--with-salabim', action='store_true', help='Include salabim rows.')
    parser.add_argument('--with-dssim-pubsub', dest='with_dssim_pubsub', action='store_true', default=True,
                        help='Include DSSim PubSub rows (default: on).')
    parser.add_argument('--without-dssim-pubsub', dest='with_dssim_pubsub', action='store_false',
                        help='Exclude DSSim PubSub rows.')
    parser.add_argument('--with-dssim-lite', dest='with_dssim_lite', action='store_true', default=True,
                        help='Include DSSim Lite rows (default: on).')
    parser.add_argument('--without-dssim-lite', dest='with_dssim_lite', action='store_false',
                        help='Exclude DSSim Lite rows.')
    parser.add_argument('--with-tq-bintree', dest='with_tq_bintree', action='store_true', default=True,
                        help='Include TQBinTree runs (default: on).')
    parser.add_argument('--without-tq-bintree', dest='with_tq_bintree', action='store_false',
                        help='Exclude TQBinTree runs.')
    parser.add_argument('--with-tq-bisect', dest='with_tq_bisect', action='store_true', default=False,
                        help='Include TQBisect runs (default: off).')
    parser.add_argument('--without-tq-bisect', dest='with_tq_bisect', action='store_false',
                        help='Exclude TQBisect runs.')
    return parser.parse_args()


def dssim_unit_resource_uncontended(n):
    sim = DSSimulation()
    res = DSUnitResource(amount=1, capacity=1, sim=sim)
    done = 0

    def worker():
        nonlocal done
        for _ in range(n):
            got = yield from res.gget()
            assert got == 1
            res.put_nowait()
            done += 1

    sim.schedule(0, worker())
    sim.run()
    assert done == n, f'unit resource-uncontended: expected {n}, got {done}'


def dssim_lite_unit_resource_uncontended(n):
    sim = DSSimulation(layer2=LiteLayer2)
    res = DSLiteUnitResource(amount=1, capacity=1, sim=sim)
    done = 0

    def worker():
        nonlocal done
        for _ in range(n):
            got = yield from res.gget()
            assert got == 1
            res.put_nowait()
            done += 1

    sim.schedule(0, worker())
    sim.run()
    assert done == n, f'lite unit resource-uncontended: expected {n}, got {done}'


def dssim_unit_priority_dispatch(n, k):
    sim = DSSimulation()
    res = DSPriorityResource(amount=0, capacity=1, preemptive=False, sim=sim)
    per = n // k
    consumed = 0

    def waiter(priority):
        nonlocal consumed
        for _ in range(per):
            got = yield from res.gget(priority=priority, preempt=False)
            assert got == 1
            consumed += 1

    def feeder():
        for _ in range(per * k):
            res.put_nowait()
            yield from sim.gwait(0)

    for i in range(k):
        sim.schedule(0, waiter(i))
    sim.schedule(0, feeder())
    sim.run()
    assert consumed == per * k, f'unit priority-dispatch: expected {per*k}, got {consumed}'


def dssim_lite_unit_priority_dispatch(n, k):
    sim = DSSimulation(layer2=LiteLayer2)
    res = DSLitePriorityResource(amount=0, capacity=1, sim=sim)
    per = n // k
    consumed = 0

    def waiter(priority):
        nonlocal consumed
        for _ in range(per):
            got = yield from res.gget(priority=priority)
            assert got == 1
            consumed += 1

    def feeder():
        for _ in range(per * k):
            res.put_nowait()
            yield from sim.gwait(0)

    for i in range(k):
        sim.schedule(0, waiter(i))
    sim.schedule(0, feeder())
    sim.run()
    assert consumed == per * k, f'lite unit priority-dispatch: expected {per*k}, got {consumed}'


def dssim_unit_preemption_delivery(n):
    sim = DSSimulation()
    res = DSPriorityResource(amount=1, capacity=1, preemptive=True, sim=sim)
    handoff = DSQueue(sim=sim)

    preempted = 0
    high_got = 0

    def low_holder():
        nonlocal preempted
        for _ in range(n):
            with res.autorelease():
                got = yield from res.gget(priority=10, preempt=True)
                assert got == 1
                handoff.put_nowait(1)
                try:
                    yield from sim.gwait(float('inf'))
                except DSResourcePreempted:
                    preempted += 1

    def high_preempter():
        nonlocal high_got
        for _ in range(n):
            yield from handoff.gget()
            with res.autorelease():
                got = yield from res.gget(priority=1, preempt=True)
                assert got == 1
                high_got += 1

    sim.schedule(0, low_holder())
    sim.schedule(0, high_preempter())
    sim.run()
    assert preempted == n, f'unit preemption-delivery: expected {n} preemptions, got {preempted}'
    assert high_got == n, f'unit preemption-delivery: expected {n} high acquires, got {high_got}'


def dssim_lite_unit_preemption_delivery(n):
    sim = DSSimulation(layer2=LiteLayer2)
    res = DSLitePriorityResource(amount=1, capacity=1, preemptive=True, sim=sim)
    handoff = sim.queue(capacity=1)

    preempted = 0
    high_got = 0

    def low_holder():
        nonlocal preempted
        for _ in range(n):
            with res.autorelease():
                got = yield from res.gget(priority=10, preempt=True)
                assert got == 1
                handoff.put_nowait(1)
                try:
                    yield from sim.gwait(float('inf'))
                except DSLitePriorityResource.Preempted:
                    preempted += 1

    def high_preempter():
        nonlocal high_got
        for _ in range(n):
            yield from handoff.gget()
            with res.autorelease():
                got = yield from res.gget(priority=1, preempt=True)
                assert got == 1
                high_got += 1

    sim.schedule(0, low_holder())
    sim.schedule(0, high_preempter())
    sim.run()
    assert preempted == n, f'lite unit preemption-delivery: expected {n} preemptions, got {preempted}'
    assert high_got == n, f'lite unit preemption-delivery: expected {n} high acquires, got {high_got}'


def dssim_unit_resource_contention(n, k):
    sim = DSSimulation()
    res = DSUnitResource(amount=1, capacity=1, sim=sim)
    per = n // k
    acquired = 0

    def worker():
        nonlocal acquired
        for _ in range(per):
            got = yield from res.gget()
            assert got == 1
            yield from sim.gwait(0)
            res.put_nowait()
            acquired += 1

    for _ in range(k):
        sim.schedule(0, worker())
    sim.run()
    assert acquired == per * k, f'unit resource-contention: expected {per*k}, got {acquired}'


def dssim_lite_unit_resource_contention(n, k):
    sim = DSSimulation(layer2=LiteLayer2)
    res = DSLiteUnitResource(amount=1, capacity=1, sim=sim)
    per = n // k
    acquired = 0

    def worker():
        nonlocal acquired
        for _ in range(per):
            got = yield from res.gget()
            assert got == 1
            yield from sim.gwait(0)
            res.put_nowait()
            acquired += 1

    for _ in range(k):
        sim.schedule(0, worker())
    sim.run()
    assert acquired == per * k, f'lite unit resource-contention: expected {per*k}, got {acquired}'


def dssim_unit_timed_contention(n, k):
    sim = DSSimulation()
    port = DSUnitResource(amount=1, capacity=1, sim=sim)
    per = n // k
    done = 0

    def worker():
        nonlocal done
        for _ in range(per):
            yield from sim.gwait(DELAY)
            got = yield from port.gget()
            assert got == 1
            yield from sim.gwait(HOLD)
            port.put_nowait()
            done += 1

    for _ in range(k):
        sim.schedule(0, worker())
    sim.run()
    assert done == per * k, f'unit timed-contention: expected {per*k}, got {done}'


def dssim_lite_unit_timed_contention(n, k):
    sim = DSSimulation(layer2=LiteLayer2)
    port = DSLiteUnitResource(amount=1, capacity=1, sim=sim)
    per = n // k
    done = 0

    def worker():
        nonlocal done
        for _ in range(per):
            yield from sim.gwait(DELAY)
            got = yield from port.gget()
            assert got == 1
            yield from sim.gwait(HOLD)
            port.put_nowait()
            done += 1

    for _ in range(k):
        sim.schedule(0, worker())
    sim.run()
    assert done == per * k, f'lite unit timed-contention: expected {per*k}, got {done}'


# ---------------------------------------------------------------------------
# SimPy unit-resource equivalents
# ---------------------------------------------------------------------------
def simpy_resource_uncontended(n):
    env = simpy.Environment()
    res = simpy.Resource(env, capacity=1)
    done = {'n': 0}

    def worker():
        for _ in range(n):
            with res.request() as req:
                yield req
                done['n'] += 1
            yield env.timeout(0)

    env.process(worker())
    env.run()
    assert done['n'] == n, f'simpy resource-uncontended: expected {n}, got {done["n"]}'


def simpy_priority_dispatch(n, k):
    env = simpy.Environment()
    res = simpy.PriorityResource(env, capacity=1)
    per = n // k
    consumed = {'n': 0}

    def waiter(priority):
        for _ in range(per):
            with res.request(priority=priority) as req:
                yield req
                consumed['n'] += 1
            yield env.timeout(0)

    def feeder():
        for _ in range(per * k):
            yield env.timeout(0)

    for i in range(k):
        env.process(waiter(i))
    env.process(feeder())
    env.run()
    assert consumed['n'] == per * k, f'simpy priority-dispatch: expected {per*k}, got {consumed["n"]}'


def simpy_preemption_delivery(n):
    env = simpy.Environment()
    res = simpy.PreemptiveResource(env, capacity=1)
    handoff = simpy.Store(env, capacity=1)

    preempted = {'n': 0}
    high_got = {'n': 0}

    def low_holder():
        for _ in range(n):
            with res.request(priority=10, preempt=True) as req:
                yield req
                yield handoff.put(1)
                try:
                    yield env.timeout(10**9)
                except simpy.Interrupt:
                    preempted['n'] += 1

    def high_preempter():
        for _ in range(n):
            yield handoff.get()
            with res.request(priority=1, preempt=True) as req:
                yield req
                high_got['n'] += 1
                yield env.timeout(0)

    env.process(low_holder())
    env.process(high_preempter())
    env.run()
    assert preempted['n'] == n, f'simpy preemption-delivery: expected {n} preemptions, got {preempted["n"]}'
    assert high_got['n'] == n, f'simpy preemption-delivery: expected {n} high acquires, got {high_got["n"]}'


def simpy_resource_contention(n, k):
    env = simpy.Environment()
    res = simpy.Resource(env, capacity=1)
    per = n // k
    acquired = {'n': 0}

    def worker():
        for _ in range(per):
            with res.request() as req:
                yield req
                yield env.timeout(0)
                acquired['n'] += 1

    for _ in range(k):
        env.process(worker())
    env.run()
    assert acquired['n'] == per * k, f'simpy resource-contention: expected {per*k}, got {acquired["n"]}'


def simpy_timed_contention(n, k):
    env = simpy.Environment()
    port = simpy.Resource(env, capacity=1)
    per = n // k
    done = {'n': 0}

    def worker():
        for _ in range(per):
            yield env.timeout(DELAY)
            with port.request() as req:
                yield req
                yield env.timeout(HOLD)
                done['n'] += 1

    for _ in range(k):
        env.process(worker())
    env.run()
    assert done['n'] == per * k, f'simpy timed-contention: expected {per*k}, got {done["n"]}'


# ---------------------------------------------------------------------------
# salabim unit-resource equivalents
# ---------------------------------------------------------------------------
def salabim_resource_uncontended(n):
    env = salabim.Environment(trace=False)
    res = salabim.Resource(env=env, capacity=1)
    done = [0]

    class Worker(salabim.Component):
        def process(self):
            for _ in range(n):
                yield self.request(res)
                done[0] += 1
                self.release(res)

    Worker(env=env)
    env.run()
    assert done[0] == n, f'salabim resource-uncontended: expected {n}, got {done[0]}'


def salabim_priority_dispatch(n, k):
    env = salabim.Environment(trace=False)
    res = salabim.Resource(env=env, capacity=1, preemptive=False)
    per = n // k
    consumed = [0]

    class Waiter(salabim.Component):
        def setup(self, request_priority):
            self.request_priority = request_priority

        def process(self):
            for _ in range(per):
                yield self.request((res, 1, self.request_priority))
                consumed[0] += 1
                self.release(res)
                yield self.hold(0)

    class Feeder(salabim.Component):
        def process(self):
            for _ in range(per * k):
                yield self.hold(0)

    for i in range(k):
        Waiter(env=env, request_priority=i)
    Feeder(env=env)
    env.run()
    assert consumed[0] == per * k, f'salabim priority-dispatch: expected {per*k}, got {consumed[0]}'


def salabim_preemption_delivery(n):
    env = salabim.Environment(trace=False)
    res = salabim.Resource(env=env, capacity=1, preemptive=True)

    preempted = [0]
    high_got = [0]
    high_ref = [None]

    class LowHolder(salabim.Component):
        def process(self):
            for _ in range(n):
                yield self.request((res, 1, 10))
                t0 = env.now()
                high_ref[0].activate()
                yield self.hold(10**9)
                if env.now() < t0 + 10**9:
                    preempted[0] += 1

    class HighPreempter(salabim.Component):
        def process(self):
            for _ in range(n):
                yield self.passivate()
                yield self.request((res, 1, 1))
                high_got[0] += 1
                self.release(res)

    high_ref[0] = HighPreempter(env=env)
    LowHolder(env=env)
    env.run()
    assert preempted[0] == n, f'salabim preemption-delivery: expected {n} preemptions, got {preempted[0]}'
    assert high_got[0] == n, f'salabim preemption-delivery: expected {n} high acquires, got {high_got[0]}'


def salabim_resource_contention(n, k):
    env = salabim.Environment(trace=False)
    res = salabim.Resource(env=env, capacity=1)
    per = n // k
    acquired = [0]

    class Worker(salabim.Component):
        def process(self):
            for _ in range(per):
                yield self.request(res)
                yield self.hold(0)
                acquired[0] += 1
                self.release(res)

    for _ in range(k):
        Worker(env=env)
    env.run()
    assert acquired[0] == per * k, f'salabim resource-contention: expected {per*k}, got {acquired[0]}'


def salabim_timed_contention(n, k):
    env = salabim.Environment(trace=False)
    port = salabim.Resource(env=env, capacity=1)
    per = n // k
    done = [0]

    class Worker(salabim.Component):
        def process(self):
            for _ in range(per):
                yield self.hold(DELAY)
                yield self.request(port)
                yield self.hold(HOLD)
                done[0] += 1
                self.release(port)

    for _ in range(k):
        Worker(env=env)
    env.run()
    assert done[0] == per * k, f'salabim timed-contention: expected {per*k}, got {done[0]}'


if __name__ == '__main__':
    args = _parse_args()
    ACTIVE_TQ_VARIANTS = []
    if args.with_tq_bintree:
        ACTIVE_TQ_VARIANTS.append(('TQBinTree', TQBinTree))
    if args.with_tq_bisect:
        ACTIVE_TQ_VARIANTS.append(('TQBisect', TQBisect))
    if not ACTIVE_TQ_VARIANTS:
        print('No DSSim timequeue selected; DSSim rows will be skipped.')

    run_simpy = False
    run_salabim = False
    if args.with_simpy:
        try:
            import simpy as simpy_mod
            simpy = simpy_mod
            run_simpy = True
        except Exception as exc:
            print(f'SimPy requested but unavailable: {exc}')

    if args.with_salabim:
        try:
            import salabim as salabim_mod
            salabim = salabim_mod
            salabim.yieldless(False)
            run_salabim = True
        except Exception as exc:
            print(f'salabim requested but unavailable: {exc}')

    print(f'Python {sys.version.split()[0]}')
    print(f'Parameters: N={N_EVENTS:,}  waiters={N_WAITERS}  cont_workers={N_CONTENTION_WORKERS}  timed_workers={N_TIMED_WORKERS}  repeats={REPEATS}\n')
    if args.with_simpy and not run_simpy:
        print('SimPy unavailable: skipping SimPy rows.\n')
    if args.with_salabim and not run_salabim:
        print('salabim unavailable: skipping salabim rows.\n')

    run_all = args.scenario == 'all'

    if run_all or args.scenario == 'resource-uncontended':
        print(f'=== Scenario 1: UnitResource uncontended (N={N_EVENTS:,}) ===')
        if args.with_dssim_pubsub and ACTIVE_TQ_VARIANTS:
            report_dssim_tq('DSSim DSUnitResource', N_EVENTS, dssim_unit_resource_uncontended, N_EVENTS)
        if args.with_dssim_lite and ACTIVE_TQ_VARIANTS:
            report_dssim_tq('DSSim DSLiteUnitResource', N_EVENTS, dssim_lite_unit_resource_uncontended, N_EVENTS)
        if run_simpy:
            report('SimPy Resource', N_EVENTS, *bench(simpy_resource_uncontended, N_EVENTS))
        if run_salabim:
            report('salabim Resource', N_EVENTS, *bench(salabim_resource_uncontended, N_EVENTS))

    if run_all or args.scenario == 'priority-dispatch':
        print(f'\n=== Scenario 2: Priority dispatch (N={N_EVENTS:,}, K={N_WAITERS}) ===')
        n2 = (N_EVENTS // N_WAITERS) * N_WAITERS
        if args.with_dssim_pubsub and ACTIVE_TQ_VARIANTS:
            report_dssim_tq('DSSim DSPriorityResource(unit)', n2, dssim_unit_priority_dispatch, n2, N_WAITERS)
        if args.with_dssim_lite and ACTIVE_TQ_VARIANTS:
            report_dssim_tq('DSSim DSLitePriorityResource(unit)', n2, dssim_lite_unit_priority_dispatch, n2, N_WAITERS)
        if run_simpy:
            report('SimPy PriorityResource', n2, *bench(simpy_priority_dispatch, n2, N_WAITERS))
        if run_salabim:
            report('salabim Resource', n2, *bench(salabim_priority_dispatch, n2, N_WAITERS))

    if run_all or args.scenario == 'preemption-delivery':
        print(f'\n=== Scenario 3: Preemption delivery (N={N_EVENTS:,}) ===')
        if args.with_dssim_pubsub and ACTIVE_TQ_VARIANTS:
            report_dssim_tq('DSSim Preemption(unit)', N_EVENTS, dssim_unit_preemption_delivery, N_EVENTS)
        if args.with_dssim_lite and ACTIVE_TQ_VARIANTS:
            report_dssim_tq('DSSim LitePreemption(unit)', N_EVENTS, dssim_lite_unit_preemption_delivery, N_EVENTS)
        if run_simpy:
            report('SimPy PreemptiveResource', N_EVENTS, *bench(simpy_preemption_delivery, N_EVENTS))
        if run_salabim:
            report('salabim PreemptiveResource', N_EVENTS, *bench(salabim_preemption_delivery, N_EVENTS))

    if run_all or args.scenario == 'resource-contention':
        print(f'\n=== Scenario 4: UnitResource contention (N={N_EVENTS:,}, K={N_CONTENTION_WORKERS}) ===')
        n4 = (N_EVENTS // N_CONTENTION_WORKERS) * N_CONTENTION_WORKERS
        if args.with_dssim_pubsub and ACTIVE_TQ_VARIANTS:
            report_dssim_tq('DSSim DSUnitContended', n4, dssim_unit_resource_contention, n4, N_CONTENTION_WORKERS)
        if args.with_dssim_lite and ACTIVE_TQ_VARIANTS:
            report_dssim_tq('DSSim DSLiteUnitContended', n4, dssim_lite_unit_resource_contention, n4, N_CONTENTION_WORKERS)
        if run_simpy:
            report('SimPy ResourceContended', n4, *bench(simpy_resource_contention, n4, N_CONTENTION_WORKERS))
        if run_salabim:
            report('salabim ResourceContended', n4, *bench(salabim_resource_contention, n4, N_CONTENTION_WORKERS))

    if run_all or args.scenario == 'timed-contention':
        print(f'\n=== Scenario 5: UnitTimed contention (N={N_EVENTS:,}, K={N_TIMED_WORKERS}, delay={DELAY:g}, hold={HOLD:g}) ===')
        n5 = (N_EVENTS // N_TIMED_WORKERS) * N_TIMED_WORKERS
        if args.with_dssim_pubsub and ACTIVE_TQ_VARIANTS:
            report_dssim_tq('DSSim DSUnitTimedContended', n5, dssim_unit_timed_contention, n5, N_TIMED_WORKERS)
        if args.with_dssim_lite and ACTIVE_TQ_VARIANTS:
            report_dssim_tq('DSSim DSLiteUnitTimedContended', n5, dssim_lite_unit_timed_contention, n5, N_TIMED_WORKERS)
        if run_simpy:
            report('SimPy TimedContended', n5, *bench(simpy_timed_contention, n5, N_TIMED_WORKERS))
        if run_salabim:
            report('salabim TimedContended', n5, *bench(salabim_timed_contention, n5, N_TIMED_WORKERS))

    print()
