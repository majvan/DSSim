# Glossary

## AlwaysFalse

A named callable condition that never matches any event. Used as a pure time-delay sentinel — the only way the wait can return is via timeout. Also the default condition for `check_and_wait()`. PubSubLayer2 only.

## AlwaysTrue

A named callable condition that matches every event. The default `cond` for all `wait()` calls — omitting `cond` is equivalent to passing `AlwaysTrue`. PubSubLayer2 only.

## Circuit

See [DSCircuit](#dscircuit).

## Condition

A criterion used to decide whether an incoming event should wake a waiting process or subscriber. Conditions are evaluated before the process is resumed, preventing spurious wakeups. Accepted types: plain value (exact match), callable (predicate), `AlwaysTrue`/`AlwaysFalse` (named sentinels), `DSFilter`, `DSCircuit`, `DSFuture`/`DSProcess` (completion), or `None` (equivalent to `AlwaysTrue`).

## Consumer

A subscriber registered in the `CONSUME` tier. The first consumer whose `send()` returns a truthy value claims the event. Subsequent consumers in the same tier are not called for that event.

## DSAgent

A `DSComponent` subclass that auto-starts its own `DSProcess` and provides ergonomic queue, container, and resource helper methods (`pop`, `get`, `put`, `enter`, etc.). The recommended way to write self-driving components. PubSubLayer2 only.

## DSCircuit

A composite condition combining multiple `DSFilter` objects with AND (`&`, all must match) or OR (`|`, any must match) logic. Supports reset semantics via negated filters (`-f`): a negated filter resets the state of positive filters when its condition matches. Used for multi-condition readiness checks. PubSubLayer2 only.

## DSComponent

The base class for all named simulation objects. Requires `name` and `sim` constructor arguments. All publishers, subscribers, processes, agents, queues, resources, and hardware components inherit from `DSComponent`.

## DSFilter

A reusable, composable condition object wrapping a predicate. Supports three signal types:

- `DEFAULT` (monostable) — once triggered, stays triggered
- `REEVALUATE` — re-evaluates on every event; signal state can toggle
- `PULSED` — triggers momentarily but never latches

Can be composed with `|` (OR) and `&` (AND) operators to create a `DSCircuit`. PubSubLayer2 only.

## DSFuture

An awaitable object representing a value that will be set in the future. Can be `await`-ed inside coroutines or used as a `cond` in `wait()` to block until the future completes. Exposes `finish(value)`, `fail(exc)`, `finished()`, `value`, and `exc`. PubSubLayer2 only.

## DSLiteCallback

A minimal callback subscriber for LiteLayer2. Wraps a callable and calls it directly on each `send(event)`. No condition filtering.

## DSLiteProcess

Lightweight process in LiteLayer2. Wraps a generator or coroutine with minimal overhead: no condition stacking, no abort, no join. Suitable for high-throughput scenarios without complex condition logic.

## DSLitePub

A minimal fan-out publisher for LiteLayer2. Delivers every event to all registered subscribers in registration order. No tiers, no condition filtering, no circuits.

## DSLiteSub

Base subscriber class for LiteLayer2. Any object with a `send(event)` method; `DSLiteCallback` is the ready-made concrete subclass.

## DSProcess

Process object wrapping a generator or coroutine in PubSubLayer2. Provides full lifecycle management (scheduled → started → finished), a condition stack, `abort()`, `join()` via `DSFuture`, and timeout handling. PubSubLayer2 only.

## DSSchedulable

Decorator that wraps a plain function or method as a generator-compatible callable. Useful when an existing function must be scheduled without rewriting it as a generator. Available in both profiles.

## DSStatefulComponent

A `DSComponent` subclass that exposes a `tx_changed` publisher. Fires `tx_changed` events whenever the component's observable state changes. `DSQueue`, `DSResource`, `DSContainer`, and `DSState` are all `DSStatefulComponent` subclasses.

## Event Object

The Python object passed through the simulation at each dispatch step. DSSim imposes no constraints on event type: it can be `None`, an integer, a string, a dict, a dataclass, or any custom class. `None` is the conventional return value when a blocking call times out.

## Filter

A condition used to decide whether an event should wake a waiter. See [Condition](#condition) for the full list of accepted types, and [DSFilter](#dsfilter) for the reusable object form.

## LiteLayer2

The lightweight simulation layer profile. Includes generator/coroutine process support, simple fan-out pub/sub (`DSLitePub`/`DSLiteSub`), and basic queue/resource primitives. No delivery tiers, no condition stacking, no `DSFilter`/`DSCircuit`.

## Notifier Policy

Determines the dispatch order of subscribers within a single tier:

- `NotifierDict` — insertion-order; deterministic, O(1) lookup. Default policy.
- `NotifierRoundRobin` — rotates the start position after each dispatch cycle; gives all subscribers equal opportunity over time. Suitable for load-balancing multiple identical consumers.
- `NotifierPriority` — visits subscribers in ascending priority-number order (lower number = higher priority); priority is specified per `add_subscriber` call.

## NowQueue

An internal deque for zero-delay events scheduled at the current simulation time. Always drained before advancing time; faster than timed events because no ordering is needed.

## Observer

A subscriber attached for monitoring side effects, typically in `PRE` or `POST_*` phases. Observers always see events and cannot affect whether an event is consumed.

## Probe

A non-intrusive observer attached to a simulation component. Probes subscribe to the component's publisher endpoints in `PRE` phase to collect metrics without affecting event delivery to consumers. Built-in probes: `QueueStatsProbe`, `ResourceStatsProbe`.

## PubSubLayer2

The full-featured simulation layer profile. Extends LiteLayer2 with routing-rich pub/sub (`DSPub`/`DSSub`, 4-phase tiers), `DSProcess` with condition stacking, `DSFuture`, `DSFilter`, `DSCircuit`, and process context managers (`interruptible`, `timeout`).

## Publisher

An output endpoint that delivers events to registered subscribers. LiteLayer2 uses `DSLitePub` (fan-out, no tiers). PubSubLayer2 uses `DSPub` (4-phase tier routing).

## Signal

Scheduling an event at the current simulation time (delay = 0). Implemented via the NowQueue. `pub.signal(event)` is equivalent to `sim.schedule_event(0, event, pub)`.

## Spurious Wakeup

A wakeup delivered to user code even though the waiting condition is not satisfied. PubSubLayer2 waits are designed to eliminate spurious wakeups: the `cond` is evaluated before the generator is resumed.

## Subscriber

Any object that can receive an event via `send(event)`. Includes callbacks, processes, agents, filters, circuits, and any custom class implementing the `ISubscriber` interface.

## Subscription Tier

One of the four publisher phases in PubSubLayer2:

- `PRE` — runs before any consumer decision; used for logging and monitoring
- `CONSUME` — first accepting consumer claims the event; subsequent consumers are skipped
- `POST_HIT` — runs after a consumer has accepted; used for follow-on reactions
- `POST_MISS` — runs when no consumer accepted; used for fallback handling

## TimeQueue

The internal priority queue that holds all timed events. Implemented as a sorted list of `(time, deque[events])` buckets. Insertion is O(log n); pop of the earliest bucket is O(1).

## Wait Timeout

Maximum time a blocking call can wait. All DSSim blocking APIs (`wait`, `gwait`, `sleep`, `gsleep`, queue `get`/`put`, resource `get`/`put`) accept an explicit `timeout` parameter. When the timeout expires, the call returns `None`.
