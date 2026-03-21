# Chapter 8: Probes, Tracing, and Debugging

## 8.1 What Are Probes?

!!! note "PubSubLayer2 only"
    Probes, PRE observers, and event tracing all rely on PubSubLayer2's publisher/subscriber tier infrastructure. `DSLiteQueue`, `DSLiteResource`, and other Lite components have no probe API and no subscription tiers.

A _probe_ is a non-intrusive observer attached to a simulation component. Probes collect metrics over time without modifying the component's logic. They hook into the component's pubsub endpoints using `PRE` phase subscriptions, so they observe events before any consumer decision is made and cannot interfere with normal event flow.

Probes are decoupled from component core logic: `DSQueue` and `DSResource` do not know about probes internally. The `QueueProbeMixin` and `ResourceProbeMixin` provide the attachment API, and probes observe the components' publisher endpoints directly.

---

## 8.2 Queue Probes

### 8.2.1 Built-in Statistics Probe

`QueueStatsProbe` tracks occupancy and throughput for a `DSQueue`:

```python
from dssim import DSSimulation

sim = DSSimulation()
q = sim.queue(capacity=10)

# Attach the built-in stats probe
probe = q.add_stats_probe()

# ... run the simulation ...
sim.run(until=100)

# Read results
s = probe.stats()
print(f"avg length:     {s['time_avg_len']:.2f} items")
print(f"max length:     {s['max_len']} items")
print(f"non-empty time: {s['time_nonempty_ratio']*100:.1f}%")
print(f"total puts:     {s['put_count']}")
print(f"total gets:     {s['get_count']}")
```

### 8.2.2 Statistics Fields

The `stats()` dict contains:

| Field | Type | Description |
|---|---|---|
| `start_time` | float | Simulation time when probe was attached / reset |
| `end_time` | float | Simulation time of last `stats()` call |
| `duration` | float | `end_time - start_time` |
| `time_avg_len` | float | Time-weighted average queue length |
| `max_len` | int | Maximum observed queue length |
| `time_nonempty_ratio` | float | Fraction of time queue was non-empty (0–1) |
| `put_count` | int | Total number of successful put operations |
| `get_count` | int | Total number of successful get operations |
| `current_len` | int | Queue length at time of `stats()` call |

### 8.2.3 Operations Probe

`QueueOpsProbe` tracks every API-level operation attempt — puts, gets, pops, removes, and setitem calls — together with their outcomes (success, failure, blocked, timeout) and transferred item counts. It complements `QueueStatsProbe` when you need to know *why* items are moving (or not).

```python
ops = q.add_ops_probe()

# ... run the simulation ...
sim.run(until=100)

s = ops.stats()
print(f"put attempts: {s['put_attempt_count']}  success: {s['put_success_count']}  fail: {s['put_fail_count']}")
print(f"get attempts: {s['get_attempt_count']}  blocked: {s['get_blocked_count']}  timeout: {s['get_timeout_count']}")
print(f"items moved:  put {s['put_moved_items']}  get {s['get_moved_items']}")
print(f"max batch:    put {s['max_put_batch']}  get {s['max_get_batch']}")
```

#### Operations Fields

