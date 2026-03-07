#!/usr/bin/env python3
'''
Benchmark: DSSim simulator core throughput

Four scenarios
--------------
1. timed-callbacks : N events at strictly increasing timestamps dispatched to
                     one DSCallback; stresses schedule_event + time_queue pop/dispatch
2. now-burst       : one callback emits N zero-time events via schedule_event_now;
                     a second callback consumes them — stresses now_queue append + drain
3. now-chain       : a callback reschedules itself via schedule_event_now N times;
                     stresses zero-time dispatch with dynamic event generation
4. process-wakeup  : a DSProcess does N gwait wakeups driven by N zero-time events;
                     stresses process condition checks + send path in the loop

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
# DSSim
# ===========================================================================
from dssim import DSCallback, DSSimulation


def dssim_timed_callbacks(n):
    '''
    Schedules N events at strictly increasing timestamps, all dispatched to
    one DSCallback.  Stresses schedule_event + time_queue pop/dispatch.
    '''
    sim = DSSimulation()
    handled = [0]

    def sink(event):
        handled[0] += 1
        return True

    consumer = DSCallback(sink, sim=sim)
    for i in range(n):
        sim.schedule_event(i + 1, i, consumer)
    sim.run()
    assert handled[0] == n, f'timed-callbacks: expected {n}, got {handled[0]}'


def dssim_now_burst(n):
    '''
    One scheduled callback emits N zero-time events via schedule_event_now;
    a second callback consumes them.  Stresses now_queue append + drain.
    '''
    sim = DSSimulation()
    handled = [0]

    def sink(event):
        handled[0] += 1
        return True

    sink_cb = DSCallback(sink, sim=sim)

    def burst(event):
        for _ in range(n):
            sim.schedule_event_now(None, sink_cb)
        return True

    burst_cb = DSCallback(burst, sim=sim)
    sim.schedule_event(0, None, burst_cb)
    sim.run()
    assert handled[0] == n, f'now-burst: expected {n}, got {handled[0]}'


def dssim_now_chain(n):
    '''
    One callback reschedules itself via schedule_event_now until N iterations.
    Stresses zero-time dispatch with dynamic event generation.
    '''
    sim = DSSimulation()
    fired = [0]

    def chain(event):
        fired[0] += 1
        if fired[0] < n:
            sim.schedule_event_now(None, chain_cb)
        return True

    chain_cb = DSCallback(chain, sim=sim)
    sim.schedule_event(0, None, chain_cb)
    sim.run()
    assert fired[0] == n, f'now-chain: expected {n}, got {fired[0]}'


def dssim_process_wakeup(n):
    '''
    A DSProcess does N gwait wakeups; a callback emits N zero-time events to
    that process.  Stresses process condition checks + send path in the loop.
    '''
    sim = DSSimulation()
    received = [0]

    def waiter():
        cond = lambda _event: True
        for _ in range(n):
            yield from sim.gwait(cond=cond)
            received[0] += 1

    process = sim.process(waiter()).schedule(0)

    def producer(event):
        for i in range(n):
            sim.schedule_event_now(i, process)
        return True

    producer_cb = DSCallback(producer, sim=sim)
    sim.schedule_event(0, None, producer_cb)
    sim.run()
    assert received[0] == n, f'process-wakeup: expected {n}, got {received[0]}'


# ===========================================================================
# SimPy
# ===========================================================================
import simpy as _simpy


def simpy_timed_callbacks(n):
    '''
    N SimPy timeout events at strictly increasing times dispatched via callbacks.
    '''
    env = _simpy.Environment()
    handled = [0]

    def sink(event):
        handled[0] += 1

    for i in range(n):
        ev = env.timeout(i + 1, value=i)
        ev.callbacks.append(sink)
    env.run()
    assert handled[0] == n, f'simpy timed-callbacks: expected {n}, got {handled[0]}'


def simpy_now_burst(n):
    '''
    A seed callback emits N timeout(0) events; a second callback counts each.
    '''
    env = _simpy.Environment()
    handled = [0]

    def sink(event):
        handled[0] += 1

    def burst(event):
        for _ in range(n):
            ev = env.timeout(0)
            ev.callbacks.append(sink)

    seed = env.timeout(0)
    seed.callbacks.append(burst)
    env.run()
    assert handled[0] == n, f'simpy now-burst: expected {n}, got {handled[0]}'


def simpy_now_chain(n):
    '''
    A callback reschedules itself via timeout(0) until N iterations.
    '''
    env = _simpy.Environment()
    fired = [0]

    def chain(event):
        fired[0] += 1
        if fired[0] < n:
            ev = env.timeout(0)
            ev.callbacks.append(chain)

    seed = env.timeout(0)
    seed.callbacks.append(chain)
    env.run()
    assert fired[0] == n, f'simpy now-chain: expected {n}, got {fired[0]}'


def simpy_process_wakeup(n):
    '''
    A SimPy process waits on a shared event N times; producer recreates and
    triggers the event each iteration with timeout(0) between each.
    '''
    env = _simpy.Environment()
    received = [0]
    wakeup = [env.event()]

    def waiter():
        for _ in range(n):
            yield wakeup[0]
            received[0] += 1
            wakeup[0] = env.event()

    def producer():
        for i in range(n):
            wakeup[0].succeed(i)
            yield env.timeout(0)

    env.process(waiter())
    env.process(producer())
    env.run()
    assert received[0] == n, f'simpy process-wakeup: expected {n}, got {received[0]}'


# ===========================================================================
# main
# ===========================================================================
if __name__ == '__main__':
    print(f'Python {sys.version.split()[0]}')
    print(f'Parameters: N={N_EVENTS:,}  repeats={REPEATS}\n')

    # ---- scenario 1 --------------------------------------------------------
    print(f'=== Scenario 1: timed-callbacks  (1 callback, N={N_EVENTS:,}) ===')
    report('DSSim', N_EVENTS, *bench(dssim_timed_callbacks, N_EVENTS))
    report('SimPy', N_EVENTS, *bench(simpy_timed_callbacks, N_EVENTS))

    # ---- scenario 2 --------------------------------------------------------
    print(f'\n=== Scenario 2: now-burst  (1 burst → N zero-time events, N={N_EVENTS:,}) ===')
    report('DSSim', N_EVENTS, *bench(dssim_now_burst, N_EVENTS))
    report('SimPy', N_EVENTS, *bench(simpy_now_burst, N_EVENTS))

    # ---- scenario 3 --------------------------------------------------------
    print(f'\n=== Scenario 3: now-chain  (self-rescheduling callback, N={N_EVENTS:,}) ===')
    report('DSSim', N_EVENTS, *bench(dssim_now_chain, N_EVENTS))
    report('SimPy', N_EVENTS, *bench(simpy_now_chain, N_EVENTS))

    # ---- scenario 4 --------------------------------------------------------
    print(f'\n=== Scenario 4: process-wakeup  (1 process + 1 producer, N={N_EVENTS:,}) ===')
    report('DSSim', N_EVENTS, *bench(dssim_process_wakeup, N_EVENTS))
    report('SimPy', N_EVENTS, *bench(simpy_process_wakeup, N_EVENTS))

    print()
