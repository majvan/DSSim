#!/usr/bin/env python3
'''
Benchmark: DSSim Queue vs salabim Store

Five scenarios
--------------
1. free-flow      : unbounded queue, 1 producer dumps N items; 1 consumer drains
2. backpressure   : bounded queue (capacity C), producer blocks when full,
                    consumer blocks when empty — tight put/get alternation
3. many-workers   : K producers + K consumers on one unbounded queue,
                    each pair exchanges N/K items (put_nowait, no blocking)
4. blocked-getters: K getters all blocked on empty queue; 1 producer puts
                    items one at a time — stresses "notify one from K waiters"
5. cross-notify   : K consumers scheduled before K producers, capacity=1;
                    consumers subscribe before producers so every dequeue
                    triggers cross-notification in the old broadcast model —
                    stresses the tx_item/tx_space separation benefit

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
N_EVENTS = 10_000   # total items exchanged per run
CAPACITY = 10       # buffer size for backpressure scenario
N_WORKERS = 100     # producers == consumers in many-workers / blocked-getters
CROSS_WORKERS = 100 # producers == consumers in cross-notify (capacity=1)
REPEATS = 100       # independent timed runs; we report mean + min


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def bench(fn, *args, **kwargs):
    '''Run fn(*args) REPEATS times; return (min_sec, mean_sec, total_sec).'''
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
from dssim import DSSimulation, Queue, DSSchedulable


def dssim_free_flow(n):
    '''
    Unbounded queue.  Producer puts N items via put_nowait (no blocking),
    then yields once.  Consumer drains via gget with timeout=0 so it stops
    when the queue is empty and no more items will arrive.
    '''
    sim = DSSimulation()
    q = Queue(sim=sim)
    got = 0

    @DSSchedulable
    def producer():
        for i in range(n):
            q.put_nowait(i)

    def consumer():
        nonlocal got
        while got < n:
            yield from q.gget(timeout=0)
            got += 1

    sim.schedule(0, producer())
    sim.schedule(0, consumer())
    sim.run()
    assert got == n, f'free-flow: expected {n}, got {got}'


def dssim_backpressure(n, capacity):
    '''
    Bounded queue (capacity).  Producer uses gput (blocks when full);
    consumer uses gget (blocks when empty).  Models tight alternation.
    '''
    sim = DSSimulation()
    q = Queue(capacity=capacity, sim=sim)
    got = 0

    @DSSchedulable
    def producer():
        for i in range(n):
            yield from q.gput(float('inf'), i)

    def consumer():
        nonlocal got
        while got < n:
            yield from q.gget()
            got += 1

    sim.schedule(0, producer())
    sim.schedule(0, consumer())
    sim.run()
    assert got == n, f'backpressure: expected {n}, got {got}'


def dssim_many_workers(n, k):
    '''
    K producers + K consumers sharing one unbounded queue.
    Each producer puts n//k items; each consumer gets n//k items.
    Tests scheduler overhead with O(k) concurrent coroutines.
    '''
    sim = DSSimulation()
    q = Queue(sim=sim)
    per = n // k
    got = 0

    @DSSchedulable
    def producer():
        for i in range(per):
            q.put_nowait(i)

    def consumer():
        nonlocal got
        for _ in range(per):
            yield from q.gget()
            got += 1

    for _ in range(k):
        sim.schedule(0, producer())
        sim.schedule(0, consumer())
    sim.run()
    assert got == n, f'many-workers: expected {n}, got {got}'


def dssim_blocked_getters(n, k):
    '''
    K getters all block on an empty queue before the producer starts.
    Producer puts N items one at a time, yielding after each so exactly
    one getter wakes per item.  Stresses "notify one from K waiting getters".
    '''
    sim = DSSimulation()
    q = Queue(sim=sim)
    per = n // k
    got = 0

    def getter():
        nonlocal got
        for _ in range(per):
            yield from q.gget()
            got += 1

    def producer():
        for i in range(n):
            q.put_nowait(i)
            yield from sim.gwait(0)   # yield so one getter can run per item

    for _ in range(k):
        sim.schedule(0, getter())    # getters first → all block before producer
    sim.schedule(0, producer())
    sim.run()
    assert got == n, f'blocked-getters: expected {n}, got {got}'


def dssim_cross_notify(n, k, capacity):
    '''
    K consumers scheduled before K producers; capacity=1 keeps the queue
    almost always either full or empty.  Consumers subscribe to the notifier
    before producers, so in the old broadcast model each dequeue would iterate
    K failing consumer conditions before finding a producer (O(K) overhead).
    With tx_item/tx_space separation each side only sees its own events: O(1).
    '''
    sim = DSSimulation()
    q = Queue(capacity=capacity, sim=sim)
    per = n // k
    got = 0

    def producer():
        for i in range(per):
            yield from q.gput(float('inf'), i)

    def consumer():
        nonlocal got
        for _ in range(per):
            yield from q.gget()
            got += 1

    for _ in range(k):
        sim.schedule(0, consumer())  # consumers first → subscribe before producers
        sim.schedule(0, producer())
    sim.run()
    assert got == n, f'cross-notify: expected {n}, got {got}'


# ===========================================================================
# SimPy
# ===========================================================================
import simpy as _simpy


def simpy_free_flow(n):
    '''
    Unbounded SimPy Store.  Producer puts N items without yielding (non-blocking
    for unbounded stores), then yields once.  Consumer drains via store.get().
    '''
    env = _simpy.Environment()
    store = _simpy.Store(env)
    got = [0]

    def producer():
        for i in range(n):
            store.put(i)          # non-blocking: event triggered immediately
        yield env.timeout(0)      # yield once to let consumer run

    def consumer():
        while got[0] < n:
            yield store.get()
            got[0] += 1

    env.process(producer())
    env.process(consumer())
    env.run()
    assert got[0] == n, f'simpy free-flow: expected {n}, got {got[0]}'


def simpy_backpressure(n, capacity):
    '''
    Bounded SimPy Store (capacity).  Producer yields on each put (blocks when
    full); consumer yields on each get (blocks when empty).
    '''
    env = _simpy.Environment()
    store = _simpy.Store(env, capacity=capacity)
    got = [0]

    def producer():
        for i in range(n):
            yield store.put(i)

    def consumer():
        while got[0] < n:
            yield store.get()
            got[0] += 1

    env.process(producer())
    env.process(consumer())
    env.run()
    assert got[0] == n, f'simpy backpressure: expected {n}, got {got[0]}'


def simpy_many_workers(n, k):
    '''
    K SimPy producer processes + K consumer processes sharing one unbounded
    Store.  Each produces/consumes n//k items.
    '''
    env = _simpy.Environment()
    store = _simpy.Store(env)
    per = n // k
    got = [0]

    def producer():
        for i in range(per):
            store.put(i)
        yield env.timeout(0)

    def consumer():
        for _ in range(per):
            yield store.get()
            got[0] += 1

    for _ in range(k):
        env.process(producer())
        env.process(consumer())
    env.run()
    assert got[0] == n, f'simpy many-workers: expected {n}, got {got[0]}'


def simpy_blocked_getters(n, k):
    '''
    K getters all block on an empty Store; producer puts N items one at a time
    with timeout(0) between each so exactly one getter wakes per item.
    '''
    env = _simpy.Environment()
    store = _simpy.Store(env)
    per = n // k
    got = [0]

    def getter():
        for _ in range(per):
            yield store.get()
            got[0] += 1

    def producer():
        for i in range(n):
            store.put(i)
            yield env.timeout(0)   # yield so one getter can run per item

    for _ in range(k):
        env.process(getter())      # getters first → all block before producer
    env.process(producer())
    env.run()
    assert got[0] == n, f'simpy blocked-getters: expected {n}, got {got[0]}'


def simpy_cross_notify(n, k, capacity):
    '''
    K consumers scheduled before K producers; bounded Store (capacity=1).
    Mirrors the dssim_cross_notify scenario.
    '''
    env = _simpy.Environment()
    store = _simpy.Store(env, capacity=capacity)
    per = n // k
    got = [0]

    def producer():
        for i in range(per):
            yield store.put(i)

    def consumer():
        for _ in range(per):
            yield store.get()
            got[0] += 1

    for _ in range(k):
        env.process(consumer())    # consumers first, matching dssim ordering
        env.process(producer())
    env.run()
    assert got[0] == n, f'simpy cross-notify: expected {n}, got {got[0]}'


# ===========================================================================
# salabim
# ===========================================================================
import salabim as _sal
_sal.yieldless(False)


def _sal_item_class(env):
    '''Factory: return a fresh Item class bound to env (avoids class reuse).'''
    class Item(_sal.Component):
        def setup(self, value):
            self.value = value
        def process(self):
            pass   # data item — no active behaviour
    return Item


def sal_free_flow(n):
    '''
    Unbounded salabim Store.  Producer puts N Component items via to_store;
    consumer drains via from_store.
    '''
    env = _sal.Environment(trace=False)
    store = _sal.Store()
    Item = _sal_item_class(env)
    got = [0]

    class Producer(_sal.Component):
        def process(self):
            for i in range(n):
                yield self.to_store(store, Item(value=i))

    class Consumer(_sal.Component):
        def process(self):
            while got[0] < n:
                yield self.from_store(store)
                got[0] += 1

    Producer(env=env)
    Consumer(env=env)
    env.run()
    assert got[0] == n, f'sal free-flow: expected {n}, got {got[0]}'


def sal_backpressure(n, capacity):
    '''
    Bounded salabim Store (capacity).  Producer blocks on to_store when full;
    consumer blocks on from_store when empty.
    '''
    env = _sal.Environment(trace=False)
    store = _sal.Store(capacity=capacity)
    Item = _sal_item_class(env)
    got = [0]

    class Producer(_sal.Component):
        def process(self):
            for i in range(n):
                yield self.to_store(store, Item(value=i))

    class Consumer(_sal.Component):
        def process(self):
            while got[0] < n:
                yield self.from_store(store)
                got[0] += 1

    Producer(env=env)
    Consumer(env=env)
    env.run()
    assert got[0] == n, f'sal backpressure: expected {n}, got {got[0]}'


def sal_many_workers(n, k):
    '''
    K salabim Producer Components + K Consumer Components sharing one Store.
    Each produces/consumes n//k items.
    '''
    env = _sal.Environment(trace=False)
    store = _sal.Store()
    Item = _sal_item_class(env)
    per = n // k
    got = [0]

    class Producer(_sal.Component):
        def process(self):
            for i in range(per):
                yield self.to_store(store, Item(value=i))

    class Consumer(_sal.Component):
        def process(self):
            for _ in range(per):
                yield self.from_store(store)
                got[0] += 1

    for _ in range(k):
        Producer(env=env)
        Consumer(env=env)
    env.run()
    assert got[0] == n, f'sal many-workers: expected {n}, got {got[0]}'


def sal_blocked_getters(n, k):
    '''
    K salabim Consumers all waiting on an empty Store; 1 Producer puts N items
    one at a time with hold(0) between each so exactly one consumer wakes.
    '''
    env = _sal.Environment(trace=False)
    store = _sal.Store()
    Item = _sal_item_class(env)
    per = n // k
    got = [0]

    class Getter(_sal.Component):
        def process(self):
            for _ in range(per):
                yield self.from_store(store)
                got[0] += 1

    class Producer(_sal.Component):
        def process(self):
            for i in range(n):
                yield self.to_store(store, Item(value=i))
                yield self.hold(0)   # yield so one getter can run per item

    for _ in range(k):
        Getter(env=env)
    Producer(env=env)
    env.run()
    assert got[0] == n, f'sal blocked-getters: expected {n}, got {got[0]}'


def sal_cross_notify(n, k, capacity):
    '''
    K Consumers scheduled before K Producers; bounded Store (capacity).
    Mirrors the dssim_cross_notify scenario.
    '''
    env = _sal.Environment(trace=False)
    store = _sal.Store(capacity=capacity)
    Item = _sal_item_class(env)
    per = n // k
    got = [0]

    class Producer(_sal.Component):
        def process(self):
            for i in range(per):
                yield self.to_store(store, Item(value=i))

    class Consumer(_sal.Component):
        def process(self):
            for _ in range(per):
                yield self.from_store(store)
                got[0] += 1

    for _ in range(k):
        Consumer(env=env)   # consumers first, matching dssim ordering
        Producer(env=env)
    env.run()
    assert got[0] == n, f'sal cross-notify: expected {n}, got {got[0]}'


# ===========================================================================
# main
# ===========================================================================
if __name__ == '__main__':
    print(f'Python {sys.version.split()[0]}')
    print(f'Parameters: N={N_EVENTS:,}  capacity={CAPACITY}'
          f'  workers={N_WORKERS}  repeats={REPEATS}\n')

    # ---- scenario 1 --------------------------------------------------------
    print(f'=== Scenario 1: free-flow  (unbounded, 1P + 1C, N={N_EVENTS:,}) ===')
    report('DSSim  Queue',  N_EVENTS, *bench(dssim_free_flow,  N_EVENTS))
    report('SimPy  Store',  N_EVENTS, *bench(simpy_free_flow,  N_EVENTS))
    report('salabim Store', N_EVENTS, *bench(sal_free_flow,    N_EVENTS))

    # ---- scenario 2 --------------------------------------------------------
    print(f'\n=== Scenario 2: backpressure  (capacity={CAPACITY}, 1P + 1C, N={N_EVENTS:,}) ===')
    report('DSSim  Queue',  N_EVENTS, *bench(dssim_backpressure, N_EVENTS, CAPACITY))
    report('SimPy  Store',  N_EVENTS, *bench(simpy_backpressure, N_EVENTS, CAPACITY))
    report('salabim Store', N_EVENTS, *bench(sal_backpressure,   N_EVENTS, CAPACITY))

    # ---- scenario 3 --------------------------------------------------------
    print(f'\n=== Scenario 3: many-workers  ({N_WORKERS}P + {N_WORKERS}C, N={N_EVENTS:,}) ===')
    report('DSSim  Queue',  N_EVENTS, *bench(dssim_many_workers, N_EVENTS, N_WORKERS))
    report('SimPy  Store',  N_EVENTS, *bench(simpy_many_workers, N_EVENTS, N_WORKERS))
    report('salabim Store', N_EVENTS, *bench(sal_many_workers,   N_EVENTS, N_WORKERS))

    # ---- scenario 4 --------------------------------------------------------
    print(f'\n=== Scenario 4: blocked-getters  ({N_WORKERS} getters, 1P, N={N_EVENTS:,}) ===')
    report('DSSim  Queue',  N_EVENTS, *bench(dssim_blocked_getters, N_EVENTS, N_WORKERS))
    report('SimPy  Store',  N_EVENTS, *bench(simpy_blocked_getters, N_EVENTS, N_WORKERS))
    report('salabim Store', N_EVENTS, *bench(sal_blocked_getters,   N_EVENTS, N_WORKERS))

    # ---- scenario 5 --------------------------------------------------------
    print(f'\n=== Scenario 5: cross-notify  ({CROSS_WORKERS}P + {CROSS_WORKERS}C, capacity=1, N={N_EVENTS:,}) ===')
    report('DSSim  Queue',  N_EVENTS, *bench(dssim_cross_notify, N_EVENTS, CROSS_WORKERS, 1))
    report('SimPy  Store',  N_EVENTS, *bench(simpy_cross_notify, N_EVENTS, CROSS_WORKERS, 1))
    report('salabim Store', N_EVENTS, *bench(sal_cross_notify,   N_EVENTS, CROSS_WORKERS, 1))

    print()