| Field | Type | Description |
|---|---|---|
| `start_time` | float | Probe start time |
| `end_time` | float | Time of last observed operation |
| `duration` | float | `end_time - start_time` |
| `current_len` | int | Queue length at last operation |
| `max_len` | int | Maximum observed queue length |
| `min_len` | int | Minimum observed queue length |
| `put_attempt_count` | int | Total put calls |
| `put_success_count` | int | Puts that transferred items |
| `put_fail_count` | int | Puts that transferred nothing |
| `put_blocked_count` | int | Puts that had to wait (queue full) |
| `put_timeout_count` | int | Puts that timed out while waiting |
| `put_requested_items` | int | Total items requested to put |
| `put_moved_items` | int | Total items actually put |
| `get_attempt_count` | int | Total get calls |
| `get_success_count` | int | Gets that transferred items |
| `get_fail_count` | int | Gets that transferred nothing |
| `get_blocked_count` | int | Gets that had to wait (queue empty) |
| `get_timeout_count` | int | Gets that timed out while waiting |
| `get_requested_items` | int | Total items requested to get |
| `get_moved_items` | int | Total items actually got |
| `pop_attempt_count` | int | Total pop calls |
| `pop_success_count` | int | Pops that removed an item |
| `pop_fail_count` | int | Pops on an empty queue |
| `pop_moved_items` | int | Total items popped |
| `remove_attempt_count` | int | Total remove calls |
| `remove_success_count` | int | Removes that found the item |
| `remove_fail_count` | int | Removes where item was absent |
| `remove_moved_items` | int | Total items removed |
| `setitem_count` | int | Total `queue[i] = x` replacements |
| `max_put_batch` | int | Largest single put transfer |
| `max_get_batch` | int | Largest single get transfer |

### 8.2.4 Latency Probe

`QueueLatencyProbe` measures two kinds of time:

- **Stay time** — how long each item spends inside the queue (from put to get/pop/remove).
- **Wait time** — how long a blocked `gput` or `gget` call waits before it can proceed.

```python
lat = q.add_latency_probe()

# ... run the simulation ...
sim.run(until=100)

s = lat.stats()
print(f"items tracked:   {s['stay_count']}")
print(f"avg stay time:   {s['stay_time_avg']:.3f}")
print(f"min/max stay:    {s['stay_time_min']:.3f} / {s['stay_time_max']:.3f}")
print(f"get waits:       {s['get_wait_count']}  avg {s['get_wait_time_avg']:.3f}")
print(f"put waits:       {s['put_wait_count']}  avg {s['put_wait_time_avg']:.3f}")
```

If the probe is attached to a queue that already contains items, those items are **seeded** — their entry timestamp is set to the current simulation time. `seeded_item_count` reports how many items were seeded. `untracked_exit_count` reports items that left the queue without a matching entry timestamp (e.g. items that entered before the probe was attached and were not seeded).

#### Latency Fields

| Field | Type | Description |
|---|---|---|
| `start_time` | float | Probe start time |
| `end_time` | float | Time of last observed operation |
| `duration` | float | `end_time - start_time` |
| `tracked_item_count` | int | Items still inside the queue with tracked entry times |
| `seeded_item_count` | int | Items that were in the queue when probe attached |
| `untracked_exit_count` | int | Items that left without a tracked entry time |
| `stay_count` | int | Items with completed stay-time measurement |
| `stay_time_total` | float | Sum of all stay times |
| `stay_time_avg` | float | Mean stay time |
| `stay_time_min` | float | Shortest stay time |
| `stay_time_max` | float | Longest stay time |
| `put_wait_count` | int | Blocked put operations |
| `put_wait_timeout_count` | int | Blocked puts that timed out |
| `put_wait_time_total` | float | Sum of all put wait times |
| `put_wait_time_avg` | float | Mean put wait time |
| `put_wait_time_min` | float | Shortest put wait |
| `put_wait_time_max` | float | Longest put wait |
| `get_wait_count` | int | Blocked get operations |
| `get_wait_timeout_count` | int | Blocked gets that timed out |
| `get_wait_time_total` | float | Sum of all get wait times |
| `get_wait_time_avg` | float | Mean get wait time |
| `get_wait_time_min` | float | Shortest get wait |
| `get_wait_time_max` | float | Longest get wait |

### 8.2.5 Resetting and Detaching

```python
probe.reset()    # clear accumulated statistics; start fresh from now
probe.close()    # detach from queue endpoints; probe stops collecting

q.remove_probe(probe)  # detach via the queue's API (also calls close())
```

---

## 8.3 Resource Probes

