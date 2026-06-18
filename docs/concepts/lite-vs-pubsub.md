# Lite vs PubSub

## LiteLayer2

Use Lite when you want:

- Simpler event handling
- Low overhead
- Direct queue/resource operations without pubsub wiring

## PubSubLayer2

Use PubSub when you need:

- Endpoint routing
- Conditional waits with filters/circuits
- Rich process/future integration
- Agents (`DSAgent`) with lifecycle state, container/resource helpers, and probes (PubSub-only)

## Practical Rule

- Start with Lite for basic throughput/process models.
- Move to PubSub when model logic depends on routed events and condition composition.
