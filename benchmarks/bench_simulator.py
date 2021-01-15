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
Benchmark: DSSim simulator core throughput

Six scenarios
-------------
1. timed-callbacks : N events at strictly increasing timestamps dispatched to
                     one generator; stresses schedule_event + time_queue pop/dispatch
2. now-burst       : one generator emits N zero-time events via signal;
                     a second generator consumes them — stresses now_queue append + drain
3. now-chain       : a generator reschedules itself via signal N times;
                     stresses zero-time dispatch with dynamic event generation
4. generator-wakeup: a generator yields N times, woken by N zero-time events from a
                     producer generator; stresses coroutine send path in the loop
5. cross-signal    : two waiting processes alternately wake each other with zero-time
                     signals; stresses mutual blocking/unblocking dispatch path
6. bucketed-burst  : K workers, L time buckets; event i is delivered to
                     worker (i % K) at time (i % L); stresses routed fan-out
                     and many-events-per-time-bucket dispatch

Each scenario is measured for three DSSim configurations:
  - raw        : DSSimulation(layer2=None), schedule_event(), plain yield
  - LiteLayer2 : DSSimulation(layer2=LiteLayer2), sim.schedule(), yield from sim.gwait()
  - PubSubLayer2: DSSimulation(layer2=PubSubLayer2), sim.schedule() → DSProcess,
                  yield from sim.gwait(cond=AlwaysTrue)

SimPy and salabim 23 are included once per scenario for comparison.