`ResourceStatsProbe` works identically to `QueueStatsProbe` but tracks resource `amount` instead of queue length:

```python
from dssim import DSSimulation

sim = DSSimulation()
r = sim.resource(amount=0, capacity=100)

probe = r.add_stats_probe()

# ... run ...
sim.run(until=50)

s = probe.stats()
print(f"avg amount:       {s['time_avg_amount']:.2f}")
print(f"max amount:       {s['max_amount']:.2f}")
print(f"non-empty time:   {s['time_nonempty_ratio']*100:.1f}%")
print(f"full time:        {s['time_full_ratio']*100:.1f}%")
print(f"preempt count:    {s['preempt_count']}")
print(f"preempted amount: {s['preempted_amount']:.2f}")
```

### 8.3.1 Resource Statistics Fields

| Field | Type | Description |
|---|---|---|
| `start_time` | float | Probe start time |
| `end_time` | float | Time of `stats()` call |
| `duration` | float | Total observation window |
| `time_avg_amount` | float | Time-weighted average resource amount |
| `max_amount` | float | Peak resource amount |
| `min_amount` | float | Lowest observed amount |
| `time_nonempty_ratio` | float | Fraction of time amount > 0 |
| `time_full_ratio` | float | Fraction of time amount ≥ capacity |
| `put_count` | int | Successful put (add) operations |
| `get_count` | int | Successful get (consume) operations |
| `preempt_count` | int | Number of preemption events (DSPriorityResource only) |
| `preempted_amount` | float | Total amount reclaimed by preemption |
| `current_amount` | float | Amount at time of `stats()` call |

### 8.3.2 Flow Probe

`ResourceFlowProbe` tracks transferred amounts and rates — how much is being put in and taken out over time. It focuses on successful transfers only and computes throughput rates.

```python
flow = r.add_flow_probe()

# ... run the simulation ...
sim.run(until=100)

s = flow.stats()
print(f"put events: {s['put_event_count']}  total amount: {s['put_amount_total']:.1f}")
print(f"get events: {s['get_event_count']}  total amount: {s['get_amount_total']:.1f}")
print(f"net amount: {s['net_amount_total']:.1f}")
print(f"put rate:   {s['put_rate']:.2f} units/s")
print(f"get rate:   {s['get_rate']:.2f} units/s")
```

#### Flow Fields

| Field | Type | Description |
|---|---|---|
| `start_time` | float | Probe start time |
| `end_time` | float | Time of `stats()` call |
| `duration` | float | `end_time - start_time` |
| `put_event_count` | int | Number of successful put events |
| `get_event_count` | int | Number of successful get events |
| `put_amount_total` | float | Total amount added |
| `get_amount_total` | float | Total amount consumed |
| `net_amount_total` | float | `put_amount_total - get_amount_total` |
| `avg_put_amount` | float | Mean amount per put event |
| `avg_get_amount` | float | Mean amount per get event |
| `max_put_amount` | float | Largest single put |
| `max_get_amount` | float | Largest single get |
| `put_rate` | float | `put_amount_total / duration` |
| `get_rate` | float | `get_amount_total / duration` |
| `unexpected_nempty_count` | int | `tx_nempty` events with no amount increase (diagnostic) |
| `unexpected_nfull_count` | int | `tx_nfull` events with no amount decrease (diagnostic) |
| `current_amount` | float | Resource amount at last observation |

### 8.3.3 Latency Probe

`ResourceLatencyProbe` measures how long blocked `gput` and `gget` calls wait before they can proceed. It only records operations that actually blocked — non-blocking calls are invisible to this probe.

```python
lat = r.add_latency_probe()

# ... run the simulation ...
sim.run(until=100)

s = lat.stats()
print(f"get waits:  {s['get_wait_count']}  avg {s['get_wait_time_avg']:.3f}  max {s['get_wait_time_max']:.3f}")
print(f"put waits:  {s['put_wait_count']}  avg {s['put_wait_time_avg']:.3f}  max {s['put_wait_time_max']:.3f}")
print(f"timeouts:   get {s['get_wait_timeout_count']}  put {s['put_wait_timeout_count']}")
```

