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

## Example Pointers

- `examples/pubsub/priority_resources.py`
- `examples/lite/PriorityResource pubsub.py`
