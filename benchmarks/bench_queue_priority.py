#!/usr/bin/env python3
'''
Benchmark: Priority queue throughput — DSSim vs SimPy

Three scenarios stress different parts of the priority queue path:

1. fill-drain    : N items inserted in worst-case priority order (largest key
                   first so every heappush must sift), then fully drained.
                   DSSim uses put_nowait + get_nowait — no simulation loop at
                   all.  SimPy has no nowait API; even a simple bulk insert
                   must go through the event machinery (process + env.run()).

2. burst         : A producer and a consumer run concurrently inside the
                   simulation loop.  The producer inserts N items back-to-back
                   (queue has unlimited capacity so puts never block); the
                   consumer drains them one-by-one.
                   DSSim is shown in two variants:
                     put_nowait + gget  — producer bypasses simulation loop
                     gput       + gget  — producer uses the blocking-put API
                                          (gput still returns immediately since
                                          capacity is unlimited, but it still
                                          goes through check_and_gwait machinery)

3. bounded       : Queue capacity = 1 forces strict put / get alternation.
                   Every gput / store.put blocks until the consumer takes
                   the current item, stressing the block/unblock path.

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
N_EVENTS = 100_000   # priority items per scenario run
REPEATS  = 20        # independent timed runs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def bench(fn, *args):
    '''Run fn(*args) REPEATS times; return (min_sec, mean_sec, stdev_sec, total_sec).'''
    times = []
    for _ in range(REPEATS):
        t0 = time.perf_counter()
        fn(*args)
        times.append(time.perf_counter() - t0)
    return min(times), statistics.mean(times), statistics.stdev(times), sum(times)


def report(label, n, min_t, mean_t, stdev_t, total_t):
    print(f'  {label:<46s}  {n/mean_t:>10,.0f} ev/s'
          f'  mean = {mean_t*1e3:7.2f} ± {stdev_t*1e3:3.2f} ms   min = {min_t*1e3:7.2f} ms'
          f'  total = {total_t:6.2f} s')


# ===========================================================================
# DSSim
# ===========================================================================
from dssim import DSSimulation, Queue
from dssim.components.container import DSKeyQueue


def _make_queue(sim=None, capacity=float('inf')):
    '''Return (sim, Queue) with DSKeyQueue keyed on item[0].'''
    if sim is None:
        sim = DSSimulation()
    q = Queue(capacity=capacity,
              policy=DSKeyQueue(key=lambda x: x[0]),
              sim=sim)
    return sim, q


# --- Scenario 1 : fill-drain (no simulation loop) --------------------------

def dssim_fill_drain(n):
    '''
    put_nowait N items in worst-case order (highest key first forces maximum
    heap sifting), then drain all with get_nowait.  sim.run() is never called.
    '''
    _, q = _make_queue()
    for i in range(n):
        q.put_nowait((n - i, i))       # key n, n-1, n-2, … 1  → all sift up
    drained = 0
    while q.get_nowait() is not None:
        drained += 1
    assert drained == n, f'dssim fill-drain: {drained} != {n}'


# --- Scenario 2a : burst with put_nowait + gget ----------------------------

def dssim_burst_nowait_put(n):
    '''
    Pre-fill queue via put_nowait (no simulation overhead for the producer),
    then let the consumer drain it inside sim.run() via gget.
    '''
    sim, q = _make_queue()
    received = 0

    for i in range(n):
        q.put_nowait((n - i, i))       # insert before sim starts

    def consumer():
        nonlocal received
        for _ in range(n):
            yield from q.gget()
            received += 1

    sim.schedule(0, consumer())
    sim.run()
    assert received == n, f'dssim burst-nowait-put: {received} != {n}'


# --- Scenario 2b : burst with gput + gget ----------------------------------

def dssim_burst_gput(n):
    '''
    Both producer (gput) and consumer (gget) run as simulation processes.
    Capacity is unlimited so gput never actually blocks, but it still goes
    through the check_and_gwait / pubsub event machinery on every call.
    '''
    sim, q = _make_queue()
    received = 0

    def producer():
        for i in range(n):
            yield from q.gput(float('inf'), (n - i, i))

    def consumer():
        nonlocal received
        for _ in range(n):
            yield from q.gget()
            received += 1

    sim.schedule(0, producer())
    sim.schedule(0, consumer())
    sim.run()
    assert received == n, f'dssim burst-gput: {received} != {n}'


# --- Scenario 3 : bounded (capacity = 1) -----------------------------------

def dssim_bounded(n):
    '''
    Capacity = 1 forces strict put / get alternation.  Each gput blocks until
    the consumer takes the previous item, exercising the full block/unblock
    path on every iteration.
    '''
    sim, q = _make_queue(capacity=1)
    received = 0

    def producer():
        for i in range(n):
            yield from q.gput(float('inf'), (i, i))

    def consumer():
        nonlocal received
        for _ in range(n):
            yield from q.gget()
            received += 1

    sim.schedule(0, producer())
    sim.schedule(0, consumer())
    sim.run()
    assert received == n, f'dssim bounded: {received} != {n}'


# ===========================================================================
# SimPy
# ===========================================================================
import simpy as _simpy


# --- Scenario 1 : fill-drain (SimPy must use processes) --------------------

def simpy_fill_drain(n):
    '''
    SimPy has no put_nowait; every put goes through the event system.
    Two processes — filler and drainer — replace the nowait loop.
    '''
    env = _simpy.Environment()
    store = _simpy.PriorityStore(env)
    drained = 0

    def filler():
        for i in range(n):
            yield store.put(_simpy.PriorityItem(n - i, i))

    def drainer():
        nonlocal drained
        for _ in range(n):
            yield store.get()
            drained += 1

    env.process(filler())
    env.process(drainer())
    env.run()
    assert drained == n, f'simpy fill-drain: {drained} != {n}'


# --- Scenario 2 : burst ----------------------------------------------------

def simpy_burst(n):
    '''
    PriorityStore with unlimited capacity.  Producer puts N items; consumer
    drains them.  Equivalent to DSSim burst-gput scenario.
    '''
    env = _simpy.Environment()
    store = _simpy.PriorityStore(env)
    received = 0

    def producer():
        for i in range(n):
            yield store.put(_simpy.PriorityItem(n - i, i))

    def consumer():
        nonlocal received
        for _ in range(n):
            yield store.get()
            received += 1

    env.process(producer())
    env.process(consumer())
    env.run()
    assert received == n, f'simpy burst: {received} != {n}'


# --- Scenario 3 : bounded (capacity = 1) -----------------------------------

def simpy_bounded(n):
    '''
    PriorityStore(capacity=1) forces strict put / get alternation.
    '''
    env = _simpy.Environment()
    store = _simpy.PriorityStore(env, capacity=1)
    received = 0

    def producer():
        for i in range(n):
            yield store.put(_simpy.PriorityItem(i, i))

    def consumer():
        nonlocal received
        for _ in range(n):
            yield store.get()
            received += 1

    env.process(producer())
    env.process(consumer())
    env.run()
    assert received == n, f'simpy bounded: {received} != {n}'


# ===========================================================================
# main
# ===========================================================================
if __name__ == '__main__':
    print(f'Python {sys.version.split()[0]}')
    print(f'Parameters: N={N_EVENTS:,}  repeats={REPEATS}\n')

    # ---- scenario 1 --------------------------------------------------------
    print(f'=== Scenario 1: fill-drain  (N={N_EVENTS:,}) ===')
    print(f'  DSSim uses put_nowait+get_nowait (no simulation loop);'
          f' SimPy has no nowait path.')
    report('DSSim  put_nowait + get_nowait',
           N_EVENTS, *bench(dssim_fill_drain, N_EVENTS))
    report('SimPy  put        + get       ',
           N_EVENTS, *bench(simpy_fill_drain, N_EVENTS))

    # ---- scenario 2 --------------------------------------------------------
    print(f'\n=== Scenario 2: burst  (unlimited capacity, N={N_EVENTS:,}) ===')
    report('DSSim  put_nowait (pre-fill) + gget',
           N_EVENTS, *bench(dssim_burst_nowait_put, N_EVENTS))
    report('DSSim  gput                 + gget',
           N_EVENTS, *bench(dssim_burst_gput, N_EVENTS))
    report('SimPy  put                  + get ',
           N_EVENTS, *bench(simpy_burst, N_EVENTS))

    # ---- scenario 3 --------------------------------------------------------
    print(f'\n=== Scenario 3: bounded  (capacity=1, alternating put/get, N={N_EVENTS:,}) ===')
    report('DSSim  gput + gget', N_EVENTS, *bench(dssim_bounded, N_EVENTS))
    report('SimPy  put  + get ', N_EVENTS, *bench(simpy_bounded, N_EVENTS))

    print()
