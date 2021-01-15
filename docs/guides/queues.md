# Queues Guide

## PubSub Queue

Use `sim.queue(...)` on default `DSSimulation()` for endpoint-aware queue behavior.

Key features:

- Change/non-empty/non-full signaling endpoints
- Conditional waits via `check_and_wait` wrappers

## Condition Helpers

`DSQueue` exposes three condition helper factories:

| Factory | Default wait tier | Subscribes to | Effect |
|---|---|---|---|
| `q.get_cond(amount=1, cond=AlwaysTrue)` | CONSUME | `q.tx_nempty` (or `q.tx_changed` if `cond` given) | Dequeues on success |
| `q.put_cond(*items)` | CONSUME | `q.tx_nfull` | Enqueues on success |
| `q.change_cond(cond=lambda q: True)` | PRE | `q.tx_changed` | Observes, no dequeue |

Use them directly when you want queue-native claiming semantics:

```python
# consume one matching item
getc = q.get_cond(cond=lambda item: item.type == "DATA")
item = yield from getc.check_and_gwait(10)

# enqueue when space opens
putc = q.put_cond("ack")
put_result = yield from putc.check_and_gwait(10)  # ('ack',)

# observe queue state changes without dequeuing
chg = q.change_cond(cond=lambda qq: len(qq) >= 5)
event = yield from chg.check_and_gwait(20)
```

Wrap in `sim.filter()` only when you need `|` / `&` composition:

```python
# OR: wake when either queue has an item
f0 = sim.filter(q0.get_cond())
f1 = sim.filter(q1.get_cond())
result = yield from (f0 | f1).check_and_gwait(10)
```

In this wrapped form, waiting is PRE-tier (observation-style). For strict queue-claiming behavior, use direct `q.get_cond(...).check_and_gwait(...)` / `q.put_cond(...).check_and_gwait(...)`.

**Note:** `get_cond(cond=...)` takes an item predicate; `change_cond(cond=...)` takes a queue predicate.

## Lite Queue

Use `sim.queue(...)` on `DSSimulation(layer2=LiteLayer2)` for Lite queue behavior.

Key features:

- Direct wakeup path
- No pubsub endpoint routing overhead
- No condition helpers (no pubsub endpoints)

## Example Pointers

- PubSub: `examples/pubsub/queue.py`
- Lite: `examples/lite/queue.py`
