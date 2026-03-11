# Glossary

## Subscriber

Any object that can receive an event via `send(event)`.

## Publisher (`DSPub`)

A publisher endpoint that routes events to subscribers across [subscription tiers](#subscription-tier).

## Subscription Tier

One of the publisher phases:

- `PRE`
- `CONSUME`
- `POST_HIT`
- `POST_MISS`

## Observer

A subscriber attached for monitoring side effects, typically in `PRE` or `POST_*` phases.

## Consumer

A subscriber in `CONSUME` phase. First accepting consumer can consume the event.

## Filter

A condition used to decide whether an event should wake a waiter.

- simple callable/value condition
- [DSFilter](../reference/pubsub.md)
- [DSCircuit](../reference/pubsub.md)

## Spurious Wakeup

A wakeup event delivered to user code even though the waiting condition is not satisfied.

In DSSim pubsub waiting, user-facing waits are designed to avoid this.

## Wait Timeout

Maximum waiting horizon for a wait operation. DSSim wait APIs support timeout directly.

## DSProcess

Process object wrapping a generator/coroutine in PubSub layer.

## DSSchedulable

Decorator helping plain functions fit scheduling expectations.

## LiteLayer2

Lighter layer with direct queue/resource behavior and low overhead.

## PubSubLayer2

Full feature layer with endpoint routing, process/future/filter/circuit integration.