#### Latency Fields

| Field | Type | Description |
|---|---|---|
| `start_time` | float | Probe start time |
| `end_time` | float | Time of `stats()` call |
| `duration` | float | `end_time - start_time` |
| `put_wait_count` | int | Blocked put operations |
| `put_wait_timeout_count` | int | Blocked puts that timed out |
| `put_wait_time_total` | float | Sum of all put wait times |
| `put_wait_time_avg` | float | Mean put wait time |
| `put_wait_time_min` | float | Shortest put wait |
| `put_wait_time_max` | float | Longest put wait |
| `get_wait_count` | int | Blocked get operations |
| `get_wait_timeout_count` | int | Blocked gets that timed out |
| `get_wait_time_total` | float | Sum of all get wait times |
| `get_wait_time_avg` | float | Mean get wait time |
| `get_wait_time_min` | float | Shortest get wait |
| `get_wait_time_max` | float | Longest get wait |

---

## 8.4 Custom Probes

The built-in probes cover queues and resources. For anything else — custom components, cross-component metrics, or specialised logging — you can write your own probe.

Any object with an `attach(component)` method can be registered via `add_probe()`. DSSim calls `attach` when the probe is added. The optional `close()` method is called automatically by `remove_probe()`.

```python
class MyQueueProbe:
    def attach(self, queue):
        self.queue = queue
        self.log = []
        logger = queue.sim.callback(self._on_event)
        queue.tx_changed.add_subscriber(logger, queue.tx_changed.Phase.PRE)
        self._logger = logger

    def _on_event(self, event):
        self.log.append((self.queue.sim.time, len(self.queue)))

    def close(self):
        self.queue.tx_changed.remove_subscriber(self._logger, self.queue.tx_changed.Phase.PRE)

sim = DSSimulation()
q = sim.queue(capacity=10)
probe = MyQueueProbe()
q.add_probe(probe)

sim.run(until=50)
print(probe.log)
```

The same pattern works for any component — attach to whichever publisher endpoints are relevant, collect whatever state you need in the callback, and clean up in `close()`.

---

## 8.5 Event-Level Probing with PRE Observers

For anything beyond built-in statistics, attach a `PRE` phase subscriber directly to any publisher endpoint:

```python
from dssim import DSSimulation

sim = DSSimulation()
q = sim.queue(capacity=5)

events_log = []

# A PRE observer on tx_nempty fires whenever an item enters the queue
logger = sim.callback(lambda e: events_log.append((sim.time, "nempty", len(q))))
q.tx_nempty.add_subscriber(logger, q.tx_nempty.Phase.PRE)

# A PRE observer on tx_nfull fires whenever space opens up
get_logger = sim.callback(lambda e: events_log.append((sim.time, "nfull", len(q))))
q.tx_nfull.add_subscriber(get_logger, q.tx_nfull.Phase.PRE)
```

This approach gives access to the raw event stream at any endpoint. PRE observers always run before any consumer can accept or reject the event, so the queue state at observation time is the state before any blocking wake-up is delivered.

---

## 8.6 Time-Series Logging

If you want a time series of queue length or resource amount sampled at regular intervals, drive it with a `DSTimer`:

```python
from dssim import DSSimulation
from dssim.pubsub.components.time import DSTimer

sim = DSSimulation()
q = sim.queue(capacity=20)

series = []
sampler = sim.callback(lambda e: series.append((sim.time, len(q))))

# Sample every 1 time unit
t = DSTimer(period=1.0, sim=sim)
t.tx.add_subscriber(sampler, t.tx.Phase.CONSUME)
t.start(t.period, float('inf'))

# ... run simulation ...
sim.run(until=100)
print(series[:5])
```

