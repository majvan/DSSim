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
| `q.policy_for_put(amount=1, cond=AlwaysTrue)` | CONSUME | `q.tx_nempty` (or `q.tx_changed` if `cond` given) | Dequeues on success |
| `q.policy_for_get(*items)` | CONSUME | `q.tx_nfull` | Enqueues on success |
| `q.policy_for_observe(cond=lambda q: True)` | PRE | `q.tx_changed` | Observes, no dequeue |

Use them directly when you want queue-native claiming semantics:

```python
# consume one matching item
getc = q.policy_for_put(cond=lambda item: item.type == "DATA")
item = yield from getc['cond'].check_and_gwait(10)

# enqueue when space opens
putc = q.policy_for_get("ack")
put_result = yield from putc['cond'].check_and_gwait(10)  # ('ack',)

# observe queue state changes without dequeuing
chg = q.policy_for_observe(cond=lambda qq: len(qq) >= 5)
event = yield from chg['cond'].check_and_gwait(20)
```

Wrap in `sim.filter()` only when you need `|` / `&` composition:

```python
# OR: wake when either queue has an item
f0 = sim.filter(policy=q0.policy_for_put())
f1 = sim.filter(policy=q1.policy_for_put())
result = yield from (f0 | f1).check_and_gwait(10)
```

In wrapped form, waiting uses the policy tier (`CONSUME` for getter/putter, `PRE` for observer). For direct condition waits use `policy['cond']`.

**Note:** `policy_for_put(cond=...)` takes an item predicate; `policy_for_observe(cond=...)` takes a queue predicate.

## Lite Queue

Use `sim.queue(...)` on `DSSimulation(layer2=LiteLayer2)` for Lite queue behavior.

Key features:

- Direct wakeup path
- No pubsub endpoint routing overhead
- No condition helpers (no pubsub endpoints)

## Example Pointers

- PubSub: `examples/pubsub/queue.py`
- Lite: `examples/lite/queue.py`
