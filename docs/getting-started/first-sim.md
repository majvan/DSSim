# First Simulation

This page walks through three short simulations, each adding one concept. By the end you will have seen scheduling, sleeping, inter-process communication via a queue, and conditional waiting.

All examples use **LiteLayer2** — the lightweight profile with no external dependencies beyond the standard library. Switching to PubSubLayer2 later requires only changing the construction argument.

---

## 1. Hello, Simulation

The smallest useful simulation: one process that wakes up, prints something, sleeps, and prints again.

```python
from dssim import DSSimulation, LiteLayer2

sim = DSSimulation(layer2=LiteLayer2)

async def worker():
    print(f"t={sim.time}  start")
    await sim.wait(3)            # sleep for 3 time units
    print(f"t={sim.time}  done")

sim.schedule(0, worker())        # schedule the coroutine to start at t=0
sim.run(until=10)
```

Output:

```
t=0  start
t=3  done
```

Key points:

- `DSSimulation(layer2=LiteLayer2)` creates the simulation engine.
- `await sim.wait(N)` suspends the coroutine for `N` time units and returns `None` on timeout. Generator code uses `yield from sim.gwait(N)` instead.
- `sim.schedule(delay, coroutine)` enqueues the coroutine to start after `delay` time units from now.
- `sim.run(until=N)` advances time until no more events remain or time reaches `N`.

---

## 2. Two Processes

Scheduling multiple processes that run concurrently — each with its own timeline.

```python
from dssim import DSSimulation, LiteLayer2

sim = DSSimulation(layer2=LiteLayer2)

async def source():
    for i in range(3):
        print(f"t={sim.time}  source sends {i}")
        await sim.wait(2)

async def monitor():
    await sim.wait(1)            # offset by 1 so we interleave
    for i in range(3):
        print(f"t={sim.time}  monitor tick")
        await sim.wait(2)

sim.schedule(0, source())
sim.schedule(0, monitor())
sim.run(until=10)
```

Output:

```
t=0  source sends 0
t=1  monitor tick
t=2  source sends 1
t=3  monitor tick
t=4  source sends 2
t=5  monitor tick
```

Both processes run in the same event loop. DSSim advances time to the next scheduled event and resumes whichever process is due, so the output interleaves naturally without threads.

---

## 3. Producer and Consumer via Queue

Real models need components to hand data to each other. A queue decouples the producer's pace from the consumer's pace.

```python
from dssim import DSSimulation, LiteLayer2

sim = DSSimulation(layer2=LiteLayer2)
q = sim.queue(name="pipe")       # unbounded FIFO queue

async def producer():
    for item in ["A", "B", "C"]:
        print(f"t={sim.time}  produce {item!r}")
        await q.put(item)        # blocks if queue is full (not here — unbounded)
        await sim.wait(2)        # wait before producing the next item

async def consumer():
    while True:
        item = await q.get(timeout=20)   # blocks until an item arrives
        if item is None:
            print(f"t={sim.time}  consumer timed out, stopping")
            break
        print(f"t={sim.time}  consume {item!r}")
        await sim.wait(3)                # processing time

sim.schedule(0, producer())
sim.schedule(0, consumer())
sim.run(until=30)
```

Output:

```
t=0  produce 'A'
t=0  consume 'A'
t=2  produce 'B'
t=3  consume 'B'
t=4  produce 'C'
t=6  consume 'C'
t=26  consumer timed out, stopping
```

Key points:

- `sim.queue(name=...)` creates a queue. Use `await q.put(item)` to enqueue and `await q.get(timeout=N)` to dequeue.
- Both calls block if the queue is full / empty respectively and return `None` on timeout.
- The consumer's `timeout=20` causes it to stop when no new item arrives within 20 time units after the last one.

---

## What to Read Next

| Goal | Chapter |
|---|---|
| Understand the layer stack and profiles | [Chapter 2: Core Design Concepts](../user-guide/02-core-concepts.md) |
| Learn publisher-subscriber wiring and subscription contexts | [Chapter 3: Publisher-Subscriber Principle](../user-guide/03-pubsub-layer2.md) |
| Use condition filtering, filters, and circuits | [Chapter 4: Condition Filtering](../user-guide/04-condition-filtering.md) |
| Write full process-oriented models | [Chapter 5: Processes](../user-guide/05-processes.md) |
| Use Queue, Container, Resource | [Chapter 6: Components](../user-guide/06-components.md) |
| Port code from SimPy or salabim | [Chapter 9: Shim Layers](../user-guide/09-shims.md) |
