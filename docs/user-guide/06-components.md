# Chapter 6: Basic Generic Components

## 6.1 Overview

DSSim ships three stateful simulation components that model the most common coordination patterns:

| Component | What it holds | Blocks when... |
|---|---|---|
| `DSQueue` | ordered items (objects) | full on put / empty on get |
| `DSContainer` | object counts (unordered) | full on put / empty on get |
| `DSResource` | numeric amount | exhausted on get / full on put |

All three are available in `PubSubLayer2`. In LiteLayer2, low-overhead equivalents exist for queue/resource (`DSLiteQueue`, `DSLiteResource`) — see [Section 6.7](#67-lite-equivalents).

---

## 6.2 Queue

`DSQueue` is a FIFO buffer with optional capacity. Producers put items; consumers get them.

### 6.2.1 Creating a Queue

```python
from dssim import DSSimulation

sim = DSSimulation()

q = sim.queue(capacity=10)   # bounded FIFO
q_inf = sim.queue()          # unbounded FIFO (default capacity=inf)
```

### 6.2.2 Non-blocking put and get

```python
result = q.put_nowait("item")   # None if full, else the item tuple
item   = q.get_nowait()         # None if empty, else the item
```

Non-blocking operations return immediately. `put_nowait` returns `None` if the buffer is already at capacity. `get_nowait` returns `None` if the buffer is empty.

### 6.2.3 Blocking put and get

From inside a process (coroutine style):

```python
async def producer(q):
    await q.put(5, "item")      # timeout=5, blocks until there is space

async def consumer(q):
    item = await q.get(timeout=10)      # blocks until there is an item
    if item is None:
        print("timed out")
```

Generator style:

```python
def producer(q):
    yield from q.gput(5, "item")

def consumer(q):
    item = yield from q.gget(timeout=10)
```

`timeout` is always explicit. When the timeout expires without success, the call returns `None`.

### 6.2.4 Conditional get

```python
# Get only an item for which cond(item) is True
item = await q.get(timeout=5, cond=lambda e: e.priority > 2)
```

A condition on `get` restricts which head item is eligible. If the head item does not pass the condition, the getter stays blocked even if the queue is non-empty.

### 6.2.5 Queue policies (FIFO, LIFO, Priority)

The default policy is FIFO. Pass a custom buffer object for other orderings:

```python
from dssim.base_components import DSLifoOrder, DSKeyOrder

q_lifo = sim.queue(policy=DSLifoOrder())                    # LIFO (stack)
q_prio = sim.queue(policy=DSKeyOrder(key=lambda e: e.priority))  # min-priority first
```

`DSKeyOrder` uses Python's `heapq` internally. Equal-priority items maintain insertion order.

### 6.2.6 Queue internals and observability

Three publisher endpoints are exposed:

| Endpoint | Fires when |
|---|---|
| `q.tx_nempty` | queue transitions from empty to non-empty |
| `q.tx_nfull` | queue transitions from full to non-full |
| `q.tx_changed` | any change (superset of above) |

These endpoints are used internally to wake blocked getters/putters. They can also be subscribed to for monitoring:

```python
monitor = sim.callback(lambda e: print(f"queue changed: len={len(q)}"))
q.tx_changed.add_subscriber(monitor, q.tx_changed.Phase.PRE)
```

### 6.2.7 Round-robin notification

By default subscribers in each tier are notified in insertion order (`NotifierDict`). To distribute wake-ups fairly among multiple consumers (e.g. load-balance 10 workers), use `NotifierRoundRobin`:

```python
from dssim import NotifierRoundRobin

q = sim.queue(
    capacity=100,
    nempty_ep=sim.publisher(name="q.tx_nempty", notifier=NotifierRoundRobin()),
)
```

With `NotifierRoundRobin`, each new event starts notifying from the subscriber that follows the last successful consumer, giving all consumers equal opportunity over time.

For priority ordering, pass `NotifierPriority` and specify a `priority` on each `add_subscriber` call.

### 6.2.8 Condition helpers

`DSQueue` provides three condition helper factories:

| Factory | Default wait tier | Subscribes to | On successful check |
|---|---|---|---|
| `q.get_cond(amount=1, cond=AlwaysTrue)` | CONSUME | `q.tx_nempty` (or `q.tx_changed` if `cond` given) | Dequeues the item(s) |
| `q.put_cond(*items)` | CONSUME | `q.tx_nfull` | Enqueues the items |
| `q.change_cond(cond=lambda q: True)` | PRE | `q.tx_changed` | Observes; no dequeue |

Each returns an `ICondition` object with helper waits (`wait`, `gwait`, `check_and_wait`, `check_and_gwait`).

Direct usage (recommended for queue claiming semantics):

```python
# wait for a specific item and consume it
getc = q.get_cond(cond=lambda item: item.type == "DATA")
item = yield from getc.check_and_gwait(timeout=10)

# wait until space opens and enqueue
putc = q.put_cond("ACK")
result = yield from putc.check_and_gwait(timeout=10)  # ('ACK',)

# non-consuming queue-state watch
chg = q.change_cond(cond=lambda qq: len(qq) >= 3)
event = yield from chg.check_and_gwait(timeout=10)
```

Filter wrapping is for composition (`|` / `&`) and runs in PRE tier:

```python
# compose: wake when either of two queues has an item
f0 = sim.filter(q0.get_cond())
f1 = sim.filter(q1.get_cond())
result = yield from (f0 | f1).check_and_gwait(20)
```

If you need full manual control, you can still use the low-level form:

```python
cond = q.get_cond()
with sim.consume(q.tx_nempty):
    item = yield from sim.gwait(timeout=10, cond=cond)
```

**`get_cond` vs `change_cond`:** `get_cond` *consumes* (dequeues) on success. `change_cond` only *observes* — it does not remove items.

**`cond` parameter types differ:** `get_cond(cond=...)` takes an *item predicate* (`cond(item) -> bool`). `change_cond(cond=...)` takes a *queue predicate* (`cond(queue) -> bool`).

---

## 6.3 Container

`DSContainer` is like `DSQueue` but stores _counts_ of objects rather than individual items. It is unordered: you track how many of each object type are present, not in what sequence they arrived.

```python
from dssim import DSSimulation

sim = DSSimulation()
c = sim.container(capacity=20)
```

Typical use: modeling pools of agents, token counts, or anonymous units.

```python
# Put: add objects to the container
await c.put(5, "agent_A", "agent_A", "agent_B")   # 2×A, 1×B
result = c.put_nowait("agent_A")

# Get: remove one occurrence of a specific object
objs = await c.get_n(5, "agent_A")   # returns list, e.g. ["agent_A"]
obj = c.get_nowait()   # returns any object

# Remove unconditionally
c.remove("agent_B")

# Inspect
print(c.size)          # total item count
print(c.container)     # dict: {obj: count, ...}
```

Like `DSQueue`, blocking `put` / `get` accept a `timeout` and return `None` on expiry.

---

## 6.4 Resource

`DSResource` models a pool of abstract numeric quantity. You do not get specific _items_ out of a resource — you get an _amount_. This is suitable for modeling bandwidth, tokens, fuel, CPU time, or memory.

```python
from dssim import DSSimulation

sim = DSSimulation()
r = sim.resource(amount=0, capacity=100)   # starts empty, can hold up to 100
```

### 6.4.1 Basic put and get

```python
# Producer: add to pool
await r.put(timeout=5)              # put 1 unit
await r.put_n(timeout=5, amount=10) # put 10 units

# Consumer: take from pool
got = await r.get(timeout=5)        # get 1 unit; returns amount got or None on timeout
got = await r.get_n(timeout=5, amount=5)   # get up to 5 units

# Non-blocking
r.put_nowait()
r.put_n_nowait(amount=10)
r.get_nowait()
r.get_n_nowait(amount=5)
```

Generator variants exist for all: `gput`, `gput_n`, `gget`, `gget_n`.

### 6.4.2 Publisher endpoints

`DSResource` exposes:

| Endpoint | Fires when |
|---|---|
| `r.tx_nempty` | pool transitions from zero to non-zero |
| `r.tx_nfull` | pool transitions from capacity to below capacity |
| `r.tx_changed` | any change |

### 6.4.3 Condition helper: get_cond

`DSResource` (and `DSPriorityResource`) expose a `get_cond()` factory for use with `sim.filter()`:

```python
cond = r.get_cond(amount=2)   # or get_cond(amount=1, priority=1, preempt=True)
f = sim.filter(cond)
result = yield from f.check_and_gwait(timeout=10)
amount = f.cond.cond_value()   # amount actually acquired
```

`get_cond` subscribes to `r.tx_nempty`. On each condition check it attempts immediate acquisition; for `DSPriorityResource` this also handles preemption. The returned amount is available via `cond_value()`.

Combining two resources in a circuit (wait for both):

```python
f0 = sim.filter(r0.get_cond())
f1 = sim.filter(r1.get_cond())
result = yield from (f0 & f1).check_and_gwait(timeout=20)
```

### 6.4.4 PriorityResource

`DSPriorityResource` supports preemption: a higher-priority requester can take resources back from lower-priority holders.

```python
from dssim.pubsub.components.resource import DSResourcePreempted

r = sim.priority_resource(amount=1, capacity=1)

async def holder(priority):
    try:
        got = await r.get(timeout=5, priority=priority, owner=sim.pid)
        await sim.sleep(10)
        r.put_nowait()
    except DSResourcePreempted as exc:
        print(f"preempted by {exc.by} (priority={exc.priority})")
```

When a higher-priority request cannot be satisfied from the free pool, lower-priority holders are preempted one by one (largest numeric priority first, i.e. weakest holder first) until enough resource is freed.

`DSMutex` is a special case of `DSPriorityResource` with `capacity=1`:

```python
mu = sim.priority_resource(capacity=1)
async def critical_section():
    await mu.get(timeout=5, owner=sim.pid)
    ...  # exclusive access
    mu.put_nowait()
```

---

## 6.5 DSAgent Queue and Resource Helpers

When using `DSAgent`, queue and resource operations are available as agent methods. These do the same thing as calling the component methods directly, but also handle `DSAbortException` propagation:

```python
class Worker(DSAgent):
    async def process(self):
        item = await self.pop(queue, timeout=5)          # queue.get(...)
        n = await self.get_n(resource, amount=2)         # resource.get_n(...)
        await self.put(resource)                         # resource.put(...)
        await self.enter(container, timeout=5)           # container.put(...)
        await self.pop(container, timeout=5)             # container.get(...)
```

Available helpers:

| Agent method | Container op | Resource op |
|---|---|---|
| `enter(container)` | `container.put(self)` | — |
| `pop(container)` | `container.get()` | — |
| `enter_nowait(container)` | `container.put_nowait(self)` | — |
| `get(resource)` | — | `resource.get()` |
| `get_n(resource, amount)` | — | `resource.get_n(amount)` |
| `put(resource)` | — | `resource.put()` |
| `put_n(resource, amount)` | — | `resource.put_n(amount)` |

---

## 6.6 Timer and State

### Timer

`DSTimer` is a periodic clock component. It fires `tx` events at a fixed period:

```python
from dssim.pubsub.components.time import DSTimer

sim = DSSimulation()
t = DSTimer(period=1.0, repeats=10, sim=sim)
cb = sim.callback(lambda e: print(f"tick: {e}"))
t.tx.add_subscriber(cb, t.tx.Phase.CONSUME)

t.start(t.period, t.counter)  # start ticking
sim.run(until=15)
```

Control methods:

```python
t.start(period=1.0, repeats=5)  # start or restart
t.stop()                         # stop; resets remaining period
t.pause()                        # pause; preserves remaining period
t.resume()                       # continue from paused position
```

### State

`DSState` is a dict-like component that publishes changes via `tx_changed`:

```python
s = sim.state()
s["mode"] = "idle"    # triggers tx_changed event
s.update({"mode": "running", "count": 0})  # triggers tx_changed for each key
```

Waiting for a state change:

```python
async def monitor():
    with sim.consume(s.tx_changed):
        await sim.wait(timeout=10, cond=lambda e: e.get("mode") == "running")
```

---

## 6.7 Lite Equivalents

For scenarios where pubsub overhead matters more than expressiveness, `DSLiteQueue` and `DSLiteResource` provide direct sentinel-based blocking without the pubsub machinery:

```python
from dssim.lite.components.litequeue import DSLiteQueue
from dssim.lite.components.literesource import DSLiteResource

lq = DSLiteQueue(capacity=10, sim=sim)       # explicit Lite variant
lr = DSLiteResource(amount=0, capacity=100, sim=sim)
```

APIs are identical to `DSQueue` and `DSResource` (`gput`, `gget`, `put_nowait`, etc.). The key differences:

- No `tx_nempty` / `tx_nfull` / `tx_changed` endpoints (no pubsub observers).
- No condition parameter on `get` (all gets accept any head item).
- Lower dispatch overhead in benchmarks (typically 2–5× faster in contended scenarios).

Use `DSLiteQueue` when you do not need monitoring endpoints, conditional gets, or custom notifier policies.

---

## 6.8 Key Takeaways

- `DSQueue` holds ordered objects; `DSContainer` holds counted objects; `DSResource` holds numeric amount.
- All blocking operations accept a `timeout` and return `None` on expiry.
- `DSQueue` supports FIFO, LIFO, and priority ordering via the `policy` parameter.
- Publisher endpoints (`tx_nempty`, `tx_nfull`, `tx_changed`) can be subscribed to for monitoring without interfering with blocking semantics.
- `NotifierRoundRobin` on the `nempty_ep` distributes wake-ups fairly across multiple waiters.
- **Condition helpers** (`get_cond`, `put_cond`, `change_cond` on queues; `get_cond` on resources) wrap acquisition logic in `ICondition` objects for use with `sim.filter()` — enabling composable OR/AND waits across multiple components without manual `with sim.consume(...)` blocks.
- `DSAgent` provides ergonomic wrappers for queue and resource operations inside agent processes.
- Use `DSLiteQueue` / `DSLiteResource` when throughput matters more than event routing expressiveness.
