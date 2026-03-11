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
Benchmark: DSSim Resource / PriorityResource / preemption delivery

Scenarios
---------
1. resource-uncontended : single process repeatedly acquires/releases Resource
2. priority-dispatch    : K blocked waiters on PriorityResource, feeder wakes one item at a time
3. preemption-delivery  : low-priority holder repeatedly preempted by high-priority requester;
                          measures preemption dispatch + exception delivery path

Metrics per scenario
--------------------
- events/s  : N / mean wall-clock seconds
- mean ms   : average wall-clock time over REPEATS runs
- min ms    : fastest run
'''

import sys
import os
import time
import statistics

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dssim import DSSimulation, TinyLayer2
from dssim import Resource, PriorityResource, TinyResource, TinyPriorityResource
from dssim import Queue, DSResourcePreempted

try:
    import simpy
    _HAS_SIMPY = True
except Exception:
    simpy = None
    _HAS_SIMPY = False


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
N_EVENTS = 20_000
N_WAITERS = 100
REPEATS = 30


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Scenario 1: plain Resource
# ---------------------------------------------------------------------------
def dssim_resource_uncontended(n):
    sim = DSSimulation()
    res = Resource(amount=1, capacity=1, sim=sim)
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
    assert done == n, f'resource-uncontended: expected {n}, got {done}'


# TinyLayer2 variant of scenario 1
def dssim_tiny_resource_uncontended(n):
    sim = DSSimulation(layer2=TinyLayer2)
    res = TinyResource(amount=1, capacity=1, sim=sim)
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
    assert done == n, f'tiny resource-uncontended: expected {n}, got {done}'


# ---------------------------------------------------------------------------
# Scenario 2: PriorityResource waiter dispatch
# ---------------------------------------------------------------------------
def dssim_priority_dispatch(n, k):
    sim = DSSimulation()
    res = PriorityResource(amount=0, capacity=1, preemptive=False, sim=sim)
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
            yield from sim.gwait(0)  # wake exactly one waiter per token

    for i in range(k):
        sim.schedule(0, waiter(i))
    sim.schedule(0, feeder())
    sim.run()
    assert consumed == per * k, f'priority-dispatch: expected {per*k}, got {consumed}'


# TinyLayer2 variant of scenario 2
def dssim_tiny_priority_dispatch(n, k):
    sim = DSSimulation(layer2=TinyLayer2)
    res = TinyPriorityResource(amount=0, capacity=1, sim=sim)
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
    assert consumed == per * k, f'tiny priority-dispatch: expected {per*k}, got {consumed}'


# ---------------------------------------------------------------------------
# Scenario 3: preemption dispatch + delivery
# ---------------------------------------------------------------------------
def dssim_preemption_delivery(n):
    sim = DSSimulation()
    res = PriorityResource(amount=1, capacity=1, preemptive=True, sim=sim)
    handoff = Queue(sim=sim)  # low holder notifies high preempter each cycle

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
    assert preempted == n, f'preemption-delivery: expected {n} preemptions, got {preempted}'
    assert high_got == n, f'preemption-delivery: expected {n} high acquires, got {high_got}'


def dssim_tiny_preemption_delivery(n):
    sim = DSSimulation(layer2=TinyLayer2)
    res = TinyPriorityResource(amount=1, capacity=1, preemptive=True, sim=sim)
    handoff = sim.tiny_queue(capacity=1)

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
                except TinyPriorityResource.Preempted:
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
    assert preempted == n, f'tiny preemption-delivery: expected {n} preemptions, got {preempted}'
    assert high_got == n, f'tiny preemption-delivery: expected {n} high acquires, got {high_got}'


# ---------------------------------------------------------------------------
# SimPy equivalents
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


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    print(f'Python {sys.version.split()[0]}')
    print(f'Parameters: N={N_EVENTS:,}  waiters={N_WAITERS}  repeats={REPEATS}\n')
    if not _HAS_SIMPY:
        print('SimPy unavailable: skipping SimPy rows.\n')

    print(f'=== Scenario 1: Resource uncontended (N={N_EVENTS:,}) ===')
    report('DSSim Resource', N_EVENTS, *bench(dssim_resource_uncontended, N_EVENTS))
    report('DSSim TinyResource', N_EVENTS, *bench(dssim_tiny_resource_uncontended, N_EVENTS))
    if _HAS_SIMPY:
        report('SimPy Resource', N_EVENTS, *bench(simpy_resource_uncontended, N_EVENTS))

    print(f'\n=== Scenario 2: Priority dispatch (N={N_EVENTS:,}, K={N_WAITERS}) ===')
    n2 = (N_EVENTS // N_WAITERS) * N_WAITERS  # keep divisible
    report('DSSim PriorityResource', n2, *bench(dssim_priority_dispatch, n2, N_WAITERS))
    report('DSSim TinyPriorityResource', n2, *bench(dssim_tiny_priority_dispatch, n2, N_WAITERS))
    if _HAS_SIMPY:
        report('SimPy PriorityResource', n2, *bench(simpy_priority_dispatch, n2, N_WAITERS))

    print(f'\n=== Scenario 3: Preemption delivery (N={N_EVENTS:,}) ===')
    report('DSSim Preemption', N_EVENTS, *bench(dssim_preemption_delivery, N_EVENTS))
    report('DSSim TinyPreemption', N_EVENTS, *bench(dssim_tiny_preemption_delivery, N_EVENTS))
    if _HAS_SIMPY:
        report('SimPy PreemptiveResource', N_EVENTS, *bench(simpy_preemption_delivery, N_EVENTS))

    print()
