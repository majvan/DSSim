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
Benchmark: Layer2 routing microbenchmarks (PubSub + Lite)

Focus
-----
The scenarios below isolate routing behavior of Layer2-like paths:

1) Pure Lite delivery:
   - direct delivery to ISubscriber
   - direct delivery to generator

2) Pure publisher routing:
   - PRE / CONSUME / POST_HIT pass-through
   - PRE / CONSUME / POST_MISS pass-through

3) Consumer filter combinations:
   - miss path (none short-circuit): None + {value, callable, get_cond, only}
   - hit path (first short-circuit): None + {value, callable, get_cond, only}
   - direct_call: callback decides directly from event payload (no extra cond stack)

4) Different notifier policies:
   - 0-consumer baseline
   - pass-through rate
   - churn scenarios (remove+add subscriber during routing)

5) Mutation during callback:
   - subscriber registry changes from callback body

6) Consumer ordering effects:
   - hit at index {0, S/2, S-1}
   - full miss

7) Mixed hit ratio:
   - 10%, 50%, 90%

8) End-to-end:
   - signal -> run path

9) Scale sweep:
   - S sweep

10) Latency profile:
   - p50/p95/p99 for try_send path

Important
---------
Benchmarked delivery path explicitly includes `sim.try_send(...)`.
If the current codebase does not expose `DSSimulation.try_send`, this benchmark
adds a compatibility alias to `send_object` at runtime.
'''

import os
import sys
import time
import statistics
import argparse
from typing import Callable, Any, Type, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dssim import (
    DSSchedulable,
    DSSimulation,
    LiteLayer2,
    DSCallback,
    DSCondCallback,
    DSSub,
    DSPub,
    NotifierDict,
    NotifierRoundRobin,
    NotifierPriority,
)
from dssim.base import ISubscriber, EventType


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
N_EVENTS = 50_000
S = 32
REPEATS = 10
N_EVENTS_EXTRA = 20_000
N_LATENCY_EVENTS = 5_000
REPEATS_QUICK = 3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ensure_try_send_api() -> None:
    # Keep benchmark portable across commits where try_send may or may not exist.
    if not hasattr(DSSimulation, 'try_send'):
        DSSimulation.try_send = DSSimulation.send_object


def bench(fn: Callable, *args, **kwargs):
    times = []
    for _ in range(REPEATS):
        t0 = time.perf_counter()
        fn(*args, **kwargs)
        times.append(time.perf_counter() - t0)
    return min(times), statistics.mean(times), statistics.stdev(times), sum(times)


def bench_with_repeats(repeats: int, fn: Callable, *args, **kwargs):
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn(*args, **kwargs)
        times.append(time.perf_counter() - t0)
    return min(times), statistics.mean(times), statistics.stdev(times), sum(times)


def report(label: str, n: int, min_t: float, mean_t: float, stdev_t: float, total_t: float) -> None:
    print(
        f'  {label:<46s}  {n/mean_t:>10,.0f} ev/s'
        f'  mean = {mean_t*1e3:7.2f} ± {stdev_t*1e3:3.2f} ms'
        f'  min = {min_t*1e3:7.2f} ms  total = {total_t:6.2f} s'
    )


def _inc(counter):
    counter[0] += 1


def _false(_event: Any) -> bool:
    return False


def _percentile(sorted_values: Sequence[int], ratio: float) -> int:
    if not sorted_values:
        return 0
    idx = int((len(sorted_values) - 1) * ratio)
    return sorted_values[idx]


class BenchCallback(DSCallback):
    '''Direct-send callback used by post-check pubsub benchmark scenarios.'''
    pass


class BenchObserver(DSSub):
    '''Observer subscriber that is safe for direct DSPub.send() dispatch.'''
    supports_direct_send = True

    def __init__(self, forward_method: Callable[..., EventType], **kwargs):
        super().__init__(**kwargs)
        self.forward_method = forward_method

    def send(self, event: EventType):
        return self.forward_method(event)


# ---------------------------------------------------------------------------
# 1) Pure pub/sub routing scenarios
# ---------------------------------------------------------------------------
def pubsub_pre_observers_one_consumer(n: int, n_pre: int) -> None:
    sim = DSSimulation()
    pub = DSPub(sim=sim)
    pre_seen = [0]
    consume_seen = [0]

    for _ in range(n_pre):
        pub.add_subscriber(BenchObserver(lambda e, c=pre_seen: (_inc(c), False)[1], sim=sim), phase=DSPub.Phase.PRE)
    pub.add_subscriber(BenchCallback(lambda e, c=consume_seen: (_inc(c), True)[1], sim=sim), phase=DSPub.Phase.CONSUME)

    for i in range(n):
        sim.try_send(pub, i)

    assert consume_seen[0] == n
    assert pre_seen[0] == n * n_pre


def pubsub_post_hit_observers_one_consumer(n: int, n_post: int) -> None:
    sim = DSSimulation()
    pub = DSPub(sim=sim)
    consume_seen = [0]
    post_seen = [0]

    pub.add_subscriber(BenchCallback(lambda e, c=consume_seen: (_inc(c), True)[1], sim=sim), phase=DSPub.Phase.CONSUME)
    for _ in range(n_post):
        pub.add_subscriber(BenchObserver(lambda e, c=post_seen: (_inc(c), False)[1], sim=sim), phase=DSPub.Phase.POST_HIT)

    for i in range(n):
        sim.try_send(pub, i)

    assert consume_seen[0] == n
    assert post_seen[0] == n * n_post


def pubsub_post_miss_observers_one_consumer(n: int, n_post: int) -> None:
    sim = DSSimulation()
    pub = DSPub(sim=sim)
    consume_seen = [0]
    post_seen = [0]

    pub.add_subscriber(BenchCallback(lambda e, c=consume_seen: (_inc(c), False)[1], sim=sim), phase=DSPub.Phase.CONSUME)
    for _ in range(n_post):
        pub.add_subscriber(BenchObserver(lambda e, c=post_seen: (_inc(c), False)[1], sim=sim), phase=DSPub.Phase.POST_MISS)

    for i in range(n):
        sim.try_send(pub, i)

    assert consume_seen[0] == n
    assert post_seen[0] == n * n_post


# ---------------------------------------------------------------------------
# 2) Consumer filter combinations
# ---------------------------------------------------------------------------
def _add_group2_consumer(pub: DSPub, sim: DSSimulation, mode: str, cb: Callable[[Any], bool], exact_value: int) -> None:
    if mode == 'none_value':
        consumer = DSCondCallback(cb, cond=None, sim=sim)
        consumer.get_cond().push(exact_value)
    elif mode == 'none_callable':
        consumer = DSCondCallback(cb, cond=None, sim=sim)
        consumer.get_cond().push(lambda e, x=exact_value: e == x)
    elif mode == 'none_get_cond':
        consumer = DSCondCallback(cb, cond=None, sim=sim)
        consumer.get_cond().push(sim.filter(lambda e, x=exact_value: e == x))
    elif mode == 'none_only':
        consumer = DSCondCallback(cb, cond=None, sim=sim)
    elif mode == 'direct_call':
        # Plain callback path: decision is done in callback body.
        consumer = BenchCallback(cb, sim=sim)
    else:
        raise ValueError(f'Unknown Group2 mode: {mode}')
    pub.add_subscriber(consumer, phase=DSPub.Phase.CONSUME)


def _group2_event(mode: str, exact_value: int) -> Any:
    if mode == 'none_only':
        return None
    return exact_value


def _group2_miss(n: int, mode: str, n_consumers: int, exact_value: int = 7777) -> None:
    sim = DSSimulation()
    pub = DSPub(sim=sim)
    seen = [0]

    count = max(1, n_consumers)

    if mode == 'direct_call':
        def _reject(event, c=seen, x=exact_value):
            _inc(c)
            return event == (x + 1)  # always false for event==x
    else:
        def _reject(_event, c=seen):
            _inc(c)
            return False

    for _ in range(count):
        _add_group2_consumer(pub, sim, mode, _reject, exact_value)
    event = _group2_event(mode, exact_value)
    for _ in range(n):
        sim.try_send(pub, event)

    assert seen[0] == n * count


def _group2_hit(n: int, mode: str, n_consumers: int, exact_value: int = 7777) -> None:
    sim = DSSimulation()
    pub = DSPub(sim=sim)
    first_seen = [0]
    other_seen = [0]

    count = max(1, n_consumers)

    if mode == 'direct_call':
        def _accept(event, c=first_seen, x=exact_value):
            _inc(c)
            return event == x

        def _reject(event, c=other_seen, x=exact_value):
            _inc(c)
            return event == (x + 1)  # always false for event==x
    else:
        def _accept(_event, c=first_seen):
            _inc(c)
            return True

        def _reject(_event, c=other_seen):
            _inc(c)
            return False

    _add_group2_consumer(pub, sim, mode, _accept, exact_value)
    for _ in range(count - 1):
        _add_group2_consumer(pub, sim, mode, _reject, exact_value)
    event = _group2_event(mode, exact_value)
    for _ in range(n):
        sim.try_send(pub, event)

    assert first_seen[0] == n
    assert other_seen[0] == 0


def pubsub_consumer_none_plus_value_miss(n: int, n_consumers: int) -> None:
    _group2_miss(n, 'none_value', n_consumers)


def pubsub_consumer_none_plus_callable_miss(n: int, n_consumers: int) -> None:
    _group2_miss(n, 'none_callable', n_consumers)


def pubsub_consumer_none_plus_get_cond_filter_miss(n: int, n_consumers: int) -> None:
    _group2_miss(n, 'none_get_cond', n_consumers)


def pubsub_consumer_none_only_miss(n: int, n_consumers: int) -> None:
    _group2_miss(n, 'none_only', n_consumers)


def pubsub_consumer_none_plus_value_hit(n: int, n_consumers: int) -> None:
    _group2_hit(n, 'none_value', n_consumers)


def pubsub_consumer_none_plus_callable_hit(n: int, n_consumers: int) -> None:
    _group2_hit(n, 'none_callable', n_consumers)


def pubsub_consumer_none_plus_get_cond_filter_hit(n: int, n_consumers: int) -> None:
    _group2_hit(n, 'none_get_cond', n_consumers)


def pubsub_consumer_none_only_hit(n: int, n_consumers: int) -> None:
    _group2_hit(n, 'none_only', n_consumers)


def pubsub_consumer_direct_call_miss(n: int, n_consumers: int) -> None:
    _group2_miss(n, 'direct_call', n_consumers)


def pubsub_consumer_direct_call_hit(n: int, n_consumers: int) -> None:
    _group2_hit(n, 'direct_call', n_consumers)


# ---------------------------------------------------------------------------
# 3) Notifier policy scenarios
# ---------------------------------------------------------------------------
def pubsub_notifier_zero_consumers(n: int, notifier: Type) -> None:
    sim = DSSimulation()
    pub = DSPub(notifier=notifier, sim=sim)
    for i in range(n):
        sim.try_send(pub, i)


def pubsub_notifier_pass_through(n: int, notifier: Type, n_subscribers: int) -> None:
    sim = DSSimulation()
    pub = DSPub(notifier=notifier, sim=sim)
    consumed = [0]

    for i in range(max(1, n_subscribers - 1)):
        cb = BenchCallback(_false, sim=sim)
        if notifier is NotifierPriority:
            pub.add_subscriber(cb, phase=DSPub.Phase.CONSUME, priority=i)
        else:
            pub.add_subscriber(cb, phase=DSPub.Phase.CONSUME)

    last = BenchCallback(lambda e, c=consumed: (_inc(c), True)[1], sim=sim)
    if notifier is NotifierPriority:
        pub.add_subscriber(last, phase=DSPub.Phase.CONSUME, priority=n_subscribers + 1)
    else:
        pub.add_subscriber(last, phase=DSPub.Phase.CONSUME)

    for i in range(n):
        sim.try_send(pub, i)

    assert consumed[0] == n


def pubsub_notifier_churn(n: int, notifier: Type, n_subscribers: int) -> None:
    sim = DSSimulation()
    pub = DSPub(notifier=notifier, sim=sim)
    consumed = [0]

    for _ in range(max(1, n_subscribers)):
        pub.add_subscriber(BenchCallback(_false, sim=sim), phase=DSPub.Phase.CONSUME)

    flap = BenchCallback(_false, sim=sim)
    pub.add_subscriber(flap, phase=DSPub.Phase.CONSUME)
    pub.add_subscriber(BenchCallback(lambda e, c=consumed: (_inc(c), True)[1], sim=sim), phase=DSPub.Phase.CONSUME)

    for i in range(n):
        pub.remove_subscriber(flap, phase=DSPub.Phase.CONSUME)  # deferred cleanup path for round-robin
        pub.add_subscriber(flap, phase=DSPub.Phase.CONSUME)
        sim.try_send(pub, i)

    assert consumed[0] == n
    consume_notifier = pub.subs[DSPub.Phase.CONSUME]
    if hasattr(consume_notifier, 'needs_cleanup'):
        assert consume_notifier.needs_cleanup is False


# ---------------------------------------------------------------------------
# 5) Consumer position and hit-ratio scenarios
# ---------------------------------------------------------------------------
def pubsub_consumer_hit_position(n: int, n_consumers: int, hit_index: int) -> None:
    sim = DSSimulation()
    pub = DSPub(sim=sim)
    accepted = [0]
    checked = [0]
    count = max(1, n_consumers)

    def _accept(_event, c_checked=checked, c_accepted=accepted):
        _inc(c_checked)
        _inc(c_accepted)
        return True

    def _reject(_event, c_checked=checked):
        _inc(c_checked)
        return False

    for i in range(count):
        cb = BenchCallback(_accept if i == hit_index else _reject, sim=sim)
        pub.add_subscriber(cb, phase=DSPub.Phase.CONSUME)

    for i in range(n):
        sim.try_send(pub, i)

    if 0 <= hit_index < count:
        assert accepted[0] == n
        assert checked[0] == n * (hit_index + 1)
    else:
        assert accepted[0] == 0
        assert checked[0] == n * count


def pubsub_consumer_hit_ratio_mix(n: int, n_consumers: int, hit_ratio: float) -> None:
    sim = DSSimulation()
    pub = DSPub(sim=sim)
    hits = [0]
    checked = [0]
    count = max(1, n_consumers)
    threshold = max(0, min(100, int(hit_ratio * 100)))

    def _first(_event, c_checked=checked, c_hits=hits, t=threshold):
        _inc(c_checked)
        if (_event % 100) < t:
            _inc(c_hits)
            return True
        return False

    def _reject(_event, c_checked=checked):
        _inc(c_checked)
        return False

    pub.add_subscriber(BenchCallback(_first, sim=sim), phase=DSPub.Phase.CONSUME)
    for _ in range(count - 1):
        pub.add_subscriber(BenchCallback(_reject, sim=sim), phase=DSPub.Phase.CONSUME)

    for i in range(n):
        sim.try_send(pub, i)

    expected_hits = (n // 100) * threshold + min(n % 100, threshold)
    assert hits[0] == expected_hits
    expected_checked = n + (n - expected_hits) * (count - 1)
    assert checked[0] == expected_checked


# ---------------------------------------------------------------------------
# 6) In-callback mutation scenarios
# ---------------------------------------------------------------------------
def _add_consume_sub(pub: DSPub, notifier: Type, subscriber: BenchCallback, priority: int) -> None:
    if notifier is NotifierPriority:
        pub.add_subscriber(subscriber, phase=DSPub.Phase.CONSUME, priority=priority)
    else:
        pub.add_subscriber(subscriber, phase=DSPub.Phase.CONSUME)


def _remove_consume_sub(pub: DSPub, notifier: Type, subscriber: BenchCallback, priority: int) -> None:
    if notifier is NotifierPriority:
        pub.remove_subscriber(subscriber, phase=DSPub.Phase.CONSUME, priority=priority)
    else:
        pub.remove_subscriber(subscriber, phase=DSPub.Phase.CONSUME)


def pubsub_notifier_in_callback_mutation(n: int, notifier: Type, n_subscribers: int) -> None:
    sim = DSSimulation()
    pub = DSPub(notifier=notifier, sim=sim)
    consumed = [0]
    mutated = [0]
    count = max(1, n_subscribers)

    target = BenchCallback(_false, sim=sim)

    def _mutator_cb(_event, c=mutated):
        _remove_consume_sub(pub, notifier, target, priority=1)
        _add_consume_sub(pub, notifier, target, priority=1)
        _inc(c)
        return False

    mutator = BenchCallback(_mutator_cb, sim=sim)
    terminal = BenchCallback(lambda e, c=consumed: (_inc(c), True)[1], sim=sim)

    _add_consume_sub(pub, notifier, mutator, priority=0)
    _add_consume_sub(pub, notifier, target, priority=1)
    for i in range(count - 1):
        _add_consume_sub(pub, notifier, BenchCallback(_false, sim=sim), priority=2 + i)
    _add_consume_sub(pub, notifier, terminal, priority=10_000)

    for i in range(n):
        sim.try_send(pub, i)

    assert consumed[0] == n
    assert mutated[0] == n
    consume_notifier = pub.subs[DSPub.Phase.CONSUME]
    if hasattr(consume_notifier, 'needs_cleanup'):
        assert consume_notifier.needs_cleanup is False


# ---------------------------------------------------------------------------
# 7) End-to-end scheduling and run-loop scenarios
# ---------------------------------------------------------------------------
def pubsub_end_to_end_signal_run(n: int, n_consumers: int) -> None:
    sim = DSSimulation()
    pub = DSPub(sim=sim)
    consumed = [0]
    count = max(1, n_consumers)

    for _ in range(count - 1):
        pub.add_subscriber(BenchCallback(_false, sim=sim), phase=DSPub.Phase.CONSUME)
    pub.add_subscriber(BenchCallback(lambda e, c=consumed: (_inc(c), True)[1], sim=sim), phase=DSPub.Phase.CONSUME)

    @DSSchedulable
    def producer():
        for i in range(n):
            sim.signal(i, pub)

    sim.schedule(0, producer())
    sim.run()
    assert consumed[0] == n


# ---------------------------------------------------------------------------
# 8) Latency profile and scale sweep
# ---------------------------------------------------------------------------
def pubsub_try_send_latency_profile(n: int, n_consumers: int) -> tuple[float, float, float]:
    sim = DSSimulation()
    pub = DSPub(sim=sim)
    consumed = [0]
    count = max(1, n_consumers)

    for _ in range(count - 1):
        pub.add_subscriber(BenchCallback(_false, sim=sim), phase=DSPub.Phase.CONSUME)
    pub.add_subscriber(BenchCallback(lambda e, c=consumed: (_inc(c), True)[1], sim=sim), phase=DSPub.Phase.CONSUME)

    latencies_ns = []
    for i in range(n):
        t0 = time.perf_counter_ns()
        sim.try_send(pub, i)
        latencies_ns.append(time.perf_counter_ns() - t0)

    assert consumed[0] == n
    latencies_ns.sort()
    p50_us = _percentile(latencies_ns, 0.50) / 1000.0
    p95_us = _percentile(latencies_ns, 0.95) / 1000.0
    p99_us = _percentile(latencies_ns, 0.99) / 1000.0
    return p50_us, p95_us, p99_us


def report_scale_sweep() -> None:
    print('\n=== Group 9: Scale Sweep (hit@S-1) ===')
    print(f'  repeats={REPEATS_QUICK}  N={N_EVENTS_EXTRA:,}')
    for s_value in (1, 4, 16, 64, 256):
        min_t, mean_t, stdev_t, total_t = bench_with_repeats(
            REPEATS_QUICK, pubsub_consumer_hit_position, N_EVENTS_EXTRA, s_value, s_value - 1
        )
        report(f'S={s_value}', N_EVENTS_EXTRA, min_t, mean_t, stdev_t, total_t)


# ---------------------------------------------------------------------------
# 4) Pure Lite delivery (event -> sim.try_send -> subscriber.send)
# ---------------------------------------------------------------------------
class _LiteSink(ISubscriber):
    def __init__(self):
        self.count = 0

    def send(self, _event):
        self.count += 1
        return True


def lite_delivery_to_isubscriber(n: int) -> None:
    sim = DSSimulation(layer2=LiteLayer2)
    sink = _LiteSink()
    for i in range(n):
        sim.try_send(sink, i)
    assert sink.count == n


def lite_delivery_to_generator(n: int) -> None:
    sim = DSSimulation(layer2=LiteLayer2)
    seen = [0]

    def sink():
        while True:
            event = yield
            if event is not None:
                seen[0] += 1

    sink_gen = sink()
    next(sink_gen)  # prime generator to first yield
    for i in range(n):
        sim.try_send(sink_gen, i)
    assert seen[0] == n


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def _parse_args():
    parser = argparse.ArgumentParser(
        description='Layer2 routing microbenchmarks (PubSub + Lite).',
    )
    parser.add_argument(
        '--scenario',
        choices=[
            'all',
            'lite-delivery',
            'pubsub-routing',
            'hit-position',
            'hit-ratio',
            'filter-combos',
            'notifier-policies',
            'notifier-mutation',
            'end-to-end',
            'scale-sweep',
            'latency',
        ],
        default='all',
        help='Run only a selected benchmark group (default: all).',
    )
    return parser.parse_args()


if __name__ == '__main__':
    args = _parse_args()
    run_all = args.scenario == 'all'
    _ensure_try_send_api()

    print(f'Python {sys.version.split()[0]}')
    print(f'Parameters: N={N_EVENTS:,}  S={S}  repeats={REPEATS}\n')

    if run_all or args.scenario == 'lite-delivery':
        print('=== Group 1: Pure Lite Delivery ===')
        report('Lite try_send -> ISubscriber', N_EVENTS, *bench(lite_delivery_to_isubscriber, N_EVENTS))
        report('Lite try_send -> generator', N_EVENTS, *bench(lite_delivery_to_generator, N_EVENTS))

    if run_all or args.scenario == 'pubsub-routing':
        print('\n=== Group 2: Pure PubSub PRE/CONSUME/POST routing ===')
        report('PRE observers', N_EVENTS, *bench(pubsub_pre_observers_one_consumer, N_EVENTS, S))
        report('POST_HIT observers', N_EVENTS, *bench(pubsub_post_hit_observers_one_consumer, N_EVENTS, S))
        report('POST_MISS observers', N_EVENTS, *bench(pubsub_post_miss_observers_one_consumer, N_EVENTS, S))

    if run_all or args.scenario == 'hit-position':
        print('\n=== Group 3: Consumer Hit Position ===')
        report('Hit at idx=0', N_EVENTS, *bench(pubsub_consumer_hit_position, N_EVENTS, S, 0))
        report('Hit at idx=S//2', N_EVENTS, *bench(pubsub_consumer_hit_position, N_EVENTS, S, S // 2))
        report('Hit at idx=S-1', N_EVENTS, *bench(pubsub_consumer_hit_position, N_EVENTS, S, S - 1))
        report('Miss (no consumer hit)', N_EVENTS, *bench(pubsub_consumer_hit_position, N_EVENTS, S, -1))

    if run_all or args.scenario == 'hit-ratio':
        print('\n=== Group 4: Hit-Ratio Mix ===')
        report('Hit-ratio 10%', N_EVENTS, *bench(pubsub_consumer_hit_ratio_mix, N_EVENTS, S, 0.10))
        report('Hit-ratio 50%', N_EVENTS, *bench(pubsub_consumer_hit_ratio_mix, N_EVENTS, S, 0.50))
        report('Hit-ratio 90%', N_EVENTS, *bench(pubsub_consumer_hit_ratio_mix, N_EVENTS, S, 0.90))

    if run_all or args.scenario == 'filter-combos':
        print('\n=== Group 5: Consumer Filter Combinations ===')
        report('Miss: None + exact value', N_EVENTS, *bench(pubsub_consumer_none_plus_value_miss, N_EVENTS, S))
        report('Miss: None + callable', N_EVENTS, *bench(pubsub_consumer_none_plus_callable_miss, N_EVENTS, S))
        report('Miss: None + get_cond() filter', N_EVENTS, *bench(pubsub_consumer_none_plus_get_cond_filter_miss, N_EVENTS, S))
        report('Miss: None only', N_EVENTS, *bench(pubsub_consumer_none_only_miss, N_EVENTS, S))
        report('Miss: direct_call', N_EVENTS, *bench(pubsub_consumer_direct_call_miss, N_EVENTS, S))
        report('Hit: None + exact value', N_EVENTS, *bench(pubsub_consumer_none_plus_value_hit, N_EVENTS, S))
        report('Hit: None + callable', N_EVENTS, *bench(pubsub_consumer_none_plus_callable_hit, N_EVENTS, S))
        report('Hit: None + get_cond() filter', N_EVENTS, *bench(pubsub_consumer_none_plus_get_cond_filter_hit, N_EVENTS, S))
        report('Hit: None only', N_EVENTS, *bench(pubsub_consumer_none_only_hit, N_EVENTS, S))
        report('Hit: direct_call', N_EVENTS, *bench(pubsub_consumer_direct_call_hit, N_EVENTS, S))

    if run_all or args.scenario == 'notifier-policies':
        print('\n=== Group 6: Notifier Policies ===')
        report('NotifierDict pass-through', N_EVENTS, *bench(pubsub_notifier_zero_consumers, N_EVENTS, NotifierDict))
        report('NotifierRoundRobin pass-through', N_EVENTS, *bench(pubsub_notifier_pass_through, N_EVENTS, NotifierRoundRobin, S))
        report('NotifierPriority pass-through', N_EVENTS, *bench(pubsub_notifier_pass_through, N_EVENTS, NotifierPriority, S))
        report('NotifierDict churn (cleanup path)', N_EVENTS, *bench(pubsub_notifier_churn, N_EVENTS, NotifierDict, S))
        report('NotifierRoundRobin churn (cleanup path)', N_EVENTS, *bench(pubsub_notifier_churn, N_EVENTS, NotifierRoundRobin, S))
        report('NotifierPriority churn (cleanup path)', N_EVENTS, *bench(pubsub_notifier_churn, N_EVENTS, NotifierPriority, S))

    if run_all or args.scenario == 'notifier-mutation':
        print('\n=== Group 7: Notifier Mutation During Callback ===')
        report('NotifierDict in-callback mutation', N_EVENTS_EXTRA, *bench(pubsub_notifier_in_callback_mutation, N_EVENTS_EXTRA, NotifierDict, S))
        report('NotifierRoundRobin in-callback mutation', N_EVENTS_EXTRA, *bench(pubsub_notifier_in_callback_mutation, N_EVENTS_EXTRA, NotifierRoundRobin, S))
        report('NotifierPriority in-callback mutation', N_EVENTS_EXTRA, *bench(pubsub_notifier_in_callback_mutation, N_EVENTS_EXTRA, NotifierPriority, S))

    if run_all or args.scenario == 'end-to-end':
        print('\n=== Group 8: End-to-End Signal->Run ===')
        report('signal->run path (S consumers)', N_EVENTS_EXTRA, *bench(pubsub_end_to_end_signal_run, N_EVENTS_EXTRA, S))

    if run_all or args.scenario == 'scale-sweep':
        report_scale_sweep()

    if run_all or args.scenario == 'latency':
        print('\n=== Group 9: try_send Latency Percentiles ===')
        p50_us, p95_us, p99_us = pubsub_try_send_latency_profile(N_LATENCY_EVENTS, S)
        print(f'  N={N_LATENCY_EVENTS:,}, S={S}: p50={p50_us:.2f} us, p95={p95_us:.2f} us, p99={p99_us:.2f} us')

    print()
