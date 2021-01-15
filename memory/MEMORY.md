# DSSim Project Memory

## Architecture Overview
- Event-driven discrete simulation framework (Python)
- Core: `DSSimulation` with time-queue, pub/sub, process scheduling
- Generator-based (`yield from`) and coroutine-based (`async/await`) processes
- All components require `sim=` kwarg (or singleton)

## Key Files
- `dssim/simulation.py` - Main simulation engine (DSSimulation)
- `dssim/base.py` - DSComponent, StackedCond, types
- `dssim/pubsub.py` - DSProducer, DSConsumer, NotifierDict/RoundRobin/Priority
- `dssim/process.py` - DSProcess, DSSchedulable, DSSubscriberContextManager
- `dssim/components/container.py` - **DSQueue**, Container, Queue (+ mixins)
- `dssim/components/resource.py` - Resource, Mutex
- `dssim/components/state.py` - State
- `dssim/processcomponent.py` - DSProcessComponent, PCGenerator, ContainerMixin

## DSQueue (core data structure, in container.py)
- Plain Python class (no simulation awareness), deque-based
- O(1): append, appendleft, pop, popleft; O(n): pop_at, remove, remove_if
- Properties: head, tail; Methods: remove_if(cond)->bool, pop_at(index), clear()
- append() returns the item; remove() raises ValueError if not found
- Exported from `dssim.components.container` (not yet from top-level `dssim`)

## Queue Component (uses 3 DSQueues)
- `_buffer`: DSQueue holding items in transit
- `_putters` / `_getters`: DSQueues tracking blocked processes (try/finally cleanup)
- `buffer` / `putters` / `getters` properties for observability
- `get_nowait(amount, cond)`: cond checked against `_buffer.head` (FIFO semantics)
- `get`/`gget`: cond=lambda e: len>=amount and cond(head); popleft N items on wake
- Old `self.queue` list attribute gone; use `q[0]` or `q.buffer.head`
- `__contains__` implemented (delegates to `_buffer`)

## Notification mechanism
- `tx_changed` DSProducer on DSStatefulComponent — fires always; for external observers (e.g. `q.gwait(cond=...)`)
- `DSProducer.send()` stops at the first consumer whose condition passes (not a full broadcast)
- **Queue has two additional targeted producers** (Option A+B optimization):
  - `tx_item`: fires on put (only if `_getters` non-empty) → `gget`/`get` subscribe here
  - `tx_space`: fires on get/remove/pop (only if `_putters` non-empty) → `gput`/`put` subscribe here
  - Eliminates cross-notification: getters never see get-events; putters never see put-events

## Running tests
```
PYTHONPATH=. python -m pytest tests/ -q
```

## Running examples
```
PYTHONPATH=. python examples/<name>.py
```
Note: `examples/run_all.sh` doesn't export PYTHONPATH - use direct invocation.

## API patterns
- `Queue(capacity=N, name='q', sim=sim)` - create queue
- `q.put_nowait('item')` → tuple or None
- `yield from q.gget(timeout, amount, cond)` → list or None
- `yield from q.gput(timeout, *items)` → event or None
- `q[0]` - first item (NOT `q.queue[0]` - old API removed)
- `q.remove(item_or_cond)` - remove by equality or callable
- `self not in q` - membership check via `__contains__`
