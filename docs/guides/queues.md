# Queues Guide

## PubSub Queue

Use `sim.queue(...)` on default `DSSimulation()` for endpoint-aware queue behavior.

Key features:

- Change/non-empty/non-full signaling endpoints
- Conditional waits via `check_and_wait` wrappers

## Lite Queue

Use `sim.queue(...)` on `DSSimulation(layer2=LiteLayer2)` for Lite queue behavior.

Key features:

- Direct wakeup path
- No pubsub endpoint routing overhead

## Example Pointers

- PubSub: `examples/pubsub/queue.py`
- Lite: `examples/lite/queue.py`
