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

## Condition Helper: get_cond

`DSResource` and `DSPriorityResource` expose `get_cond()` for use with `sim.filter()`:

```python
cond = r.get_cond(amount=1)           # or get_cond(priority=1, preempt=True)
f = sim.filter(cond)
result = yield from f.check_and_gwait(timeout=10)
amount = f.cond.cond_value()          # amount actually acquired
```

`get_cond` subscribes to `r.tx_nempty`. On each check it attempts immediate acquisition (with preemption if requested). Use it to compose multi-resource waits:

```python
# wait until both resources are acquired
f0 = sim.filter(r0.get_cond())
f1 = sim.filter(r1.get_cond())
result = yield from (f0 & f1).check_and_gwait(timeout=20)
```

## Example Pointers

- `examples/pubsub/priority_resource.py`
- `examples/lite/priority_resource.py`
