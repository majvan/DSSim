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
Benchmark: DSSim generator vs coroutine dispatch (raw + LiteLayer2)

Goal
----
Compare generator consumers against coroutine consumers in:
1. raw DSSim (``layer2=None``)
2. LiteLayer2 DSSim (``layer2=LiteLayer2``)

Both variants use object event delivery (``schedule_event`` / ``signal``).

Scenarios
---------
1. timed-dispatch : N object events scheduled at increasing timestamps
2. now-burst      : N object events queued via ``signal`` at time 0

Metrics per scenario
--------------------
- events/s  : N / mean wall-clock seconds
- mean ms   : average wall-clock time over REPEATS runs
- min ms    : fastest run
'''

import os
import statistics
import sys
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dssim import DSSimulation, LiteLayer2


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
N_EVENTS = 200_000
REPEATS = 25


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class _RawAwaitable:
    '''Single-step awaitable for raw coroutine consumers.

    ``await _RawAwaitable()`` suspends once and resumes with the next event
    sent by DSSim.
    '''

    def __await__(self):
        event = yield None
        return event


def bench(fn, *args):
    times = []
    for _ in range(REPEATS):
        t0 = time.perf_counter()
        fn(*args)
        times.append(time.perf_counter() - t0)
    return min(times), statistics.mean(times), statistics.stdev(times), sum(times)


def report(label, n, min_t, mean_t, stdev_t, total_t):
    print(
        f'  {label:<27s}  {n/mean_t:>10,.0f} ev/s'
        f'  mean = {mean_t*1e3:7.2f} ± {stdev_t*1e3:3.2f} ms'
        f'  min = {min_t*1e3:7.2f} ms'
        f'  total = {total_t:6.2f} s'
    )


def _parse_args():
    parser = argparse.ArgumentParser(
        description='Generator vs coroutine benchmark for DSSim raw and LiteLayer2.',
    )
    parser.add_argument(
        '--scenario',
        choices=['all', 'timed-dispatch', 'now-burst'],
        default='all',
        help='Run only a selected scenario (default: all).',
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Scenario 1: timed-dispatch
# ---------------------------------------------------------------------------
def raw_timed_generator(n):
    sim = DSSimulation(layer2=None)
    payload = {'kind': 'timed'}
    handled = 0
    last_event = None

    def sink():
        nonlocal handled, last_event
        while True:
            event = yield
            handled += 1
            last_event = event

    consumer = sink()
    sim.schedule_event(0, None, consumer)  # prime to first ``yield``
    for i in range(n):
        sim.schedule_event(i + 1, payload, consumer)
    sim.run()

    assert handled == n, f'timed generator: expected {n}, got {handled}'
    assert last_event is payload, 'timed generator: final payload mismatch'


def raw_timed_coroutine(n):
    sim = DSSimulation(layer2=None)
    payload = {'kind': 'timed'}
    handled = 0
    last_event = None

    async def sink():
        nonlocal handled, last_event
        wait_one = _RawAwaitable()
        while True:
            event = await wait_one
            handled += 1
            last_event = event

    consumer = sink()
    sim.schedule_event(0, None, consumer)  # prime to first ``await``
    for i in range(n):
        sim.schedule_event(i + 1, payload, consumer)
    sim.run()

    assert handled == n, f'timed coroutine: expected {n}, got {handled}'
    assert last_event is payload, 'timed coroutine: final payload mismatch'


def lite_timed_generator(n):
    sim = DSSimulation(layer2=LiteLayer2)
    payload = {'kind': 'timed'}
    handled = 0
    last_event = None

    def sink():
        nonlocal handled, last_event
        while True:
            event = yield from sim.gwait()
            handled += 1
            last_event = event

    consumer = sink()
    sim.schedule(0, consumer)  # prime to first gwait
    for i in range(n):
        sim.schedule_event(i + 1, payload, consumer)
    sim.run()

    assert handled == n, f'lite timed generator: expected {n}, got {handled}'
    assert last_event is payload, 'lite timed generator: final payload mismatch'


def lite_timed_coroutine(n):
    sim = DSSimulation(layer2=LiteLayer2)
    payload = {'kind': 'timed'}
    handled = 0
    last_event = None

    async def sink():
        nonlocal handled, last_event
        while True:
            event = await sim.wait()
            handled += 1
            last_event = event

    consumer = sink()
    sim.schedule(0, consumer)  # prime to first wait
    for i in range(n):
        sim.schedule_event(i + 1, payload, consumer)
    sim.run()

    assert handled == n, f'lite timed coroutine: expected {n}, got {handled}'
    assert last_event is payload, 'lite timed coroutine: final payload mismatch'


# ---------------------------------------------------------------------------
# Scenario 2: now-burst
# ---------------------------------------------------------------------------
def raw_now_burst_generator(n):
    sim = DSSimulation(layer2=None)
    payload = {'kind': 'now'}
    handled = 0
    last_event = None

    def sink():
        nonlocal handled, last_event
        while True:
            event = yield
            handled += 1
            last_event = event

    consumer = sink()
    sim.schedule_event(0, None, consumer)  # prime
    for _ in range(n):
        sim.signal(payload, consumer)
    sim.run()

    assert handled == n, f'now-burst generator: expected {n}, got {handled}'
    assert last_event is payload, 'now-burst generator: final payload mismatch'


def raw_now_burst_coroutine(n):
    sim = DSSimulation(layer2=None)
    payload = {'kind': 'now'}
    handled = 0
    last_event = None

    async def sink():
        nonlocal handled, last_event
        wait_one = _RawAwaitable()
        while True:
            event = await wait_one
            handled += 1
            last_event = event

    consumer = sink()
    sim.schedule_event(0, None, consumer)  # prime
    for _ in range(n):
        sim.signal(payload, consumer)
    sim.run()

    assert handled == n, f'now-burst coroutine: expected {n}, got {handled}'
    assert last_event is payload, 'now-burst coroutine: final payload mismatch'


def lite_now_burst_generator(n):
    sim = DSSimulation(layer2=LiteLayer2)
    payload = {'kind': 'now'}
    handled = 0
    last_event = None

    def sink():
        nonlocal handled, last_event
        while True:
            event = yield from sim.gwait()
            handled += 1
            last_event = event

    consumer = sink()
    sim.schedule(0, consumer)  # prime to first gwait
    for _ in range(n):
        sim.signal(payload, consumer)
    sim.run()

    assert handled == n, f'lite now-burst generator: expected {n}, got {handled}'
    assert last_event is payload, 'lite now-burst generator: final payload mismatch'


def lite_now_burst_coroutine(n):
    sim = DSSimulation(layer2=LiteLayer2)
    payload = {'kind': 'now'}
    handled = 0
    last_event = None

    async def sink():
        nonlocal handled, last_event
        while True:
            event = await sim.wait()
            handled += 1
            last_event = event

    consumer = sink()
    sim.schedule(0, consumer)  # prime to first wait
    for _ in range(n):
        sim.signal(payload, consumer)
    sim.run()

    assert handled == n, f'lite now-burst coroutine: expected {n}, got {handled}'
    assert last_event is payload, 'lite now-burst coroutine: final payload mismatch'


if __name__ == '__main__':
    args = _parse_args()
    run_all = args.scenario == 'all'

    print(f'Python {sys.version.split()[0]}')
    print(f'Parameters: N={N_EVENTS:,}  repeats={REPEATS}\n')

    if run_all or args.scenario == 'timed-dispatch':
        print(f'=== Scenario 1: timed-dispatch (N={N_EVENTS:,}) ===')
        g1 = bench(raw_timed_generator, N_EVENTS)
        c1 = bench(raw_timed_coroutine, N_EVENTS)
        tg1 = bench(lite_timed_generator, N_EVENTS)
        tc1 = bench(lite_timed_coroutine, N_EVENTS)
        report('DSSim raw generator', N_EVENTS, *g1)
        report('DSSim raw coroutine', N_EVENTS, *c1)
        report('DSSim lite generator', N_EVENTS, *tg1)
        report('DSSim lite coroutine', N_EVENTS, *tc1)
        print(f'  raw  coroutine/generator mean ratio: {c1[1] / g1[1]:.3f}x')
        print(f'  lite coroutine/generator mean ratio: {tc1[1] / tg1[1]:.3f}x')

    if run_all or args.scenario == 'now-burst':
        print(f'\n=== Scenario 2: now-burst (N={N_EVENTS:,}) ===')
        g2 = bench(raw_now_burst_generator, N_EVENTS)
        c2 = bench(raw_now_burst_coroutine, N_EVENTS)
        tg2 = bench(lite_now_burst_generator, N_EVENTS)
        tc2 = bench(lite_now_burst_coroutine, N_EVENTS)
        report('DSSim raw generator', N_EVENTS, *g2)
        report('DSSim raw coroutine', N_EVENTS, *c2)
        report('DSSim LiteLayer2 generator', N_EVENTS, *tg2)
        report('DSSim LiteLayer2 coroutine', N_EVENTS, *tc2)
        print(f'  raw  coroutine/generator mean ratio: {c2[1] / g2[1]:.3f}x')
        print(f'  lite coroutine/generator mean ratio: {tc2[1] / tg2[1]:.3f}x')
    print()
