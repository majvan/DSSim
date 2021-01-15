# Chapter 4: Condition Filtering

!!! note "PubSubLayer2"
    Everything in this chapter is specific to PubSubLayer2. LiteLayer2 has no condition evaluation machinery — subscriber wake-ups are driven entirely by queue/resource sentinel signals.

Condition filtering is the mechanism that prevents spurious wakeups. When a process or subscriber specifies a `cond`, the scheduler evaluates it against every incoming event _before_ resuming the caller. The caller only wakes when the condition passes — or when the timeout expires and `None` is returned.

---

## 4.1 Condition Types

A condition can be any of the following:

### Plain value — exact match

```python
event = await sim.wait(timeout=5, cond="ready")
# wakes only when the event equals "ready"
```

The condition is satisfied when `event == cond`.

### Callable — predicate

```python
event = await sim.wait(timeout=5, cond=lambda e: isinstance(e, int) and e > 10)
# wakes only when the event is an integer greater than 10
```

Any callable that takes one argument and returns a truthy value is a valid condition. This includes plain functions, methods, and `DSFilter` objects (which implement `__call__`).

### `DSFilter` — reusable, named condition

```python
ready = sim.filter(cond=lambda e: e.status == "ready")
event = await ready.wait(timeout=10)
```

`DSFilter` wraps a condition in a reusable object with additional signal-type control (see [Section 4.2](#42-dsfilter-and-signal-types)). Use `filter.wait()` to wait on it — see [Section 4.5](#45-waiting-on-a-filter-or-circuit) for details.


### `DSCircuit` — composed condition

```python
both_ready = filter_a & filter_b
event = await both_ready.wait(timeout=10)
```

`DSCircuit` combines multiple `DSFilter` objects with AND or OR logic (see [Section 4.3](#43-dscircuit-composing-filters)). Use `circuit.wait()` to wait on it — see [Section 4.5](#45-waiting-on-a-filter-or-circuit) for details.

### `DSFuture` / `DSProcess` — wait for completion

A `DSFuture` or `DSProcess` used as a condition makes the wait resolve when the future finishes (i.e., `.finished()` is `True`).

Every future has an internal publisher that fires a completion event when `finish()` is called. Two things are required for the wait to work:

- **subscription** — the waiting process must be subscribed to the future's internal publisher so the completion event reaches it
- **condition** — `cond=task` gates the wake-up: the process only resumes when `task.finished()` is `True`, ignoring any other events that may arrive

The preferred form is `task.wait()`, which handles both automatically:

```python
task = sim.process(worker_gen()).schedule(0)
result = await task.wait(timeout=10)
# result is None if the task did not finish within 10 time units
```

The equivalent explicit form using `sim.wait()` requires a subscription context manager alongside `cond=task`:

```python
with sim.consume(task):
    result = await sim.wait(cond=task, timeout=10)
```

`cond=task` alone is not enough — without the context manager, no completion event reaches the waiting process and the wait never resolves. The context manager alone is not enough either — without `cond=task`, the process wakes on the first event from any subscribed source, not specifically the task's completion.

### `AlwaysTrue` / `AlwaysFalse` — named sentinels

Two named callable constants are provided for clarity in situations where a literal `True` or `False` condition is intended:

```python
from dssim import AlwaysTrue, AlwaysFalse
```

**`AlwaysTrue`** — every event satisfies the condition. It is the default `cond` for all `wait()` calls, so omitting `cond` is equivalent to passing `AlwaysTrue` explicitly:

```python
event = await sim.wait(timeout=5)               # same as cond=AlwaysTrue
event = await sim.wait(timeout=5, cond=AlwaysTrue)
```

**`AlwaysFalse`** — no event ever satisfies the condition. The call can only return via timeout, making it a pure time-delay primitive:

```python
await sim.wait(timeout=3, cond=AlwaysFalse)    # sleeps exactly 3 time units
```

This is how `sim.sleep(3)` is implemented internally. `AlwaysFalse` is also the default condition for `check_and_wait()`: the pre-check runs first; if already satisfied the call returns immediately, otherwise it blocks until timeout — no random event will trigger an early wake-up.

### `None` — always true

Omitting `cond` or passing `None` is equivalent to `AlwaysTrue`: any event satisfies the condition. The explicit `AlwaysTrue` form is preferred when the intent should be clear in code.

---

## 4.1.1 Subscription is not automatic with `sim.wait(cond=...)`

!!! warning "Common pitfall"
    Using a condition in `sim.wait(cond=...)` does **not** automatically subscribe the process to any publisher. If no events reach the process, the condition is never evaluated and the wait blocks forever — or until timeout.

A frequent mistake is referencing task futures inside a plain lambda condition:

```python
# BROKEN — the process is not subscribed to task1 or task2's completion publishers.
# No completion event ever arrives, so the lambda is never evaluated.
await sim.wait(cond=lambda e: task1.finished() and task2.finished())
```

The condition is evaluated against each event that is *delivered to the process*. Without a subscription, no events arrive and the wait hangs indefinitely.

**The rule:**

| What you call | Subscribes automatically? | Tier | Publisher |
|---|---|---|---|
| `filter.wait(timeout)` | Yes | PRE | filter's own endpoints |
| `circuit.wait(timeout)` | Yes | PRE | all constituent filter endpoints |
| `task.wait(timeout)` | Yes | PRE | `task._finish_tx` (completion) |
| `future.wait(timeout)` | Yes | PRE | `future._finish_tx` (completion) |
| `queue.get(timeout)` | Yes | CONSUME | `queue.tx_nempty` or `queue.tx_changed` |
| `queue.put(timeout)` | Yes | CONSUME | `queue.tx_nfull` |
| `queue.wait(timeout)` | Yes | CONSUME | `queue.tx_nempty` or `queue.tx_changed` |
| `container.get(timeout)` | Yes | CONSUME | `container.tx_nempty` or `container.tx_changed` |
| `container.wait(timeout)` | Yes | CONSUME | `container.tx_nempty` or `container.tx_changed` |
| `resource.get_n(timeout)` | Yes | CONSUME | `resource.tx_nempty` |
| `resource.put_n(timeout)` | Yes | CONSUME | `resource.tx_nfull` |
| `stateful.wait(timeout)` | Yes | CONSUME | `component.tx_changed` |
| `queue.get_cond(...).check_and_wait(timeout)` | Yes | CONSUME | `queue.tx_nempty` or `queue.tx_changed` |
| `queue.put_cond(...).check_and_wait(timeout)` | Yes | CONSUME | `queue.tx_nfull` |
| `queue.change_cond(...).check_and_wait(timeout)` | Yes | PRE | `queue.tx_changed` |
| `sim.filter(queue.get_cond(...)).check_and_wait(timeout)` | Yes | PRE | `queue.tx_nempty` or `queue.tx_changed` |
| `sim.filter(queue.put_cond(...)).check_and_wait(timeout)` | Yes | PRE | `queue.tx_nfull` |
| `sim.filter(queue.change_cond(...)).check_and_wait(timeout)` | Yes | PRE | `queue.tx_changed` |
| `sim.filter(resource.get_cond(...)).check_and_wait(timeout)` | Yes | PRE | `resource.tx_nempty` |
| `sim.wait(cond=task)` | Yes — special case: process auto-subscribes when `cond` is a `DSFuture` | PRE | `task._finish_tx` |
| `sim.wait(cond=lambda …)` | **No** — you must subscribe manually | — | — |
| `sim.wait(cond=value)` | **No** — you must subscribe manually | — | — |
| `agent.wait(timeout, cond=…)` | **No** — delegates to `sim.wait` | — | — |

**Lambdas are opaque.** Even when you wrap a condition inside a `DSFilter`, the filter only sees a callable — it has no way to know that the lambda references `task1` or `task2` internally, so it still cannot subscribe to their publishers automatically. This is equally broken:

```python
# STILL BROKEN — the filter cannot introspect the lambda to find task1 or task2
done_a = sim.filter(cond=lambda e: task1.finished(), sigtype=SignalType.DEFAULT)
done_b = sim.filter(cond=lambda e: task2.finished(), sigtype=SignalType.DEFAULT)
await (done_a & done_b).wait(timeout=30)
```

The solution is to pass the tasks **directly as the condition**. When a `DSFilter` receives a `DSProcess` or `DSFuture` as its `cond`, it knows exactly which publisher to subscribe to:

```python
# CORRECT — the filter knows task1 and task2 are futures and subscribes to them
done_a = sim.filter(cond=task1, sigtype=SignalType.DEFAULT)
done_b = sim.filter(cond=task2, sigtype=SignalType.DEFAULT)
await (done_a & done_b).wait(timeout=30)
```

Or subscribe manually when using a lambda condition:

```python
# CORRECT — manual subscription covers both tasks
with sim.consume(task1) + sim.consume(task2):
    await sim.wait(cond=lambda e: task1.finished() and task2.finished(), timeout=30)
```

---

## 4.2 `DSFilter` and Signal Types

`DSFilter` is a reusable condition object. Use `sim.filter()` to create one:

```python
f = sim.filter(cond=lambda e: e > 100)
```

A `DSFilter` can be passed as the `cond` of any `wait` call, added as a subscriber to a publisher endpoint, or composed into a `DSCircuit`.

### Signal Types

The `sigtype` parameter controls how the filter behaves after it first matches:

| Signal type | Constant | Behaviour |
|---|---|---|
| Monostable | `SignalType.DEFAULT` | Once triggered, stays triggered. Subsequent events do not reset it. |
| Reevaluate | `SignalType.REEVALUATE` | Re-evaluates on every event. The signal state can toggle — it reflects whether the _latest_ event passed. |
| Pulsed | `SignalType.PULSED` | Triggers momentarily. Never stays in a triggered state; `finished()` always returns `None`. |

The tables below use a filter with `cond=lambda e: e > 0` and trace the filter's internal state through a sequence of events.

**Monostable (`SignalType.DEFAULT`)** — latches on first match, ignores everything after:

| Event | Condition `e > 0` | Filter state | Wakes waiter? |
|---|---|---|---|
| `5` | ✓ pass | **latched** | Yes |
| `-3` | ✗ fail | latched | — (already resolved) |
| `2` | ✓ pass | latched | — (already resolved) |

Once latched, the filter's state never changes. A late `wait()` on an already-latched filter returns immediately.

**Reevaluate (`SignalType.REEVALUATE`)** — reflects the current event; state can toggle back and forth:

| Event | Condition `e > 0` | Filter state | Wakes waiter? |
|---|---|---|---|
| `5` | ✓ pass | **high** | Yes |
| `-3` | ✗ fail | **low** | No — condition no longer met |
| `2` | ✓ pass | **high** | Yes — wakes again |
| `-1` | ✗ fail | **low** | No |

A process waiting on a reevaluate filter is woken every time the condition transitions from false to true. Useful for level-sensitive readiness conditions that can become un-ready.

**Pulsed (`SignalType.PULSED`)** — fires once per matching event, never latches:

| Event | Condition `e > 0` | Filter state | Wakes waiter? |
|---|---|---|---|
| `-3` | ✗ fail | idle | No |
| `5` | ✓ pass | **pulse** → idle | Yes |
| `2` | ✓ pass | **pulse** → idle | Yes — wakes again on next match |
| `-1` | ✗ fail | idle | No |

The filter fires a momentary pulse for each matching event and immediately returns to idle. `finished()` always returns `None` — there is no latched state to query.

```python
from dssim.pubsub.pubsub import SignalType

# monostable: once seen, stays True
f_latch = sim.filter(cond=lambda e: e == "done", sigtype=SignalType.DEFAULT)

# reevaluate: reflects current state
f_level = sim.filter(cond=lambda e: e > 0, sigtype=SignalType.REEVALUATE)

# pulsed: triggers once, never latches
f_pulse = sim.filter(cond=lambda e: e == "tick", sigtype=SignalType.PULSED)
```

### Checking a Filter Directly

A `DSFilter` is callable — it evaluates the condition and returns a bool:

```python
f = sim.filter(cond=lambda e: e > 5)
print(f(3))   # False
print(f(10))  # True
```

---

## 4.3 `DSCircuit` — Composing Filters

`DSCircuit` combines filters using Python's `|` (OR) and `&` (AND) operators. The result is another composable object that can be used anywhere a condition is accepted.

### OR — any condition matches

```python
f1 = sim.filter(cond=lambda e: e == "A")
f2 = sim.filter(cond=lambda e: e == "B")

either = f1 | f2
event = await either.wait(timeout=5)
# wakes when event is "A" or "B"
```

### AND — all conditions must match

```python
channel_ready = sim.filter(cond=lambda e: e.channel_ok)
credit_ok     = sim.filter(cond=lambda e: e.credits > 0)

both = channel_ready & credit_ok
event = await both.wait(timeout=10)
# wakes when a single event satisfies both
```

### Chaining

Operators chain naturally. Multiple filters of the same kind flatten into a single circuit:

```python
f1 | f2 | f3   # one OR circuit with three arms — not (f1 | f2) | f3
f1 & f2 & f3   # one AND circuit with three arms
```

Mixed operators follow Python precedence (`&` binds tighter than `|`):

```python
f1 | f2 & f3   # equivalent to f1 | (f2 & f3)
```

### Negation — reset semantics

Prefixing a filter with `-` inverts its role. A negated filter acts as a _resetter_: when its condition matches, it clears the latched state of **all positive filters** in the circuit, as if none of them had ever fired.

Consider a three-input circuit that resolves only when both `A` and `B` have been seen, unless `C` arrives to cancel the sequence:

```python
seen_a  = sim.filter(cond=lambda e: e == "A", sigtype=SignalType.DEFAULT)
seen_b  = sim.filter(cond=lambda e: e == "B", sigtype=SignalType.DEFAULT)
reset_c = sim.filter(cond=lambda e: e == "C")

ready = seen_a & seen_b & -reset_c
event = await ready.wait(timeout=10)
```

The event sequence below shows what happens to the circuit state at each step:

| Event | `seen_a` | `seen_b` | `-reset_c` | Circuit resolves? |
|---|---|---|---|---|
| `"A"` | ✓ latched | — | — | No — `seen_b` not yet seen |
| `"B"` | ✓ latched | ✓ latched | — | **Yes** — both positive filters satisfied |

If `C` arrives before both `A` and `B` are latched, the circuit resets:

| Event | `seen_a` | `seen_b` | `-reset_c` | Circuit resolves? |
|---|---|---|---|---|
| `"A"` | ✓ latched | — | — | No |
| `"C"` | ✗ cleared | ✗ cleared | fired | No — reset; state lost |
| `"B"` | — | ✓ latched | — | No — `seen_a` must be seen again |
| `"A"` | ✓ latched | ✓ latched | — | **Yes** |

The resetter targets the inner accumulated state of the positive filters — it does not affect the circuit's ability to resolve later once the positive conditions are re-satisfied.

### Return value

When a `DSCircuit` resolves, `wait` returns the last matching event. The circuit collects each filter's matched value internally; the caller receives the event that caused the final resolution.

---

## 4.4 Subscribing a Filter to a Publisher

A `DSFilter` or `DSCircuit` can be registered as a permanent subscriber on a publisher using `add_subscriber`. Events then flow through two levels of routing: the publisher dispatches to the filter, and the filter wakes any process waiting on it.

```python
f = sim.filter(cond=lambda e: e.type == "DATA")
pub.add_subscriber(f, pub.Phase.CONSUME)

# Later, in a process:
result = await f.wait(timeout=10)
```

The filter sits on the publisher permanently — it receives events even when no process is currently waiting on it. When `f.wait()` is called, the process suspends and is resumed the next time the filter matches an event from `pub`.

This pattern is useful when the filter needs to track state across multiple wait calls (e.g., a monostable filter that latches after seeing the first match):

```python
seen_init = sim.filter(cond=lambda e: e == "INIT", sigtype=SignalType.DEFAULT)
pub.add_subscriber(seen_init, pub.Phase.CONSUME)

# ... time passes, other code runs ...

# By the time we wait, "INIT" may have already been seen — check_and_wait handles this
result = await seen_init.check_and_wait(timeout=5)
```

### Permanent vs transient subscription

| | `add_subscriber` | `.wait()` |
|---|---|---|
| Lifetime | Permanent — survives across waits | Transient — active only during the `wait` call |
| Tier | Your choice (`CONSUME`, `PRE`, …) | Always PRE (observation-only) |
| State accumulation | Yes — filter state builds even when no process is waiting | No — filter only sees events while a process is blocked on it |
| Use when | The filter must track events continuously | A one-shot conditional wait is sufficient |

When using `add_subscriber` with a filter in the CONSUME tier, the filter acts as a consumer and claims the event if its condition matches. Use PRE if you want the filter to observe without consuming:

```python
pub.add_subscriber(f, pub.Phase.PRE)      # observe only
pub.add_subscriber(f, pub.Phase.CONSUME)  # compete for events
```

---

## 4.5 Waiting on a Filter or Circuit

Both `DSFilter` and `DSCircuit` expose a `.wait()` method. This is the **preferred** way to block on a condition:

```python
result = await my_filter.wait(timeout=10)
result = await my_circuit.wait(timeout=10)
```

### What `.wait()` does

Calling `filter.wait(timeout)` is equivalent to:

```python
with sim.observe_pre(filter):
    result = await sim.wait(timeout=timeout, cond=filter)
```

The key detail is `observe_pre`: the filter is subscribed to the **PRE tier** — the observation-only phase that runs before any consumer decision and cannot consume or block events. This means:

- The filter sees every event that passes through the publishers it is attached to.
- The filter never competes with actual consumers for events.
- Subscription and unsubscription are automatic — no `with` block, no publisher reference needed.

### Why not `with sim.consume(pub)`?

A common alternative is to subscribe manually in the CONSUME tier:

```python
# Avoid this pattern with filters and circuits
with sim.consume(pub):
    result = await sim.wait(timeout=10, cond=my_circuit)
```

This works superficially but is semantically wrong: the process enters the CONSUME tier and _competes_ for events. If the process consumes an event that a real consumer was supposed to handle, that consumer never sees it. The PRE tier used by `.wait()` avoids this entirely.

Use the manual pattern only when you intentionally want to consume events from a specific publisher endpoint.

### Pre-checking before blocking

`check_and_wait(timeout)` checks whether the condition is already satisfied before registering the wait. If it is, the method returns immediately with the cached event — no suspension needed:

```python
# if the filter already fired, returns immediately; otherwise blocks
result = await my_filter.check_and_wait(timeout=10)
```

This is useful for conditions that may have been satisfied before the current process started watching.

### Generator variants

For components written as plain generators (not coroutines), use:

```python
result = yield from my_filter.gwait(timeout=10)
result = yield from my_filter.check_and_gwait(timeout=10)
```

---

## 4.6 Advanced: Process and Future Conditions

`DSFuture` and `DSProcess` objects can be used directly as conditions. This enables patterns where one process waits for another to reach a specific state or produce a result.

### Waiting for a Future to resolve

A `DSFuture` is a promise: any process can wait on it, and all waiters wake simultaneously when `finish()` is called.

```python
async def initializer():
    await sim.sleep(3)           # simulate startup work
    init_done.finish({"port": 8080, "version": 2})

async def server():
    config = await sim.wait(cond=init_done)
    print(f"t={sim.time}: listening on port {config['port']}")

async def monitor():
    config = await sim.wait(cond=init_done)   # same future, multiple waiters
    print(f"t={sim.time}: monitor saw version {config['version']}")

init_done = sim.future()
sim.process(initializer()).schedule(0)
sim.process(server()).schedule(0)
sim.process(monitor()).schedule(0)
sim.run(until=10)
# t=3: listening on port 8080
# t=3: monitor saw version 2
```

All processes waiting on the same `DSFuture` receive the value passed to `finish()` and resume at the same simulation time. The future is permanently resolved after that — late arrivals that `wait(cond=init_done)` after `finish()` wake immediately.

### Waiting for a process to finish

A `DSProcess` is itself a `DSFuture` subtype. Using it as a `cond` blocks until the process completes and returns its value:

```python
async def worker():
    await sim.sleep(5)
    return 42

task = sim.process(worker()).schedule(0)

async def master():
    result = await sim.wait(cond=task)   # blocks until task.finished() is True
    print(f"worker returned {result}")   # worker returned 42
```

If the worker was aborted, `wait(cond=task)` still returns — `result` will be `None` and `task.exc` will hold the exception.

### Combining a process condition with a timeout

```python
async def master():
    result = await sim.wait(timeout=10, cond=task)
    if result is None:
        print("task did not finish in time")
    else:
        print(f"task returned {result}")
```

The timeout and the process condition are independent. Whichever fires first — process completion or timeout expiry — wakes the waiter. `None` always means timeout.

### Using a `DSFilter` around a process condition

A `DSFilter` can wrap a `DSProcess` condition and forward incoming events to the wrapped process for evaluation. The filter signals when the process returns a truthy value from its generator.

This pattern is useful when validation logic is stateful or async:

```python
async def threshold_checker():
    """Yields True the first time a value exceeds the threshold."""
    while True:
        event = yield   # receives forwarded events
        if event is not None and event > 100:
            return True  # signals the filter

checker = sim.process(threshold_checker())
f = sim.filter(cond=checker, forward_events=True)

result = await f.wait(timeout=20)
# result is the first event > 100 delivered to the filter
```

---

## 4.7 Advanced: Complex Circuits in Practice

The following patterns show how to compose filters and circuits for real coordination problems.

### Pattern 1: Ordered two-phase handshake

A monostable filter latches `True` permanently once it fires. Combining two monostable filters in AND produces a circuit that resolves only after _both_ events have been seen — in any order.

```python
from dssim.pubsub.pubsub import SignalType

req_seen = sim.filter(cond=lambda e: e == "REQUEST", sigtype=SignalType.DEFAULT)
ack_seen = sim.filter(cond=lambda e: e == "ACK",     sigtype=SignalType.DEFAULT)

handshake = req_seen & ack_seen
result = await handshake.wait(timeout=20)
# resolves as soon as both REQUEST and ACK have been delivered
# (order does not matter)
```

### Pattern 2: Arm / fire / cancel

A pulsed filter for the trigger event prevents it from latching while a negated filter resets the armed state on cancellation:

```python
armed  = sim.filter(cond=lambda e: e.type == "ARM")
cancel = sim.filter(cond=lambda e: e.type == "CANCEL")
fire   = sim.filter(cond=lambda e: e.type == "FIRE", sigtype=SignalType.PULSED)

# Resolves when: ARM has been seen AND FIRE arrives AND CANCEL has not appeared
trigger = armed & fire & -cancel
result = await trigger.wait(timeout=30)

if result is None:
    print("timed out — never triggered")
else:
    print(f"fired at t={sim.time}")
```

The `-cancel` resetter clears `armed` whenever a CANCEL event arrives, so a CANCEL after ARM but before FIRE prevents the trigger from ever resolving.

### Pattern 3: Any error from multiple sources

Three independent error conditions collapsed into one OR circuit:

```python
timeout_err = sim.filter(cond=lambda e: e.code == "TIMEOUT")
crc_err     = sim.filter(cond=lambda e: e.code == "CRC_FAIL")
overflow    = sim.filter(cond=lambda e: e.code == "OVERFLOW")

any_error = timeout_err | crc_err | overflow
fault = await any_error.wait(timeout=100)

if fault is not None:
    print(f"fault detected: {fault.code} at t={sim.time}")
```

### Pattern 4: Level-sensitive readiness with reevaluate

A `REEVALUATE` filter tracks the _current_ value of a condition, not whether it was ever true. Use this when a resource can become un-ready after being ready:

```python
link_up = sim.filter(
    cond=lambda e: e.link_state == "UP",
    sigtype=SignalType.REEVALUATE,
)
credits_ok = sim.filter(
    cond=lambda e: e.credits > 0,
    sigtype=SignalType.REEVALUATE,
)

can_send = link_up & credits_ok

# Blocks until both conditions are simultaneously true
event = await can_send.wait(timeout=50)
```

If `link_state` drops back to `"DOWN"` while waiting, `link_up` re-evaluates to `False` and the circuit goes dark again. The waiter stays blocked until both are true at the same time.

### Pattern 5: Sharing a circuit across processes

A `DSCircuit` holds state. If you share a circuit object between two processes, both processes observe the _same_ filter state. This is a useful way to model a shared global readiness condition but requires care: the first process to resolve the circuit latches its state.

If you need per-waiter isolation, create a fresh circuit for each waiter:

```python
def make_ready_circuit():
    chan_ok  = sim.filter(cond=lambda e: e.chan_ok,  sigtype=SignalType.DEFAULT)
    cred_ok  = sim.filter(cond=lambda e: e.cred_ok,  sigtype=SignalType.DEFAULT)
    return chan_ok & cred_ok

async def sender(i):
    circuit = make_ready_circuit()   # each sender gets its own instance
    await circuit.wait(timeout=20)
    print(f"sender {i} proceeding")
```

---

## 4.8 Key Takeaways

- Seven condition types: plain value (exact match), callable (predicate), `AlwaysTrue`/`AlwaysFalse` (named sentinels), `DSFilter` (reusable), `DSCircuit` (composed), `DSFuture`/`DSProcess` (completion), `None` (equivalent to `AlwaysTrue`).
- `DSFilter` signal types: monostable (`DEFAULT`) latches forever; reevaluate (`REEVALUATE`) reflects the current event; pulsed (`PULSED`) fires once without latching.
- `DSCircuit` composes filters with `|` (OR) and `&` (AND); negated filters (`-f`) act as resetters that clear positive filter state.
- **Prefer `await filter.wait(timeout)` / `await circuit.wait(timeout)`** over manual `with sim.consume(pub): await sim.wait(cond=...)`. The `.wait()` method subscribes via the PRE tier (observation-only), so the process never competes with real consumers for events.
- Use `check_and_wait(timeout)` when the condition may already be satisfied before the wait is registered — it returns immediately if so.
- `DSFuture.finish()` wakes all current and future waiters simultaneously; using a `DSProcess` as a condition waits for the process to return.
- Monostable AND circuits model "both events seen in any order"; reevaluate AND circuits model "both conditions simultaneously true right now".
- Per-waiter isolation requires creating a fresh circuit instance per waiter — shared circuit objects share state.
