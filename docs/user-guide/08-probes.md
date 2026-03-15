# Chapter 8: Probes and Probing

## 8.1 What Are Probes?

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

### 8.2.3 Resetting and Detaching

```python
probe.reset()    # clear accumulated statistics; start fresh from now
probe.close()    # detach from queue endpoints; probe stops collecting

q.remove_probe(probe)  # detach via the queue's API (also calls close())
```

### 8.2.4 Custom Probes

Any object with an `attach(queue)` method can be used as a probe:

```python
class MyQueueProbe:
    def attach(self, queue):
        from dssim.pubsub.pubsub import DSPub, DSSub
        self.queue = queue
        self.log = []
        self._sub = DSSub(sim=queue.sim, cond=lambda e: True)
        self._sub.send = self._on_event
        queue.tx_changed.add_subscriber(self._sub, DSPub.Phase.PRE)

    def _on_event(self, event):
        self.log.append((self.queue.sim.time, len(self.queue)))

    def close(self):
        from dssim.pubsub.pubsub import DSPub
        self.queue.tx_changed.remove_subscriber(self._sub, DSPub.Phase.PRE)

probe = MyQueueProbe()
q.add_probe(probe)
```

The only requirement is that the probe object has an `attach(component)` method. DSSim calls it when the probe is added. The `close()` method is optional but called automatically by `remove_probe()`.

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

---

## 8.4 Event-Level Probing with PRE Observers

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

## 8.5 Time-Series Logging

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

## 8.6 Key Takeaways

- Probes are attached via `add_probe()` / `add_stats_probe()` and detached via `remove_probe()`.
- Built-in `QueueStatsProbe` and `ResourceStatsProbe` provide time-weighted occupancy, throughput, and (for priority resources) preemption statistics.
- `probe.reset()` clears accumulated data; `probe.close()` stops collection.
- Custom probes only need an `attach(component)` method; they can subscribe to any endpoint in `PRE` phase to remain non-intrusive.
- For time-series sampling, pair a `DSTimer` with a callback that reads component state on each tick.
