# Process Components Guide

`DSProcessComponent` is part of the PubSub-side runtime and is useful for component-oriented models.

## When to Use

- Modeling active entities with internal `process()` loops
- Integrating with pubsub-style event routing
- Reusing `ContainerMixin` / `ResourceMixin` helpers

## Minimal Sketch

```python
from dssim import DSProcessComponent

class Worker(DSProcessComponent):
    async def process(self):
        while True:
            await self.sim.sleep(1)
```

## Related Examples

- `examples/pubsub/agent.py`
- `examples/pubsub/gasstation.py`
