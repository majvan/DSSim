#!/usr/bin/env python3
'''
Benchmark: event object type used in Queue._fire_* methods

Compare four variants for the event passed to schedule_event:
  dict      : {'event': 'queue not empty', 'process': sim.pid}   (current)
  producer  : the DSProducer instance itself                       (option 1)
  slots     : a __slots__ class with (producer, process)           (option 2)
  namedtuple: a collections.namedtuple with (producer, process)    (option 3)

Three scenarios
---------------
1. put_nowait-only  : no sim.run, 1 subscriber (DSProbe on tx_nempty)
                      — isolates raw _fire_nempty cost
2. free-flow        : 1 producer (put_nowait), 1 consumer (gget), N=100_000
                      — typical real-world usage with 1 active subscriber
3. backpressure     : gput + gget, capacity=10, N=100_000
                      — tight blocking / unblocking cycle
'''
import sys
import os
import time
import statistics
from collections import namedtuple

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

N = 100_000
CAPACITY = 10
REPEATS = 25

# ---------------------------------------------------------------------------
# Event type definitions
# ---------------------------------------------------------------------------

class SlotsEvent:
    __slots__ = ('producer', 'process')
    def __init__(self, producer, process):
        self.producer = producer
        self.process = process


NTEvent = namedtuple('NTEvent', ['producer', 'process'])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def bench(fn, *args):
    times = []
    for _ in range(REPEATS):
        t0 = time.perf_counter()
        fn(*args)
        times.append(time.perf_counter() - t0)
    return min(times), statistics.mean(times)


def pct(mean, baseline):
    return f'{(mean - baseline) / baseline * 100:+.1f}%'


def report(label, min_t, mean_t, baseline_mean=None):
    s = f'  {label:<30s}  min={min_t*1e3:8.2f}ms  mean={mean_t*1e3:8.2f}ms'
    if baseline_mean is not None:
        s += f'  {pct(mean_t, baseline_mean)}'
    print(s)


# ===========================================================================
# Patched Queue variants
# ===========================================================================
from dssim import DSSimulation, Queue, DSProbe


def make_queue_dict(sim):
    '''Current implementation — dict event.'''
    return Queue(sim=sim)


def make_queue_producer(sim):
    '''Option 1 — producer as event (monkey-patched).'''
    q = Queue(sim=sim)
    def _fire_nempty():
        if q.tx_nempty.has_subscribers():
            sim.schedule_event_now(q.tx_nempty, q.tx_nempty)
    def _fire_nfull():
        if q.tx_nfull.has_subscribers():
            sim.schedule_event_now(q.tx_nfull, q.tx_nfull)
    def _fire_changed():
        if q.tx_changed.has_subscribers():
            sim.schedule_event_now(q.tx_changed, q.tx_changed)
    q._fire_nempty = _fire_nempty
    q._fire_nfull  = _fire_nfull
    q._fire_changed = _fire_changed
    return q


def make_queue_slots(sim):
    '''Option 2 — __slots__ class event.'''
    q = Queue(sim=sim)
    def _fire_nempty():
        if q.tx_nempty.has_subscribers():
            sim.schedule_event_now(SlotsEvent(q.tx_nempty, sim.pid), q.tx_nempty)
    def _fire_nfull():
        if q.tx_nfull.has_subscribers():
            sim.schedule_event_now(SlotsEvent(q.tx_nfull, sim.pid), q.tx_nfull)
    def _fire_changed():
        if q.tx_changed.has_subscribers():
            sim.schedule_event_now(SlotsEvent(q.tx_changed, sim.pid), q.tx_changed)
    q._fire_nempty = _fire_nempty
    q._fire_nfull  = _fire_nfull
    q._fire_changed = _fire_changed
    return q


def make_queue_nt(sim):
    '''Option 3 — namedtuple event.'''
    q = Queue(sim=sim)
    def _fire_nempty():
        if q.tx_nempty.has_subscribers():
            sim.schedule_event_now(NTEvent(q.tx_nempty, sim.pid), q.tx_nempty)
    def _fire_nfull():
        if q.tx_nfull.has_subscribers():
            sim.schedule_event_now(NTEvent(q.tx_nfull, sim.pid), q.tx_nfull)
    def _fire_changed():
        if q.tx_changed.has_subscribers():
            sim.schedule_event_now(NTEvent(q.tx_changed, sim.pid), q.tx_changed)
    q._fire_nempty = _fire_nempty
    q._fire_nfull  = _fire_nfull
    q._fire_changed = _fire_changed
    return q


VARIANTS = [
    ('dict (current)', make_queue_dict),
    ('producer',       make_queue_producer),
    ('slots class',    make_queue_slots),
    ('namedtuple',     make_queue_nt),
]


# ===========================================================================
# Scenario 1 — put_nowait only, 1 subscriber
# ===========================================================================

def run_put_nowait(make_q, n):
    sim = DSSimulation()
    q = make_q(sim)
    probe = DSProbe(q.tx_nempty, sim=sim)   # 1 subscriber on tx_nempty
    for i in range(n):
        q.put_nowait(i)


# ===========================================================================
# Scenario 2 — free-flow (put_nowait producer + gget consumer)
# ===========================================================================

def run_free_flow(make_q, n):
    sim = DSSimulation()
    q = make_q(sim)
    got = [0]

    def producer():
        for i in range(n):
            q.put_nowait(i)
        yield from sim.gwait(1)

    def consumer():
        while got[0] < n:
            items = yield from q.gget()
            if items:
                got[0] += 1

    sim.schedule(0, producer())
    sim.schedule(0, consumer())
    sim.run(n + 10)


# ===========================================================================
# Scenario 3 — backpressure (gput + gget, capacity=CAPACITY)
# ===========================================================================

def run_backpressure(make_q, n):
    sim = DSSimulation()
    q = make_q(sim)
    done = [0]

    def producer():
        for i in range(n):
            yield from q.gput(float('inf'), i)

    def consumer():
        while done[0] < n:
            items = yield from q.gget()
            if items:
                done[0] += 1

    sim.schedule(0, producer())
    sim.schedule(0, consumer())
    sim.run(n * 10)


# ===========================================================================
# Main
# ===========================================================================

if __name__ == '__main__':
    scenarios = [
        ('1. put_nowait x{n} (1 subscriber on tx_nempty)', run_put_nowait),
        ('2. free-flow sim.run (1P put_nowait, 1C gget, N={n})', run_free_flow),
        ('3. backpressure sim.run (gput+gget, capacity={cap}, N={n})', run_backpressure),
    ]

    for title_tmpl, run_fn in scenarios:
        title = title_tmpl.format(n=N, cap=CAPACITY)
        print(f'\n=== {title} ===')
        baseline_mean = None
        for label, make_q in VARIANTS:
            mn, mean = bench(run_fn, make_q, N)
            report(label, mn, mean, baseline_mean)
            if baseline_mean is None:
                baseline_mean = mean
