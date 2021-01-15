# DSSim — Discrete-Event Simulation Framework

DSSim is a Python framework for discrete-event simulation (DES). It advances time by jumping from one scheduled event to the next, making it well-suited for modelling systems where behavior is driven by events: hardware protocols, queuing systems, resource contention, multi-process coordination, and more.

**Full documentation: [majvan.github.io/DSSim](https://majvan.github.io/DSSim/)**

## Who It Is For

DSSim targets a wide audience — not just software engineers:

- **Hardware engineers** — describe bus protocols, pipeline stages, and signal flows using component endpoints wired together, close to how hardware is assembled.
- **Scientists and researchers** — model experiments, queuing phenomena, or multi-agent systems without writing a scheduler from scratch.
- **Software engineers** — build process-oriented models using Python generators and coroutines with familiar async idioms.

## Key Features

- **Two layer profiles** — `LiteLayer2` for maximum throughput; `PubSubLayer2` for routing-rich pub/sub with delivery tiers, condition filtering, and composable filter circuits.
- **Any Python object as an event** — no base class, no wrapping required.
- **Timeout on every blocking call** — `wait`, `get`, `put`, `sleep` all accept `timeout`; `None` is the universal "nothing happened" sentinel.
- **Condition filtering** — wake a process only when an event matches a predicate, a filter, a circuit of filters (AND/OR/reset), or a future's completion. No spurious wakeups in PubSubLayer2.
- **Publisher-subscriber with tiers** — PRE (observe), CONSUME (first-accept wins), POST_HIT, POST_MISS.
- **Built-in components** — `DSQueue`, `DSResource`, `DSPriorityResource`, `DSContainer`, `DSState`, `DSTimer`, and hardware models (UART, etc.).
- **Probes and statistics** — attach `QueueStatsProbe` / `ResourceStatsProbe` without modifying component code; custom probe types supported.
- **SimPy / salabim / asyncio shims** — migrate existing models without rewriting; migrated code and native DSSim code share the same event loop.
- **No external dependencies** — stdlib only at the core.

## Quick Start

```bash
pip install dssim
```

```python
from dssim import DSSimulation, LiteLayer2

sim = DSSimulation(layer2=LiteLayer2)

async def producer():
    for i in range(3):
        print(f"t={sim.time}  produce {i}")
        await sim.wait(2)

async def consumer():
    for _ in range(3):
        event = await sim.wait(3)
        print(f"t={sim.time}  tick")

sim.schedule(0, producer())
sim.schedule(0, consumer())
sim.run(until=10)
```

For local development from source, use editable mode:

```bash
pip install -e .
```

More examples in [`examples/lite/`](examples/lite/) and [`examples/pubsub/`](examples/pubsub/).

## Choosing a Profile

| Situation | Profile |
|---|---|
| Small or exploratory project | **PubSubLayer2** (default) |
| Debugging, probes, condition filtering needed | **PubSubLayer2** |
| Maximum throughput is the primary goal | **LiteLayer2** |
| Unsure | Start with **LiteLayer2**; switch when you hit the first blocker |

```python
sim = DSSimulation()                   # PubSubLayer2 — default
sim = DSSimulation(layer2=LiteLayer2)  # LiteLayer2
```

Switching is a one-line change at construction time.

## Documentation

Full documentation: **[majvan.github.io/DSSim](https://majvan.github.io/DSSim/)**

- [Getting Started](https://majvan.github.io/DSSim/getting-started/install/)
- [User Guide](https://majvan.github.io/DSSim/user-guide/)
- [Feature Comparison with SimPy and salabim](https://majvan.github.io/DSSim/user-guide/10-feature-comparison/)

## License

Apache 2.0