---

## 8.7 Event Tracing with `DSTrackableEvent`

Probes observe *components*. Sometimes you need to trace an *event itself* — to answer "which components handled this specific event, and in what order?"

This is most useful when an event is **reused and forwarded** through a chain of filter-like components. `DSDelay` is a typical example: it receives an event on its input endpoint and reschedules the same object to its output endpoint after a fixed delay. With a multi-hop chain like:

```
source → DSDelay(1) → DSDelay(2) → sink
```

it can be hard to tell which hops an event actually traversed, especially when routing conditions may have dropped it at some point.

### How it works

Wrap the event value in `DSTrackableEvent` before sending it. Every `send()` call in PubSubLayer2 is decorated with `@TrackEvent`, which appends `self` to the event's `.publishers` list as the event passes through each node. After the simulation runs, `.publishers` contains the complete traversal trail in order.

```python
from dssim import DSSimulation, DSTrackableEvent

sim = DSSimulation()

# Two-hop delay chain: source → delay1 → delay2 → sink
delay1 = sim.delay(1.0, name='delay1')
delay2 = sim.delay(2.0, name='delay2')

received = []
sink = sim.callback(lambda e: received.append(e), name='sink')

# Wire the chain
delay1.tx.add_subscriber(delay2.rx, delay1.tx.Phase.CONSUME)
delay2.tx.add_subscriber(sink,      delay2.tx.Phase.CONSUME)

# Wrap the event so it tracks its path
event = DSTrackableEvent("my_packet")
sim.signal(event, delay1.rx)

last_event_time, _ = sim.run(until=10)

print(f"arrived at t={last_event_time}")
print("traversal path:")
for node in event.publishers:
    print(f"  {node.name if hasattr(node, 'name') else node}")
```

Expected output:
```
arrived at t=3.0
traversal path:
  delay1.rx
  delay1.tx
  delay2.rx
  delay2.tx
  sink
```

### What goes into `.publishers`

Every subscriber and publisher node whose `send()` was called with this event is appended — callbacks, processes, futures, and publishers alike. The list is ordered by actual call sequence, which reflects both the routing tier order (PRE before CONSUME) and the time-delayed hops.

### Limitations

- **PubSubLayer2 only.** `DSTrackableEvent` is accepted by LiteLayer2 for API compatibility — you can pass it without errors — but LiteLayer2's `send()` is not decorated with `@TrackEvent`, so the `.publishers` list will remain empty.
- **Same object must be forwarded.** Components that copy or transform the event (creating a new object) break the trail at that point — only hops that pass the original `DSTrackableEvent` instance are tracked.
- **Not a replacement for probes.** Probes give you statistics over many events; `DSTrackableEvent` gives you a single-event post-mortem trace. Use both when debugging complex routing.

---

## 8.8 Key Takeaways

- Probes are attached via `add_probe()` or the factory methods (`add_stats_probe()`, `add_ops_probe()`, `add_latency_probe()`, `add_flow_probe()`) and detached via `remove_probe()`.
- **Queue probes:** `QueueStatsProbe` (occupancy, throughput), `QueueOpsProbe` (per-operation success/fail/blocked/timeout counts), `QueueLatencyProbe` (item stay time, blocked wait time).
- **Resource probes:** `ResourceStatsProbe` (amount occupancy, preemption stats), `ResourceFlowProbe` (transfer rates, moved amounts), `ResourceLatencyProbe` (blocked wait time).
- `probe.reset()` clears accumulated data; `probe.close()` stops collection.
- Custom probes only need an `attach(component)` method; they can subscribe to any endpoint in `PRE` phase to remain non-intrusive.
- For time-series sampling, pair a `DSTimer` with a callback that reads component state on each tick.
- For single-event post-mortem tracing (e.g. debugging a forwarding chain), wrap the event in `DSTrackableEvent` and inspect `.publishers` after the run.
