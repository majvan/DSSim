# Chapter 9: Shim Layers for Other Frameworks

## 9.1 Overview

DSSim provides thin compatibility shims so that code written for other DES frameworks can run on top of DSSim with minimal changes. These shims are API-compatibility layers — they expose familiar class and function names while delegating the actual simulation work to DSSim's engine.

Three shims are available:

| Module | Target framework | Import path |
|---|---|---|
| SimPy shim | SimPy 4 | `dssim.pubsub.parity.simpy` |
| salabim shim | salabim | `dssim.pubsub.parity.salabim` |
| asyncio shim | Python `asyncio` | `dssim.pubsub.parity.asyncio` |

**Scope note**: The shims cover the most common subset of each framework's API. They are designed for migration and experimentation, not as byte-for-byte behavioral clones.

---

## 9.2 SimPy Shim

### 9.2.1 Importing

```python
from dssim.pubsub.parity.simpy import (
    Environment,
    Event,
    Process,
    AnyOf,
    AllOf,
    Resource,
    PriorityResource,
    PreemptiveResource,
    Store,
    FilterStore,
    PriorityStore,
    Interrupt,
)
```

### 9.2.2 Basic SimPy patterns

The shim mirrors the SimPy 4 API surface:

```python
import dssim.pubsub.parity.simpy as simpy

def car(env):
    while True:
        print(f"Start parking at {env.now}")
        yield env.timeout(5)
        print(f"Start driving at {env.now}")
        yield env.timeout(2)

env = simpy.Environment()
env.process(car(env))
env.run(until=15)
```

Key mapped items:

| SimPy | DSSim equivalent |
|---|---|
| `Environment` | `DSSimulation` subclass with `now` / `run(until=)` / `process()` / `timeout()` |
| `Event` | `DSFuture`-backed event with `succeed()` / `fail()` / `triggered` |
| `Process` | `DSProcess` with `interrupt()` |
| `AnyOf(env, events)` | `DSCircuit` OR of `DSFuture` objects |
| `AllOf(env, events)` | `DSCircuit` AND of `DSFuture` objects |
| `Resource` | `dssim.pubsub.components.resource.DSResource` |
| `PriorityResource` | `DSPriorityResource` |
| `PreemptiveResource` | `DSPriorityResource` with preemption |
| `Store` | `DSQueue` |
| `FilterStore` | `DSQueue` with conditional `get` |
| `PriorityStore` | `DSQueue` with `DSKeyQueue` policy |

### 9.2.3 Process interruption

SimPy's interrupt pattern is supported:

```python
def interruptible(env):
    try:
        yield env.timeout(10)
    except simpy.Interrupt as i:
        print(f"interrupted: {i.cause}")

def disruptor(env, process):
    yield env.timeout(3)
    process.interrupt("cancel")

env = simpy.Environment()
p = env.process(interruptible(env))
env.process(disruptor(env, p))
env.run()
```

### 9.2.4 AnyOf / AllOf

```python
def waiter(env, e1, e2):
    result = yield env.any_of([e1, e2])
    print(f"one of them fired: {result}")
    result = yield env.all_of([e1, e2])
    print(f"both fired: {result}")
```

---

## 9.3 salabim Shim

The salabim shim maps salabim's component-centric API to DSSim:

```python
import dssim.pubsub.parity.salabim as sim_sal

class Car(sim_sal.Component):
    def process(self):
        while True:
            yield self.hold(5)   # park
            yield self.hold(2)   # drive

env = sim_sal.Environment()
Car(name="car_0")
env.run(till=15)
```

Mapped names:

| salabim | DSSim equivalent |
|---|---|
| `Environment` | `DSSimulation` subclass with `now()` |
| `Component` | `DSAgent` subclass (auto-schedules `process()`) |
| `ComponentGenerator` | `PCGenerator` |
| `Store` | `DSContainer` |
| `Queue` | `DSQueue` |
| `Resource` | `DSResource` |
| `State` | `DSState` |

The `hold(duration)` pattern inside `Component.process()` maps to `await self.sim.sleep(duration)` internally.

---

## 9.4 asyncio Shim

The asyncio shim lets you run DSSim processes as if they were `asyncio` coroutines. It is useful when porting code that uses `asyncio`'s event loop conventions, or when testing async logic without a real event loop:

```python
from dssim.pubsub.parity.asyncio import DSAsyncSimulation, Task, Timeout, CancelledError

sim = DSAsyncSimulation()

async def my_coroutine():
    await sim.sleep(3)
    return 42

task = Task(my_coroutine(), sim=sim)
task.schedule(0)
result = sim.run_until_complete(task)
print(result)   # 42
```

Key classes:

| asyncio | DSSim equivalent |
|---|---|
| `asyncio.get_event_loop()` | `DSAsyncSimulation` instance |
| `asyncio.Task` | `Task(coroutine, sim=sim)` |
| `asyncio.TimeoutError` | `Timeout` context (wraps `DSTimeoutContext`) |
| `asyncio.CancelledError` | `CancelledError` (subclass of `DSAbortException`) |
| `asyncio.Future` | `DSFuture` |
| `asyncio.gather(...)` | `DSCircuit` AND of futures |
| `loop.run_until_complete(coro)` | `sim.run_until_complete(coro)` |
| `loop.run_forever()` | `sim.run_forever()` |

The `DSAsyncSimulation` also supports `create_task`, `create_future`, and `asynccontextmanager` utilities for porting asyncio code.

---

## 9.5 Migration Notes

### From SimPy

1. Replace `import simpy` with `import dssim.pubsub.parity.simpy as simpy`.
2. Most generator-based processes work without change.
3. `env.event()` maps to a DSSim future — check `.value` instead of `.result` for the resolved value.
4. `Resource.request()` / `Resource.release()` context manager semantics are supported.
5. `AnyOf` / `AllOf` are `yield env.any_of(...)` / `yield env.all_of(...)`.

### From salabim

1. Replace `import salabim` with `import dssim.pubsub.parity.salabim as salabim`.
2. `Component.process()` generators work without change.
3. `hold()`, `passivate()`, `activate()` are mapped.
4. `Monitor` / statistics collection: use DSSim probes instead (see [Chapter 8](08-probes.md)).

### Migrating to Native DSSim

After the shim is working, the next step is replacing shim classes with DSSim native equivalents:

- `Environment` → `DSSimulation`
- `Component` → `DSAgent`
- `Store` → `DSQueue` or `DSContainer`
- Generator-only process → generator or `async def` process
- `yield env.timeout(n)` → `await sim.sleep(n)` (async) or `yield from sim.gsleep(n)` (generator)
- `env.event()` → `sim.future()`

---

## 9.6 Key Takeaways

- Three shims let SimPy, salabim, and asyncio code run on DSSim with minimal changes.
- The SimPy shim covers `Environment`, `Event`, `Process`, `AnyOf`/`AllOf`, and the main resource/store types.
- The salabim shim maps `Component` to `DSAgent` and `Environment` to `DSSimulation`.
- The asyncio shim wraps `DSSimulation` with event-loop-like methods and maps `Task`/`Future`/`Timeout`.
- Shims are a migration starting point; native DSSim APIs give access to pubsub, condition filtering, and probes that shims do not expose.
- For a side-by-side capability comparison with SimPy and salabim, see [Chapter 10](10-feature-comparison.md).
