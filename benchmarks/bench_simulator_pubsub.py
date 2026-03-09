#!/usr/bin/env python3
'''
Benchmark: DSSim simulator core throughput — PubSubLayer2 variant

Identical scenarios to bench_simulator_tiny.py but uses
DSSimulation(layer2=PubSubLayer2), which is the full default stack including
SimPubsubMixin, SimProcessMixin, SimFutureMixin, etc.

With PubSubLayer2, sim.schedule(time, generator) wraps the generator in a
DSProcess and returns it.  schedule_event_now must target the DSProcess, not
the raw generator, so each scenario captures the returned process reference.

Four scenarios
--------------
1. timed-callbacks : N events at strictly increasing timestamps dispatched to
                     one process; stresses schedule_event + time_queue pop/dispatch
2. now-burst       : one process emits N zero-time events via schedule_event_now;
                     a second process consumes them — stresses now_queue append + drain
3. now-chain       : a process reschedules itself via schedule_event_now N times;
                     stresses zero-time dispatch with dynamic event generation
4. generator-wakeup: a process yields N times, woken by N zero-time events from a
                     producer process; stresses coroutine send path in the loop

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
    print(f'  {label:<38s}  {n/mean_t:>10,.0f} ev/s'
          f'  mean = {mean_t*1e3:7.2f} ± {stdev_t*1e3:3.2f} ms   min = {min_t*1e3:7.2f} ms'
          f'  total = {total_t:6.2f} s')


# ===========================================================================
# DSSim — PubSubLayer2
# ===========================================================================
from dssim import DSSimulation, PubSubLayer2
from dssim.pubsub_base import AlwaysTrue


def dssim_timed_callbacks(n):
    '''
    Schedules N events at strictly increasing timestamps, all dispatched to
    one process.  Stresses schedule_event + time_queue pop/dispatch.
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
    assert handled == n, f'timed-callbacks: expected {n}, got {handled}'


def dssim_now_burst(n):
    '''
    One scheduled process emits N zero-time events via schedule_event_now;
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
            sim.schedule_event_now(None, sink_process)
        yield from sim.gwait(cond=AlwaysTrue)  # suspend after emitting all events

    sink_process = sim.schedule(0, sink())          # prime sink, get DSProcess
    sim.schedule(0, burst(sink_process))            # burst targets DSProcess
    sim.run()
    assert handled == n, f'now-burst: expected {n}, got {handled}'


def dssim_now_chain(n):
    '''
    One process reschedules itself via schedule_event_now until N iterations.
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
                sim.schedule_event_now(None, chain_process)

    chain_process = sim.schedule(0, chain())    # prime, get DSProcess
    sim.schedule_event(0, None, chain_process)  # trigger first iteration
    sim.run()
    assert fired == n, f'now-chain: expected {n}, got {fired}'


def dssim_generator_wakeup(n):
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
            sim.schedule_event_now(i, waiter_process)
        yield from sim.gwait(cond=AlwaysTrue)  # suspend after scheduling all events

    waiter_process = sim.schedule(0, waiter())      # prime waiter, get DSProcess
    sim.schedule(0, producer(waiter_process))       # producer targets DSProcess
    sim.run()
    assert received == n, f'generator-wakeup: expected {n}, got {received}'


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


# ===========================================================================
# main
# ===========================================================================
if __name__ == '__main__':
    print(f'Python {sys.version.split()[0]}')
    print(f'Parameters: N={N_EVENTS:,}  repeats={REPEATS}\n')

    # ---- scenario 1 --------------------------------------------------------
    print(f'=== Scenario 1: timed-callbacks  (1 process, N={N_EVENTS:,}) ===')
    report('DSSim PubSubLayer2', N_EVENTS, *bench(dssim_timed_callbacks, N_EVENTS))
    report('SimPy',              N_EVENTS, *bench(simpy_timed_callbacks, N_EVENTS))

    # ---- scenario 2 --------------------------------------------------------
    print(f'\n=== Scenario 2: now-burst  (1 burst → N zero-time events, N={N_EVENTS:,}) ===')
    report('DSSim PubSubLayer2', N_EVENTS, *bench(dssim_now_burst, N_EVENTS))
    report('SimPy',              N_EVENTS, *bench(simpy_now_burst, N_EVENTS))

    # ---- scenario 3 --------------------------------------------------------
    print(f'\n=== Scenario 3: now-chain  (self-rescheduling process, N={N_EVENTS:,}) ===')
    report('DSSim PubSubLayer2', N_EVENTS, *bench(dssim_now_chain, N_EVENTS))
    report('SimPy',              N_EVENTS, *bench(simpy_now_chain, N_EVENTS))

    # ---- scenario 4 --------------------------------------------------------
    print(f'\n=== Scenario 4: generator-wakeup  (1 waiter + 1 producer, N={N_EVENTS:,}) ===')
    report('DSSim PubSubLayer2', N_EVENTS, *bench(dssim_generator_wakeup, N_EVENTS))
    report('SimPy',              N_EVENTS, *bench(simpy_process_wakeup, N_EVENTS))

    print()
