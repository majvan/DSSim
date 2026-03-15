# Chapter 11: Benchmarks and Performance

## 11.1 Benchmark Overview

DSSim ships a benchmark suite under `benchmarks/`. Each script measures a specific aspect of simulation throughput in **events per second (ev/s)**. Higher is better.

Benchmarks are run with:

```bash
python benchmarks/bench_simulator.py
python benchmarks/bench_queue.py
python benchmarks/bench_queue_priority.py
python benchmarks/bench_resource.py
python benchmarks/bench_layer2.py
python benchmarks/bench_generator_vs_coroutine.py
```

All results below were collected on the same hardware reference commit. The baseline commit (`4bdf5`) is used for relative comparisons.

---

## 11.2 Simulator Core Throughput (`bench_simulator`)

These scenarios measure how fast the simulation engine processes events, ignoring components.

| Scenario | ev/s |
|---|---:|
| Raw timed-callbacks (no layer overhead) | ~350,000 |
| LiteLayer2 timed-callbacks | ~245,000 |
| PubSubLayer2 timed-callbacks | ~180,000 |
| PubSubLayer2 now-burst (zero-time events) | ~360,000 |
| PubSubLayer2 now-chain (self-rescheduling) | ~380,000 |
| PubSubLayer2 generator wakeup (1 waiter + 1 producer) | ~335,000 |
| PubSubLayer2 cross-signal ping-pong (2 peers) | ~380,000 |

Key observations:
- **Raw scheduling** (no subscriber routing) peaks near 350,000 ev/s.
- **LiteLayer2** adds ~30% overhead over raw callbacks — process startup and sentinel dispatch.
- **PubSubLayer2** adds ~50% over raw due to subscriber lookup and condition evaluation.
- **Zero-time events** (now-queue) are faster than timed events because binary search is skipped.
- **Ping-pong** (two processes alternately waking each other) runs near 380,000 ev/s — close to now-burst speed because every event immediately wakes a ready waiter.

---

## 11.3 Queue Throughput (`bench_queue`)

| Scenario | DSSim Queue (ev/s) | DSSim LiteQueue (ev/s) |
|---|---:|---:|
| Free-flow: unbounded, 1P+1C, N=10k | ~155,000 | — |
| Backpressure: capacity=10, 1P+1C | ~55,000 | — |
| Many-workers: 100P + 100C | ~140,000 | — |
| Blocked-getters: 100 getters, 1P | ~44,000 | ~192,000 |
| Cross-notify: 100P+100C, capacity=1 | ~31,000 | ~213,000 |

Key observations:
- **LiteQueue is 4–7× faster than Queue** in the high-contention scenarios (blocked-getters, cross-notify) because it bypasses the pubsub routing machinery.
- **Queue throughput drops** significantly with backpressure because every blocked put/get goes through a condition wait and subscriber wakeup cycle.
- At 100P+100C with free capacity the overhead is lower because most operations do not block.

### Queue priority scenarios (`bench_queue_priority`)

| Scenario | DSSim Queue (ev/s) | DSSim LiteQueue (ev/s) |
|---|---:|---:|
| Fill-drain (N=100k) | ~310,000 | — |
| Burst, put_nowait+gget | ~130,000 | ~385,000 |
| Burst, gput+gget | ~76,000 | ~375,000 |
| Bounded capacity=1, gput+gget | ~44,000 | ~220,000 |

`LiteQueue` is 2.5–3× faster than `Queue` in burst scenarios. The gap narrows when items flow freely (fill-drain) because condition evaluation cost is amortized.

---

## 11.4 Resource Throughput (`bench_resource`)

| Scenario | DSSim Resource (ev/s) | DSSim LiteResource (ev/s) |
|---|---:|---:|
| Uncontended get/put (N=20k) | ~160,000 | — |
| Priority dispatch (K=100 priorities) | ~37,000 | ~93,000 |
| Preemption delivery (N=20k) | ~17,000 | ~51,000 |

Key observations:
- **Preemption is expensive**: ~17,000 ev/s for `PriorityResource` because each preemption requires reclaiming from lower-priority holders and re-routing events.
- `LitePriorityResource` is ~3× faster than `PriorityResource` in preemption scenarios.
- For uncontended resources (no blocking), throughput is similar to uncontended queues.

