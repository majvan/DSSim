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

Five scenarios
--------------
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

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
N_EVENTS = 100_000  # logical events per scenario run
REPEATS  = 20       # independent timed runs; we report mean + min


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
    sim.schedule_event(0, None, consumer)
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
    sim.schedule_event(0, None, sink_cb)
    burst_cb = burst(sink_cb)
    sim.schedule_event(0, None, burst_cb)
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
    sim.schedule_event(0, None, chain_cb)
    sim.schedule_event(0, None, chain_cb)  # pass first yield
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
    sim.schedule_event(0, None, waiter_ref)
    producer_gen = producer()
    sim.schedule_event(0, None, producer_gen)
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
    sim.schedule_event(0, None, a_cb)  # prime to first yield
    sim.schedule_event(0, None, b_cb)  # prime to first yield
    sim.signal(None, a_cb)             # seed ping-pong
    sim.run()
    assert total == n, f'raw cross-signal: expected {n}, got {total}'


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
    sim.signal(None, a_cb) # seed ping-pong
    sim.run()
    assert total == n, f'lite cross-signal: expected {n}, got {total}'


# ===========================================================================
# DSSim — PubSubLayer2
# ===========================================================================
from dssim import PubSubLayer2
from dssim.pubsub_base import AlwaysTrue


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
    sim.schedule_event(0, None, chain_process)  # trigger first iteration
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
    sim.schedule_event(0, None, a_proc)
    sim.run()
    assert total == n, f'pubsub cross-signal: expected {n}, got {total}'


# ===========================================================================
# SimPy
# ===========================================================================
import simpy as _simpy


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


# ===========================================================================
# salabim 23
# ===========================================================================
import salabim as _salabim
_salabim.yieldless(False)


def salabim_timed_callbacks(n):
    '''
    Timer component holds 1 time unit, activates Sink, repeats N times.
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

    class Timer(_salabim.Component):
        def process(self):
            for _ in range(n):
                yield self.hold(1)
                sink_ref[0].activate()

    sink_ref[0] = Sink(env=env)
    Timer(env=env)
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


# ===========================================================================
# main
# ===========================================================================
if __name__ == '__main__':
    print(f'Python {sys.version.split()[0]}')
    print(f'Parameters: N={N_EVENTS:,}  repeats={REPEATS}\n')

    # ---- scenario 1 --------------------------------------------------------
    print(f'=== Scenario 1: timed-callbacks  (N={N_EVENTS:,}) ===')
    report('DSSim raw        ', N_EVENTS, *bench(dssim_raw_timed_callbacks,    N_EVENTS))
    report('DSSim LiteLayer2 ', N_EVENTS, *bench(dssim_lite_timed_callbacks,   N_EVENTS))
    report('DSSim PubSub     ', N_EVENTS, *bench(dssim_pubsub_timed_callbacks, N_EVENTS))
    report('SimPy            ', N_EVENTS, *bench(simpy_timed_callbacks,         N_EVENTS))
    report('salabim          ', N_EVENTS, *bench(salabim_timed_callbacks,       N_EVENTS))

    # ---- scenario 2 --------------------------------------------------------
    print(f'\n=== Scenario 2: now-burst  (1 burst → N zero-time events, N={N_EVENTS:,}) ===')
    report('DSSim raw        ', N_EVENTS, *bench(dssim_raw_now_burst,    N_EVENTS))
    report('DSSim LiteLayer2 ', N_EVENTS, *bench(dssim_lite_now_burst,   N_EVENTS))
    report('DSSim PubSub     ', N_EVENTS, *bench(dssim_pubsub_now_burst, N_EVENTS))
    report('SimPy            ', N_EVENTS, *bench(simpy_now_burst,         N_EVENTS))
    report('salabim          ', N_EVENTS, *bench(salabim_now_burst,       N_EVENTS))

    # ---- scenario 3 --------------------------------------------------------
    print(f'\n=== Scenario 3: now-chain  (self-rescheduling, N={N_EVENTS:,}) ===')
    report('DSSim raw        ', N_EVENTS, *bench(dssim_raw_now_chain,    N_EVENTS))
    report('DSSim LiteLayer2 ', N_EVENTS, *bench(dssim_lite_now_chain,   N_EVENTS))
    report('DSSim PubSub     ', N_EVENTS, *bench(dssim_pubsub_now_chain, N_EVENTS))
    report('SimPy            ', N_EVENTS, *bench(simpy_now_chain,         N_EVENTS))
    report('salabim          ', N_EVENTS, *bench(salabim_now_chain,       N_EVENTS))

    # ---- scenario 4 --------------------------------------------------------
    print(f'\n=== Scenario 4: generator-wakeup  (1 waiter + 1 producer, N={N_EVENTS:,}) ===')
    report('DSSim raw        ', N_EVENTS, *bench(dssim_raw_generator_wakeup,    N_EVENTS))
    report('DSSim LiteLayer2 ', N_EVENTS, *bench(dssim_lite_generator_wakeup,   N_EVENTS))
    report('DSSim PubSub     ', N_EVENTS, *bench(dssim_pubsub_generator_wakeup, N_EVENTS))
    report('SimPy            ', N_EVENTS, *bench(simpy_process_wakeup,           N_EVENTS))
    report('salabim          ', N_EVENTS, *bench(salabim_generator_wakeup,       N_EVENTS))

    # ---- scenario 5 --------------------------------------------------------
    print(f'\n=== Scenario 5: cross-signal  (2 waiting peers ping-pong, N={N_EVENTS:,}) ===')
    report('DSSim raw        ', N_EVENTS, *bench(dssim_raw_cross_signal,    N_EVENTS))
    report('DSSim LiteLayer2 ', N_EVENTS, *bench(dssim_lite_cross_signal,   N_EVENTS))
    report('DSSim PubSub     ', N_EVENTS, *bench(dssim_pubsub_cross_signal, N_EVENTS))
    report('SimPy            ', N_EVENTS, *bench(simpy_cross_signal,         N_EVENTS))
    report('salabim          ', N_EVENTS, *bench(salabim_cross_signal,       N_EVENTS))

    print()
