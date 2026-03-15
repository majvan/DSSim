# PubSub -> Lite Porting Status

This folder now contains executable Lite ports for pubsub examples that map to Lite primitives:

- `Bank, 1 clerk.py`
- `Bank, 3 clerks.py`
- `Bank, 3 clerks (resources).py`
- `Bank, 3 clerks (with ComponentGenerator).py`
- `Bank, 3 clerks reneging (resources).py`
- `gasstation.py`
- `agent.py` (simplified)
- `school.py` (explicit bell routing)
- `visa_check.py`
- `priority_resources_combined.py` (with Lite filter/event composition)
- already present: `queue.py`, `trajectory.py`, `process_events.py`, `coro_schedule.py`

## Not directly portable yet

Examples using pubsub-only features remain unported or would need a semantic rewrite:

- `consume/observe/check_and_wait` filtering flows
- `DSFilter`/condition circuits
- `State`-driven waits
- publisher/subscriber notifiers and priority notifier policy
- queue/store APIs requiring conditional wait or remove-from-middle behavior

Representative files:

- `Demo wait*.py`
- `conditions*.py`
- `consumer_ordering.py`
- `interruptible_context.py`
- `process_retval.py`
- `uart_*.py`
