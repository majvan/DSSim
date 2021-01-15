# Architecture

DSSim is organized around a core simulation runtime and layer-specific features.

```mermaid
flowchart TD
  A[dssim core\nbase.py, base_components.py,\nsimulation.py, timequeue.py]
  B[dssim/pubsub\nprocess, future, cond,\npubsub + pubsub components]
  C[dssim/lite\nlite queue/resource components]
  A --> B
  A --> C
```

## Core Runtime

- Event queue and dispatch
- Time progression
- Minimal scheduling and waiting primitives

## PubSub Layer

- Endpoint-based signaling
- Condition-aware waits
- DSProcess / DSFuture / DSFilter / DSCircuit
- Full pubsub components

## Lite Layer

- Lightweight waiting/scheduling usage
- Lite queue and resource components
- Lower-overhead path for simpler models
