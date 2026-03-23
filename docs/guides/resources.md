# Resources Guide

## Resource APIs

- `sim.resource(...)`
- `sim.priority_resource(...)`

These names are shared across Lite and PubSub layers; behavior depends on selected layer.

## Choose Layer

- Lite: lower overhead, minimal signaling machinery
- PubSub: full condition/pubsub ecosystem

## Typical Pattern

```python
got = yield from res.gget(timeout=10, priority=1, preempt=True)
if got:
    # do work
    res.put_nowait()
```

## Condition Helper: policy_for_get

`DSResource` and `DSPriorityResource` expose `policy_for_get()` for use with `sim.filter()`:

```python
policy = r.policy_for_get(amount=1)           # or policy_for_get(priority=1, preempt=True)
f = sim.filter(policy=policy)
result = yield from f.check_and_gwait(timeout=10)
amount = f.cond.cond_value()          # amount actually acquired
```

`policy_for_get` subscribes to `r.tx_nempty`. On each check it attempts immediate acquisition (with preemption if requested). Use it to compose multi-resource waits:

```python
# wait until both resources are acquired
f0 = sim.filter(policy=r0.policy_for_get())
f1 = sim.filter(policy=r1.policy_for_get())
result = yield from (f0 & f1).check_and_gwait(timeout=20)
```

Policy dict endpoint metadata uses:

```python
{ep: {"tier": ep.Phase.CONSUME, "params": {"priority": 1, "preempt": True}}}
```

## Example Pointers

- `examples/pubsub/priority_resource.py`
- `examples/lite/priority_resource.py`