Metrics per scenario
--------------------
- events/s  : N / mean wall-clock seconds
- mean ms   : average wall-clock time over REPEATS runs
- min ms    : fastest run (best-case, least OS noise)
'''

import sys
import os
import time
import statistics
import argparse
from contextlib import contextmanager


sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
N_EVENTS = 100_000  # logical events per scenario run
REPEATS  = 20       # independent timed runs; we report mean + min
BUCKET_PROC_COUNT = 10   # K (number of target processes) for scenario 6
BUCKET_COUNT = 100       # L (number of time buckets) for scenario 6

_simpy = None
_salabim = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def bench(fn, *args, **kwargs):
    '''Run fn(*args) REPEATS times; return (min_sec, mean_sec, stdev_sec, total_sec).'''
    times = []
    for _ in range(REPEATS):
        t0 = time.perf_counter()
        fn(*args, **kwargs)
        times.append(time.perf_counter() - t0)
    return min(times), statistics.mean(times), statistics.stdev(times), sum(times)


def report(label, n, min_t, mean_t, stdev_t, total_t):
    print(f'  {label:<26s}  {n/mean_t:>10,.0f} ev/s'
          f'  mean = {mean_t*1e3:7.2f} ± {stdev_t*1e3:3.2f} ms   min = {min_t*1e3:7.2f} ms'
          f'  total = {total_t:6.2f} s')


# ===========================================================================
# DSSim — raw (layer2=None)
# ===========================================================================
from dssim import DSSimulation
from dssim.timequeue import TQBinTree, TQBisect

ACTIVE_TQ_VARIANTS = [('TQBinTree', TQBinTree)]


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


def report_dssim_tq(label, n, fn, *args):
    for tq_name, tq_cls in ACTIVE_TQ_VARIANTS:
        with _with_timequeue(tq_cls):
            report(f'{label} [{tq_name}]', n, *bench(fn, *args))


def dssim_raw_timed_callbacks(n):
    '''
    Schedules N events at strictly increasing timestamps, all dispatched to
    one generator.  Stresses schedule_event + time_queue pop/dispatch.
    '''
    sim = DSSimulation(layer2=None)
    handled = 0

    def sink():
        nonlocal handled
        while True:
            yield
            handled += 1

    consumer = sink()
    sim.schedule_event(0, None, consumer)  # sim.signal(None, consumer) possible, too
    for i in range(n):
        sim.schedule_event(i + 1, i, consumer)
    sim.run()
    assert handled == n, f'raw timed-callbacks: expected {n}, got {handled}'


def dssim_raw_now_burst(n):
    '''
    One scheduled generator emits N zero-time events via signal;
    a second generator consumes them.  Stresses now_queue append + drain.
    '''
    sim = DSSimulation(layer2=None)
    handled = 0

    def sink():
        nonlocal handled
        while True:
            yield
            handled += 1

    def burst(sink_cb):
        for _ in range(n):
            sim.signal(None, sink_cb)

    sink_cb = sink()
    sim.schedule_event(0, None, sink_cb)  # sim.signal(None, sink_cb) possible, too
    burst_cb = burst(sink_cb)
    sim.schedule_event(0, None, burst_cb)  # sim.signal(None, burst_cb) possible, too
    sim.run()
    assert handled == n, f'raw now-burst: expected {n}, got {handled}'


def dssim_raw_now_chain(n):
    '''
    One generator reschedules itself via signal until N iterations.
    Stresses zero-time dispatch with dynamic event generation.
    '''
    sim = DSSimulation(layer2=None)
    fired = 0
    chain_cb = None

    def chain():
        nonlocal fired, chain_cb
        while True:
            yield
            fired += 1
            if fired < n:
                sim.signal(None, chain_cb)

    chain_cb = chain()
    sim.schedule_event(0, None, chain_cb)  # sim.signal(None, chain_cb) possible, too
    sim.schedule_event(0, None, chain_cb)  # pass first yield; sim.signal(None, chain_cb) possible, too
    sim.run()
    assert fired == n, f'raw now-chain: expected {n}, got {fired}'


def dssim_raw_generator_wakeup(n):
    '''
    A generator yields N times; a producer generator schedules N zero-time
    events to it.  Stresses coroutine send path in the simulation loop.
    '''
    sim = DSSimulation(layer2=None)
    received = 0
    waiter_ref = None

    def waiter():
        nonlocal received
        for _ in range(n):
            yield
            received += 1

    def producer():
        for i in range(n):
            sim.signal(i, waiter_ref)

    waiter_ref = waiter()
    sim.schedule_event(0, None, waiter_ref)  # sim.signal(None, waiter_ref) possible, too
    producer_gen = producer()
    sim.schedule_event(0, None, producer_gen)  # sim.signal(None, producer_gen) possible, too
    sim.run()
    assert received == n, f'raw generator-wakeup: expected {n}, got {received}'


def dssim_raw_cross_signal(n):
    '''
    Two generators wait on each other and alternately wake each other via
    signal.  Each received signal counts as one step; total steps == N.
    '''
    sim = DSSimulation(layer2=None)
    total = 0
    a_cb = None
    b_cb = None

    def proc_a():
        nonlocal total, b_cb
        while True:
            yield
            total += 1
            if total < n:
                sim.signal(None, b_cb)

    def proc_b():
        nonlocal total, a_cb
        while True:
            yield
            total += 1
            if total < n:
                sim.signal(None, a_cb)

    a_cb = proc_a()
    b_cb = proc_b()
    sim.schedule_event(0, None, a_cb)  # prime to first yield; sim.signal(None, a_cb) possible, too
    sim.schedule_event(0, None, b_cb)  # prime to first yield; sim.signal(None, b_cb) possible, too
    sim.schedule_event(0, None, a_cb)  # seed ping-pong; sim.signal(None, a_cb) possible, too
    sim.run()
    assert total == n, f'raw cross-signal: expected {n}, got {total}'


def dssim_raw_bucketed_burst(n, k, l):
    '''
    K workers, L time buckets. Event i targets worker (i % K) at time (i % L).
    '''
    sim = DSSimulation(layer2=None)
    process_count = max(1, k)
    bucket_count = max(1, l)
    hits = [0] * process_count
    workers = []

    def worker(idx):
        while True:
            yield
            hits[idx] += 1

    for idx in range(process_count):
        w = worker(idx)
        workers.append(w)
        sim.schedule_event(0, None, w)  # prime worker

    for i in range(n):
        sim.schedule_event(i % bucket_count, i, workers[i % process_count])

    sim.run()
    assert sum(hits) == n, f'raw bucketed-burst: expected {n}, got {sum(hits)}'


# ===========================================================================
# DSSim — LiteLayer2
# ===========================================================================
from dssim import LiteLayer2


def dssim_lite_timed_callbacks(n):
    '''
    Schedules N events at strictly increasing timestamps, all dispatched to
    one generator.  Uses sim.schedule() and yield from sim.gwait().
    '''
    sim = DSSimulation(layer2=LiteLayer2)
    handled = 0

    def sink():
        nonlocal handled
        while True:
            yield from sim.gwait()
            handled += 1

    consumer = sink()
    sim.schedule(0, consumer)           # prime: advances consumer to first gwait
    for i in range(n):
        sim.schedule(i + 1, consumer)   # wake consumer N times
    sim.run()
    assert handled == n, f'lite timed-callbacks: expected {n}, got {handled}'


def dssim_lite_now_burst(n):
    '''
    One scheduled generator emits N zero-time events via signal;
    a second generator consumes them.  Stresses now_queue append + drain.
    '''
    sim = DSSimulation(layer2=LiteLayer2)
    handled = 0

    def sink():
        nonlocal handled
        while True:
            yield from sim.gwait()
            handled += 1

    def burst():
        for _ in range(n):
            sim.signal(None, sink_cb)
        yield from sim.gwait()  # suspend after emitting all events

    sink_cb = sink()
    sim.schedule(0, sink_cb)    # prime sink first so it is ready to receive
    sim.schedule(0, burst())    # burst runs its loop then suspends
    sim.run()
    assert handled == n, f'lite now-burst: expected {n}, got {handled}'


def dssim_lite_now_chain(n):
    '''
    One generator reschedules itself via signal until N iterations.
    Stresses zero-time dispatch with dynamic event generation.
    '''
    sim = DSSimulation(layer2=LiteLayer2)
    fired = 0

    def chain():
        nonlocal fired, chain_cb
        while True:
            yield from sim.gwait()
            fired += 1
            if fired < n:
                sim.signal(None, chain_cb)

    chain_cb = chain()
    sim.schedule(0, chain_cb)   # prime: advances chain_cb to first gwait
    sim.schedule(0, chain_cb)   # trigger first iteration
    sim.run()
    assert fired == n, f'lite now-chain: expected {n}, got {fired}'


def dssim_lite_generator_wakeup(n):
    '''
    A generator yields N times; a producer generator schedules N zero-time
    events to it.  Stresses coroutine send path in the simulation loop.
    '''
    sim = DSSimulation(layer2=LiteLayer2)
    received = 0

    def waiter():
        nonlocal received
        for _ in range(n):
            yield from sim.gwait()
            received += 1

    def producer():
        for i in range(n):
            sim.signal(i, waiter_ref)
        yield from sim.gwait()  # suspend after scheduling all events

    waiter_ref = waiter()
    sim.schedule(0, waiter_ref)  # prime waiter
    sim.schedule(0, producer())  # producer fills now_queue then suspends
    sim.run()
    assert received == n, f'lite generator-wakeup: expected {n}, got {received}'


def dssim_lite_cross_signal(n):
    '''
    Two LiteLayer2 generators alternately wake each other via signal while
    both spend most of their time blocked in gwait().
    '''
    sim = DSSimulation(layer2=LiteLayer2)
    total = 0
    a_cb = None
    b_cb = None

    def proc_a():
        nonlocal total, b_cb
        while True:
            yield from sim.gwait()
            total += 1
            if total < n:
                sim.signal(None, b_cb)

    def proc_b():
        nonlocal total, a_cb
        while True:
            yield from sim.gwait()
            total += 1
            if total < n:
                sim.signal(None, a_cb)

    a_cb = proc_a()
    b_cb = proc_b()
    sim.schedule(0, a_cb)  # prime to first gwait
    sim.schedule(0, b_cb)  # prime to first gwait
    sim.schedule_event(0, None, a_cb) # seed ping-pong
    sim.run()
    assert total == n, f'lite cross-signal: expected {n}, got {total}'


def dssim_lite_bucketed_burst(n, k, l):
    '''
    K workers, L time buckets. Event i targets worker (i % K) at time (i % L).
    LiteLayer2 variant.
    '''
    sim = DSSimulation(layer2=LiteLayer2)
    process_count = max(1, k)
    bucket_count = max(1, l)
    hits = [0] * process_count
    workers = []

    def worker(idx):
        while True:
            yield from sim.gwait()
            hits[idx] += 1

    for idx in range(process_count):
        workers.append(sim.schedule(0, worker(idx)))

    for i in range(n):
        sim.schedule_event(i % bucket_count, i, workers[i % process_count])

    sim.run()
    assert sum(hits) == n, f'lite bucketed-burst: expected {n}, got {sum(hits)}'


# ===========================================================================
# DSSim — PubSubLayer2
# ===========================================================================
from dssim import PubSubLayer2
from dssim.pubsub.base import AlwaysTrue


def dssim_pubsub_timed_callbacks(n):
    '''
    Schedules N events at strictly increasing timestamps, all dispatched to
    one process.  Uses sim.schedule() → DSProcess and yield from sim.gwait(cond=AlwaysTrue).
    '''
    sim = DSSimulation(layer2=PubSubLayer2)
    handled = 0

    def sink():
        nonlocal handled
        while True:
            yield from sim.gwait(cond=AlwaysTrue)
            handled += 1

    consumer = sim.schedule(0, sink())      # returns DSProcess
    for i in range(n):
        sim.schedule_event(i + 1, i, consumer)  # wake the DSProcess N times
    sim.run()
    assert handled == n, f'pubsub timed-callbacks: expected {n}, got {handled}'


def dssim_pubsub_now_burst(n):
    '''
    One scheduled process emits N zero-time events via signal;
    a second process consumes them.  Stresses now_queue append + drain.
    '''
    sim = DSSimulation(layer2=PubSubLayer2)
    handled = 0

    def sink():
        nonlocal handled
        while True:
            yield from sim.gwait(cond=AlwaysTrue)
            handled += 1

    def burst(sink_process):
        for _ in range(n):
            sim.signal(None, sink_process)
        yield from sim.gwait(cond=AlwaysTrue)  # suspend after emitting all events

    sink_process = sim.schedule(0, sink())          # prime sink, get DSProcess
    sim.schedule(0, burst(sink_process))            # burst targets DSProcess
    sim.run()
    assert handled == n, f'pubsub now-burst: expected {n}, got {handled}'


def dssim_pubsub_now_chain(n):
    '''
    One process reschedules itself via signal until N iterations.
    Stresses zero-time dispatch with dynamic event generation.
    '''
    sim = DSSimulation(layer2=PubSubLayer2)
    fired = 0

    def chain():
        nonlocal fired, chain_process
        while True:
            yield from sim.gwait(cond=AlwaysTrue)
            fired += 1
            if fired < n:
                sim.signal(None, chain_process)

    chain_process = sim.schedule(0, chain())    # prime, get DSProcess
    sim.schedule_event(0, None, chain_process)  # add first kick-up; sim.signal(None, chain_process) possible too
    sim.run() 
    assert fired == n, f'pubsub now-chain: expected {n}, got {fired}'


def dssim_pubsub_generator_wakeup(n):
    '''
    A process yields N times; a producer process schedules N zero-time
    events to it.  Stresses coroutine send path in the simulation loop.
    '''
    sim = DSSimulation(layer2=PubSubLayer2)
    received = 0

    def waiter():
        nonlocal received
        for _ in range(n):
            yield from sim.gwait(cond=AlwaysTrue)
            received += 1

    def producer(waiter_process):
        for i in range(n):
            sim.signal(i, waiter_process)
        yield from sim.gwait(cond=AlwaysTrue)  # suspend after scheduling all events

    waiter_process = sim.schedule(0, waiter())      # prime waiter, get DSProcess
    sim.schedule(0, producer(waiter_process))       # producer targets DSProcess
    sim.run()
    assert received == n, f'pubsub generator-wakeup: expected {n}, got {received}'


def dssim_pubsub_cross_signal(n):
    '''
    Two DSProcesses alternately wake each other via signal while both block
    in gwait(cond=AlwaysTrue) between wakeups.
    '''
    sim = DSSimulation(layer2=PubSubLayer2)
    total = 0
    a_proc = None
    b_proc = None

    def proc_a():
        nonlocal total, b_proc
        while True:
            yield from sim.gwait(cond=AlwaysTrue)
            total += 1
            if total < n:
                sim.signal(None, b_proc)

    def proc_b():
        nonlocal total, a_proc
        while True:
            yield from sim.gwait(cond=AlwaysTrue)
            total += 1
            if total < n:
                sim.signal(None, a_proc)

    a_proc = sim.schedule(0, proc_a())      # prime to first gwait
    b_proc = sim.schedule(0, proc_b())      # prime to first gwait
    # Seed via time-queue at t=0 (inserted after starters) so both DSProcesses
    # are initialized before the first cross-signal is delivered.
    sim.schedule_event(0, None, a_proc)  # sim.signal(None, a_proc) possible, too
    sim.run()
    assert total == n, f'pubsub cross-signal: expected {n}, got {total}'


def dssim_pubsub_bucketed_burst(n, k, l):
    '''
    K workers, L time buckets. Event i targets worker (i % K) at time (i % L).
    PubSubLayer2 variant.
    '''
    sim = DSSimulation(layer2=PubSubLayer2)
    process_count = max(1, k)
    bucket_count = max(1, l)
    hits = [0] * process_count
    workers = []

    def worker(idx):
        while True:
            yield from sim.gwait(cond=AlwaysTrue)
            hits[idx] += 1

    for idx in range(process_count):
        workers.append(sim.schedule(0, worker(idx)))

    for i in range(n):
        sim.schedule_event(i % bucket_count, i, workers[i % process_count])

    sim.run()
    assert sum(hits) == n, f'pubsub bucketed-burst: expected {n}, got {sum(hits)}'


# ===========================================================================
# SimPy
# ===========================================================================
def simpy_timed_callbacks(n):
    '''
    N SimPy timeout events at strictly increasing times dispatched via callbacks.
    '''
    env = _simpy.Environment()
    handled = 0

    def sink(event):
        nonlocal handled
        handled += 1

    for i in range(n):
        ev = env.timeout(i + 1, value=i)
        ev.callbacks.append(sink)
    env.run()
    assert handled == n, f'simpy timed-callbacks: expected {n}, got {handled}'


def simpy_now_burst(n):
    '''
    A seed callback emits N timeout(0) events; a second callback counts each.
    '''
    env = _simpy.Environment()
    handled = 0

    def sink(event):
        nonlocal handled
        handled += 1

    def burst(event):
        for _ in range(n):
            ev = env.timeout(0)
            ev.callbacks.append(sink)

    seed = env.timeout(0)
    seed.callbacks.append(burst)
    env.run()
    assert handled == n, f'simpy now-burst: expected {n}, got {handled}'


def simpy_now_chain(n):
    '''
    A callback reschedules itself via timeout(0) until N iterations.
    '''
    env = _simpy.Environment()
    fired = 0

    def chain(event):
        nonlocal fired
        fired += 1
        if fired < n:
            ev = env.timeout(0)
            ev.callbacks.append(chain)

    seed = env.timeout(0)
    seed.callbacks.append(chain)
    env.run()
    assert fired == n, f'simpy now-chain: expected {n}, got {fired}'


def simpy_process_wakeup(n):
    '''
    A SimPy process waits on a shared event N times; producer recreates and
    triggers the event each iteration with timeout(0) between each.
    '''
    env = _simpy.Environment()
    received = 0
    wakeup = env.event()

    def waiter():
        nonlocal received, wakeup
        for _ in range(n):
            yield wakeup
            received += 1
            wakeup = env.event()

    def producer():
        for i in range(n):
            wakeup.succeed(i)
            yield env.timeout(0)

    env.process(waiter())
    env.process(producer())
    env.run()
    assert received == n, f'simpy process-wakeup: expected {n}, got {received}'


def simpy_cross_signal(n):
    '''
    Two SimPy processes alternately wake each other by succeeding each
    other's event, then block again on a fresh event.
    '''
    env = _simpy.Environment()
    total = {'n': 0}
    wake = {'a': env.event(), 'b': env.event()}

    def proc_a():
        while True:
            yield wake['a']
            wake['a'] = env.event()
            total['n'] += 1
            if total['n'] < n:
                wake['b'].succeed(None)
            else:
                break

    def proc_b():
        while True:
            yield wake['b']
            wake['b'] = env.event()
            total['n'] += 1
            if total['n'] < n:
                wake['a'].succeed(None)
            else:
                break

    env.process(proc_a())
    env.process(proc_b())
    wake['a'].succeed(None)  # seed ping-pong
    env.run()
    assert total['n'] == n, f'simpy cross-signal: expected {n}, got {total["n"]}'


def simpy_bucketed_burst(n, k, l):
    '''
    K workers, L time buckets. Event i targets worker (i % K) at time (i % L).
    SimPy variant.
    '''
    from collections import deque
    env = _simpy.Environment()
    process_count = max(1, k)
    bucket_count = max(1, l)
    hits = [0] * process_count
    mailboxes = [deque() for _ in range(process_count)]
    wakeup = [env.event() for _ in range(process_count)]

    def worker(idx):
        while True:
            if not mailboxes[idx]:
                ev = wakeup[idx]
                yield ev
                wakeup[idx] = env.event()
            while mailboxes[idx]:
                mailboxes[idx].popleft()
                hits[idx] += 1

    def deliver(idx, payload):
        # callback invoked when timeout fires
        was_empty = not mailboxes[idx]
        mailboxes[idx].append(payload)
        if was_empty and not wakeup[idx].triggered:
            wakeup[idx].succeed(None)

    for idx in range(process_count):
        env.process(worker(idx))

    for i in range(n):
        target = i % process_count
        ev = env.timeout(i % bucket_count, value=i)
        ev.callbacks.append(lambda event, idx=target, val=i: deliver(idx, val))

    env.run()
    assert sum(hits) == n, f'simpy bucketed-burst: expected {n}, got {sum(hits)}'


# ===========================================================================
# salabim 23
# ===========================================================================
def salabim_timed_callbacks(n):
    '''
    DSTimer component holds 1 time unit, activates Sink, repeats N times.
    Sink passivates between wakeups.  Stresses salabim's time-queue and the
    passivate/activate path.
    '''
    env = _salabim.Environment(trace=False)
    handled = [0]
    sink_ref = [None]

    class Sink(_salabim.Component):
        def process(self):
            while True:
                yield self.passivate()
                handled[0] += 1

    class DSTimer(_salabim.Component):
        def process(self):
            for _ in range(n):
                yield self.hold(1)
                sink_ref[0].activate()

    sink_ref[0] = Sink(env=env)
    DSTimer(env=env)
    env.run()
    assert handled[0] == n, f'salabim timed-callbacks: expected {n}, got {handled[0]}'


def salabim_now_burst(n):
    '''
    Burst component activates Sink N times with zero-time holds between each
    activation to allow Sink to run.  Stresses zero-time scheduling.
    Note: salabim has no direct "fire N events from one component to another
    without yielding" path; hold(0) is the idiomatic zero-time yield point.
    '''
    env = _salabim.Environment(trace=False)
    handled = [0]
    sink_ref = [None]

    class Sink(_salabim.Component):
        def process(self):
            for _ in range(n):
                yield self.passivate()
                handled[0] += 1

    class Burst(_salabim.Component):
        def process(self):
            for _ in range(n):
                sink_ref[0].activate()
                yield self.hold(0)

    sink_ref[0] = Sink(env=env)
    Burst(env=env)
    env.run()
    assert handled[0] == n, f'salabim now-burst: expected {n}, got {handled[0]}'


def salabim_now_chain(n):
    '''
    Chain component reschedules itself N times via hold(0).
    Stresses zero-time event processing with a single active component.
    '''
    env = _salabim.Environment(trace=False)
    fired = [0]

    class Chain(_salabim.Component):
        def process(self):
            for _ in range(n):
                yield self.hold(0)
                fired[0] += 1

    Chain(env=env)
    env.run()
    assert fired[0] == n, f'salabim now-chain: expected {n}, got {fired[0]}'


def salabim_generator_wakeup(n):
    '''
    Waiter passivates N times; Producer activates it once per hold(0) step.
    Stresses the passivate/activate interleaving path.
    '''
    env = _salabim.Environment(trace=False)
    received = [0]
    waiter_ref = [None]

    class Waiter(_salabim.Component):
        def process(self):
            for _ in range(n):
                yield self.passivate()
                received[0] += 1

    class Producer(_salabim.Component):
        def process(self):
            for _ in range(n):
                waiter_ref[0].activate()
                yield self.hold(0)

    waiter_ref[0] = Waiter(env=env)
    Producer(env=env)
    env.run()
    assert received[0] == n, f'salabim generator-wakeup: expected {n}, got {received[0]}'


def salabim_cross_signal(n):
    '''
    Two components passivate and alternately activate each other; each
    activation counts as one step until N total steps.
    '''
    env = _salabim.Environment(trace=False)
    total = [0]
    a_ref = [None]
    b_ref = [None]

    class A(_salabim.Component):
        def process(self):
            while True:
                yield self.passivate()
                total[0] += 1
                if total[0] < n:
                    b_ref[0].activate()
                else:
                    break

    class B(_salabim.Component):
        def process(self):
            while True:
                yield self.passivate()
                total[0] += 1
                if total[0] < n:
                    a_ref[0].activate()
                else:
                    break

    if n <= 0:
        return

    class Seeder(_salabim.Component):
        def process(self):
            # Let A and B reach passivate() first, then seed the first wakeup.
            yield self.hold(0)
            a_ref[0].activate()

    a_ref[0] = A(env=env)
    b_ref[0] = B(env=env)
    Seeder(env=env)
    env.run()
    assert total[0] == n, f'salabim cross-signal: expected {n}, got {total[0]}'


def salabim_bucketed_burst(n, k, l):
    '''
    K workers, L time buckets. Event i targets worker (i % K) at time (i % L).
    '''
    env = _salabim.Environment(trace=False)
    process_count = max(1, k)
    bucket_count = max(1, l)
    hits = [0] * process_count
    pending = [0] * process_count
    workers = []

    class Worker(_salabim.Component):
        def setup(self, idx):
            self.idx = idx

        def process(self):
            while True:
                yield self.passivate()
                while pending[self.idx] > 0:
                    pending[self.idx] -= 1
                    hits[self.idx] += 1

    class Scheduler(_salabim.Component):
        def process(self):
            buckets = [[] for _ in range(bucket_count)]
            for i in range(n):
                buckets[i % bucket_count].append(i % process_count)
            for t in range(bucket_count):
                if t > 0:
                    yield self.hold(1)
                for idx in buckets[t]:
                    was_zero = pending[idx] == 0
                    pending[idx] += 1
                    if was_zero:
                        workers[idx].activate()

    for idx in range(process_count):
        workers.append(Worker(env=env, idx=idx))

    Scheduler(env=env)
    env.run()
    assert sum(hits) == n, f'salabim bucketed-burst: expected {n}, got {sum(hits)}'


# ===========================================================================
# main
# ===========================================================================
def _parse_args():
    parser = argparse.ArgumentParser(
        description='Simulator benchmark (DSSim by default, optional SimPy/salabim via flags).',
    )
    parser.add_argument(
        '--scenario',
        choices=['all', 'timed-callbacks', 'now-burst', 'now-chain', 'generator-wakeup', 'cross-signal', 'bucketed-burst'],
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
            import simpy as _simpy_mod
            _simpy = _simpy_mod
            run_simpy = True
        except Exception as exc:
            print(f'SimPy requested but unavailable: {exc}')

    if args.with_salabim:
        try:
            import salabim as _salabim_mod
            _salabim = _salabim_mod
            _salabim.yieldless(False)
            run_salabim = True
        except Exception as exc:
            print(f'salabim requested but unavailable: {exc}')

    print(f'Python {sys.version.split()[0]}')
    print(f'Parameters: N={N_EVENTS:,}  repeats={REPEATS}  K={BUCKET_PROC_COUNT}  L={BUCKET_COUNT}\n')
    run_all = args.scenario == 'all'

    # ---- scenario 1 --------------------------------------------------------
    if run_all or args.scenario == 'timed-callbacks':
        print(f'=== Scenario 1: timed-callbacks  (N={N_EVENTS:,}) ===')
        if ACTIVE_TQ_VARIANTS:
            report_dssim_tq('DSSim raw        ', N_EVENTS, dssim_raw_timed_callbacks, N_EVENTS)
        if args.with_dssim_lite and ACTIVE_TQ_VARIANTS:
            report_dssim_tq('DSSim LiteLayer2 ', N_EVENTS, dssim_lite_timed_callbacks, N_EVENTS)
        if args.with_dssim_pubsub and ACTIVE_TQ_VARIANTS:
            report_dssim_tq('DSSim PubSub     ', N_EVENTS, dssim_pubsub_timed_callbacks, N_EVENTS)
        if run_simpy:
            report('SimPy            ', N_EVENTS, *bench(simpy_timed_callbacks,         N_EVENTS))
        if run_salabim:
            report('salabim          ', N_EVENTS, *bench(salabim_timed_callbacks,       N_EVENTS))

    # ---- scenario 2 --------------------------------------------------------
    if run_all or args.scenario == 'now-burst':
        print(f'\n=== Scenario 2: now-burst  (1 burst → N zero-time events, N={N_EVENTS:,}) ===')
        if ACTIVE_TQ_VARIANTS:
            report_dssim_tq('DSSim raw        ', N_EVENTS, dssim_raw_now_burst, N_EVENTS)
        if args.with_dssim_lite and ACTIVE_TQ_VARIANTS:
            report_dssim_tq('DSSim LiteLayer2 ', N_EVENTS, dssim_lite_now_burst, N_EVENTS)
        if args.with_dssim_pubsub and ACTIVE_TQ_VARIANTS:
            report_dssim_tq('DSSim PubSub     ', N_EVENTS, dssim_pubsub_now_burst, N_EVENTS)
        if run_simpy:
            report('SimPy            ', N_EVENTS, *bench(simpy_now_burst,         N_EVENTS))
        if run_salabim:
            report('salabim          ', N_EVENTS, *bench(salabim_now_burst,       N_EVENTS))

    # ---- scenario 3 --------------------------------------------------------
    if run_all or args.scenario == 'now-chain':
        print(f'\n=== Scenario 3: now-chain  (self-rescheduling, N={N_EVENTS:,}) ===')
        if ACTIVE_TQ_VARIANTS:
            report_dssim_tq('DSSim raw        ', N_EVENTS, dssim_raw_now_chain, N_EVENTS)
        if args.with_dssim_lite and ACTIVE_TQ_VARIANTS:
            report_dssim_tq('DSSim LiteLayer2 ', N_EVENTS, dssim_lite_now_chain, N_EVENTS)
        if args.with_dssim_pubsub and ACTIVE_TQ_VARIANTS:
            report_dssim_tq('DSSim PubSub     ', N_EVENTS, dssim_pubsub_now_chain, N_EVENTS)
        if run_simpy:
            report('SimPy            ', N_EVENTS, *bench(simpy_now_chain,         N_EVENTS))
        if run_salabim:
            report('salabim          ', N_EVENTS, *bench(salabim_now_chain,       N_EVENTS))

    # ---- scenario 4 --------------------------------------------------------
    if run_all or args.scenario == 'generator-wakeup':
        print(f'\n=== Scenario 4: generator-wakeup  (1 waiter + 1 producer, N={N_EVENTS:,}) ===')
        if ACTIVE_TQ_VARIANTS:
            report_dssim_tq('DSSim raw        ', N_EVENTS, dssim_raw_generator_wakeup, N_EVENTS)
        if args.with_dssim_lite and ACTIVE_TQ_VARIANTS:
            report_dssim_tq('DSSim LiteLayer2 ', N_EVENTS, dssim_lite_generator_wakeup, N_EVENTS)
        if args.with_dssim_pubsub and ACTIVE_TQ_VARIANTS:
            report_dssim_tq('DSSim PubSub     ', N_EVENTS, dssim_pubsub_generator_wakeup, N_EVENTS)
        if run_simpy:
            report('SimPy            ', N_EVENTS, *bench(simpy_process_wakeup,           N_EVENTS))
        if run_salabim:
            report('salabim          ', N_EVENTS, *bench(salabim_generator_wakeup,       N_EVENTS))

    # ---- scenario 5 --------------------------------------------------------
    if run_all or args.scenario == 'cross-signal':
        print(f'\n=== Scenario 5: cross-signal  (2 waiting peers ping-pong, N={N_EVENTS:,}) ===')
        if ACTIVE_TQ_VARIANTS:
            report_dssim_tq('DSSim raw        ', N_EVENTS, dssim_raw_cross_signal, N_EVENTS)
        if args.with_dssim_lite and ACTIVE_TQ_VARIANTS:
            report_dssim_tq('DSSim LiteLayer2 ', N_EVENTS, dssim_lite_cross_signal, N_EVENTS)
        if args.with_dssim_pubsub and ACTIVE_TQ_VARIANTS:
            report_dssim_tq('DSSim PubSub     ', N_EVENTS, dssim_pubsub_cross_signal, N_EVENTS)
        if run_simpy:
            report('SimPy            ', N_EVENTS, *bench(simpy_cross_signal,         N_EVENTS))
        if run_salabim:
            report('salabim          ', N_EVENTS, *bench(salabim_cross_signal,       N_EVENTS))

    # ---- scenario 6 --------------------------------------------------------
    if run_all or args.scenario == 'bucketed-burst':
        print(f'\n=== Scenario 6: bucketed-burst  (K={BUCKET_PROC_COUNT}, L={BUCKET_COUNT}, N={N_EVENTS:,}) ===')
        if ACTIVE_TQ_VARIANTS:
            report_dssim_tq('DSSim raw        ', N_EVENTS, dssim_raw_bucketed_burst, N_EVENTS, BUCKET_PROC_COUNT, BUCKET_COUNT)
        if args.with_dssim_lite and ACTIVE_TQ_VARIANTS:
            report_dssim_tq('DSSim LiteLayer2 ', N_EVENTS, dssim_lite_bucketed_burst, N_EVENTS, BUCKET_PROC_COUNT, BUCKET_COUNT)
        if args.with_dssim_pubsub and ACTIVE_TQ_VARIANTS:
            report_dssim_tq('DSSim PubSub     ', N_EVENTS, dssim_pubsub_bucketed_burst, N_EVENTS, BUCKET_PROC_COUNT, BUCKET_COUNT)
        if run_simpy:
            report('SimPy            ', N_EVENTS, *bench(simpy_bucketed_burst,        N_EVENTS, BUCKET_PROC_COUNT, BUCKET_COUNT))
        if run_salabim:
            report('salabim          ', N_EVENTS, *bench(salabim_bucketed_burst,      N_EVENTS, BUCKET_PROC_COUNT, BUCKET_COUNT))

    print()