---

## 11.5 PubSub Layer Throughput (`bench_layer2`)

The `bench_layer2` suite isolates specific parts of the pubsub dispatch path.

### PRE / CONSUME / POST routing (Group 2)

| Scenario | ev/s |
|---|---:|
| PRE observers only | ~75,000 |
| POST_HIT observers | ~82,000 |
| POST_MISS observers | ~88,000 |

These scenarios send one event to a publisher with observers only (no blocking processes). Results reflect pure routing overhead.

### Consumer hit position (Group 3)

| Hit position | ev/s |
|---|---:|
| First consumer (idx=0) | ~300,000 |
| Middle consumer (idx=S/2) | ~85,000 |
| Last consumer (idx=S-1) | ~52,000 |
| No hit (miss) | ~52,000 |

DSSim iterates consumers in order and stops at the first accept. Hit performance degrades linearly with position because earlier consumers must be evaluated and rejected before the accepting consumer is reached.

**Implication:** For hot paths, put the most likely consumer first in the subscriber list, or use `NotifierRoundRobin` to distribute hit opportunities.

### Hit-ratio mix (Group 4)

| Hit ratio | ev/s |
|---|---:|
| 10% hits | ~55,000 |
| 50% hits | ~90,000 |
| 90% hits | ~185,000 |

Higher hit ratio means more events find their consumer quickly → higher throughput.

### Notifier policies (Group 6)

| Policy | Pass-through (ev/s) | Churn/cleanup (ev/s) |
|---|---:|---:|
| `NotifierDict` | — | ~54,000 |
| `NotifierRoundRobin` | ~48,000 | ~37,000 |
| `NotifierPriority` | ~38,000 | ~50,000 |

`NotifierRoundRobin` and `NotifierPriority` carry 20–40% overhead over `NotifierDict` due to rotation or sorting logic. This cost is only relevant on the hot dispatch path.

### Scale sweep — hit at last position (Group 9)

| Subscriber count (S) | ev/s |
|---|---:|
| 4 | ~275,000 |
| 16 | ~92,000 |
| 64 | ~27,000 |
| 256 | ~7,000 |

Throughput degrades roughly as O(1/S) when the hit is always at the last position. For models with many subscribers in the CONSUME tier, consider reducing subscriber count or restructuring the event routing.

---

## 11.6 Generator vs. Coroutine (`bench_generator_vs_coroutine`)

| Scenario | DSSim raw generator | DSSim raw coroutine | DSSim lite generator | DSSim lite coroutine |
|---|---:|---:|---:|---:|
| Timed dispatch N=200k | ~290,000 | ~280,000 | ~240,000 | ~220,000 |

Generators and coroutines have nearly identical throughput. The ~10% difference between raw and lite flavors reflects `DSProcess` startup cost versus `DSLiteProcess`.

**Implication:** Choose between generator and `async def` based on readability preference, not performance. The runtime cost difference is negligible.

---

## 11.7 Guidelines for Performance-Sensitive Models

1. **Use LiteLayer2** if your model does not need pubsub routing, condition filtering, or circuit composition.
2. **Prefer `LiteQueue`/`LiteResource`** for high-contention components when monitoring via `tx_nempty`/`tx_changed` is not needed.
3. **Put the most-likely consumer first** in the subscriber list to minimize per-event iteration cost.
4. **Use `NotifierRoundRobin` or `NotifierPriority` only when needed** — they carry overhead relative to `NotifierDict`.
5. **Avoid O(S) fan-out** for large subscriber counts; restructure routing or use multiple publishers to keep S small.
6. **Batch zero-time events** where possible — now-queue events are faster than timed events because the time queue binary search is skipped.

---

## 11.8 Key Takeaways

- DSSim raw scheduling reaches ~350,000 ev/s; PubSubLayer2 adds ~50% overhead over raw.
- `LiteQueue` and `LiteResource` are 3–7× faster than their pubsub counterparts in high-contention scenarios.
- PubSub consumer dispatch is O(S) in the number of consumers; hit-at-first-position is the optimal case.
- Generator vs. coroutine choice does not affect throughput meaningfully.
- When hit ratios are high and subscriber counts are small, PubSubLayer2 throughput approaches LiteLayer2.
