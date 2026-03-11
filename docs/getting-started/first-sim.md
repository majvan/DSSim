# First Simulation

## Minimal Example

```python
from dssim import DSSimulation, LiteLayer2

sim = DSSimulation(layer2=LiteLayer2)

def worker():
    print("t=", sim.time, "start")
    yield from sim.gsleep(3)
    print("t=", sim.time, "done")

sim.schedule(0, worker())
sim.run()
```

## Next Steps

1. Add a queue with `sim.queue()`.
2. Add a resource with `sim.resource()` or `sim.priority_resource()`.
3. Move to `PubSubLayer2` when you need endpoint-based routing and conditions.
