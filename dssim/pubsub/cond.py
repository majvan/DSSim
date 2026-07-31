# Copyright 2021- majvan (majvan@gmail.com)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
'''
This file implements advanced logic - with overloading operators
to be able create advanced expressions for conditions.
'''
from typing import List, Set, Any, Dict, Tuple, Union, Optional, Callable, Iterable, Generator, Mapping, TYPE_CHECKING
from types import MappingProxyType
import inspect
from enum import Enum
from dssim.base import TimeType, EventType, EventRetType
from dssim.pubsub.base import CondType, ICondition, CallableConditionMixin, SubscriberMetadata, TestObject, AlwaysTrue, ITwoPhaseCondition
from dssim.pubsub.future import DSFuture
from dssim.pubsub.pubsub import TrackEvent


if TYPE_CHECKING:
    from dssim.pubsub.pubsub import DSPub
    from dssim.simulation import DSSimulation


FilterExpression = Callable[[Iterable[object]], bool]
SignalType = Union["DSFilter", "DSCircuit"]
SignalList = List[SignalType]
EPSpecType = Dict[str, Any]
EPMapType = Dict["DSPub", EPSpecType]


class _ConditionProxy(ICondition, CallableConditionMixin):
    """Adapter that preserves ICondition semantics but avoids DSFuture shortcuts."""

    __slots__ = ('_cond',)

    def __init__(self, cond: ICondition) -> None:
        self._cond = cond

    def check(self, event: EventType) -> Tuple[bool, EventType]:
        return self._cond.check(event)

    def cond_value(self) -> EventType:
        getter = getattr(self._cond, 'cond_value', None)
        if callable(getter):
            return getter()
        return None


class _FilterWaitMixin:
    def _should_auto_detach_on_precheck_hit(self) -> bool:
        """Allow subclasses to keep send()/wait() detach semantics consistent."""
        return True

    def _detach_on_precheck_hit(self) -> None:
        if not self.one_shot or not self.is_attached():
            return
        if not self._should_auto_detach_on_precheck_hit():
            return
        self.detach()

    def attach(self) -> Any:
        raise NotImplementedError

    def is_attached(self) -> bool:
        raise NotImplementedError

    def gwait(self, timeout: TimeType = float('inf'), val: EventRetType = True) -> Generator[EventType, EventType, EventType]:
        # Self-contained gated wait: subscribe to condition endpoints while blocked.
        if not self.is_attached():
            self.attach()
        cond = _ConditionProxy(self)
        with self.sim.observe_pre(self):
            retval = yield from self.sim.gwait(timeout=timeout, cond=cond, val=val)
        return retval

    async def wait(self, timeout: TimeType = float('inf'), val: EventRetType = True) -> EventType:
        # Self-contained gated wait: subscribe to condition endpoints while blocked.
        if not self.is_attached():
            self.attach()
        cond = _ConditionProxy(self)
        with self.sim.observe_pre(self):
            return await self.sim.wait(timeout=timeout, cond=cond, val=val)

    def check_and_gwait(self, timeout: TimeType = float('inf'), val: EventRetType = True) -> Generator[EventType, EventType, EventType]:
        # Pre-check first (without endpoint registration). Register producers only
        # when we actually need to block.
        if not self.is_attached():
            self.attach()
        signaled, event = self.check(TestObject)
        if signaled:
            self._detach_on_precheck_hit()
            return event
        cond = _ConditionProxy(self)
        with self.sim.observe_pre(self):
            retval = yield from self.sim.gwait(timeout=timeout, cond=cond, val=val)
        return retval

    async def check_and_wait(self, timeout: TimeType = float('inf'), val: EventRetType = True) -> EventType:
        # Pre-check first (without endpoint registration). Register producers only
        # when we actually need to block.
        if not self.is_attached():
            self.attach()
        signaled, event = self.check(TestObject)
        if signaled:
            self._detach_on_precheck_hit()
            return event
        cond = _ConditionProxy(self)
        with self.sim.observe_pre(self):
            return await self.sim.wait(timeout=timeout, cond=cond, val=val)


class DSFilter(_FilterWaitMixin, DSFuture, ICondition, CallableConditionMixin):
    '''Endpoint-driven filter (router) used as a leaf in circuit trees.'''

    class SignalType(Enum):
        LATCH = 0
        REEVALUATE = 1
        PULSED = 2

    ONE_LINER = None

    def __init__(
        self,
        cond: CondType = AlwaysTrue,
        sigtype: SignalType = SignalType.LATCH,
        signal_timeout: bool = False,
        eps: Union[Iterable["DSPub"], Mapping["DSPub", Any]] = (),
        signal_to_endpoint: bool = True,
        one_shot: bool = True,
        policy: Optional[Mapping[str, Any]] = None,
        *args: Any,
        **kwargs: Any,
    ):
        """Create an endpoint-driven filter.

        The filter subscribes to source endpoints and maintains local signal state
        according to selected signal type (LATCH/REEVALUATE/PULSED).
        """
        resolved_cond = cond
        resolved_sigtype = sigtype
        resolved_signal_timeout = signal_timeout
        resolved_eps = eps
        resolved_signal_to_endpoint = signal_to_endpoint
        resolved_one_shot = one_shot
        resolved_policy = policy

        if resolved_policy is None and isinstance(cond, Mapping):
            policy_keys = ('cond', 'sigtype', 'signal_timeout', 'eps', 'signal_to_endpoint', 'one_shot')
            if any((k in cond) for k in policy_keys):
                resolved_policy = cond
                resolved_cond = AlwaysTrue

        if resolved_policy is not None:
            resolved_cond = resolved_policy.get('cond', resolved_cond)
            resolved_sigtype = resolved_policy.get('sigtype', resolved_sigtype)
            resolved_signal_timeout = resolved_policy.get('signal_timeout', resolved_signal_timeout)
            resolved_eps = resolved_policy.get('eps', resolved_eps)
            resolved_signal_to_endpoint = resolved_policy.get('signal_to_endpoint', resolved_signal_to_endpoint)
            resolved_one_shot = resolved_policy.get('one_shot', resolved_one_shot)

        super().__init__(*args, **kwargs)
        self.expression: Optional[FilterExpression] = self.ONE_LINER
        self.signals: SignalList = [self]
        self.positive = True
        self.signaled = False
        self.value: EventType = None
        self.cond = resolved_cond
        self.signal_timeout = resolved_signal_timeout
        self.signal_to_endpoint = resolved_signal_to_endpoint
        self.one_shot = resolved_one_shot
        self.pulse = resolved_sigtype in (self.SignalType.PULSED,)
        self.reevaluate = resolved_sigtype in (self.SignalType.REEVALUATE, self.SignalType.PULSED)
        self.forward_events = False  # intentionally unsupported in the new endpoint-driven design
        self._is_attached = False
        self._base_eps: Mapping["DSPub", EPSpecType] = MappingProxyType({})
        self._eps: EPMapType = {}
        self._listeners: Set["DSCircuit"] = set()
        self._pulse_token = -1
        self._pulse_value: EventType = None

        if inspect.isgenerator(self.cond) or inspect.iscoroutine(self.cond):
            # Wrapping is still supported for convenience, but no event forwarding is performed.
            self.cond = self.sim.process(self.cond).schedule(0)
        self._refresh_cond_traits()
        source_eps = self._normalize_base_eps(resolved_eps)
        if len(source_eps) == 0:
            get_eps = getattr(self.cond, 'get_eps', None)
            if callable(get_eps):
                source_eps = {ep: {'tier': ep.Phase.PRE, 'params': {}} for ep in get_eps()}
        self._base_eps = MappingProxyType(source_eps)

    def _normalize_base_eps(self, eps: Union[Iterable["DSPub"], Mapping["DSPub", Any]]) -> EPMapType:
        if isinstance(eps, Mapping):
            normalized: EPMapType = {}
            for ep, cfg in eps.items():
                if not isinstance(cfg, Mapping):
                    raise TypeError('Filter eps mapping values must be dicts with keys "tier" and optional "params".')
                if 'tier' not in cfg:
                    raise ValueError('Filter eps mapping entry is missing required key "tier".')
                tier = cfg['tier']
                params = dict(cfg.get('params', {}))
                normalized[ep] = {'tier': tier, 'params': params}
            return normalized
        return {ep: {'tier': ep.Phase.PRE, 'params': {}} for ep in eps}

    def _refresh_cond_traits(self) -> None:
        """Cache condition traits used in the hot check()/_match_event() path."""
        self._cond_is_future = isinstance(self.cond, DSFuture)
        self._cond_is_icond = isinstance(self.cond, ICondition)
        self._cond_is_callable = callable(self.cond)
        # Same attribute name as DSCircuit._two_phase, so circuit classification
        # and probes read one member uniformly instead of calling a method.
        self._two_phase = isinstance(self.cond, ITwoPhaseCondition)

    def create_metadata(self, **kwargs: Any) -> SubscriberMetadata:
        """Accept all incoming events; filtering is handled by check()."""
        self.meta = SubscriberMetadata()
        self.meta.cond.push(lambda _e: True)
        return self.meta

    def register_listener(self, circuit: "DSCircuit") -> None:
        """Register a parent circuit that should be notified on signal changes."""
        self._listeners.add(circuit)

    def unregister_listener(self, circuit: "DSCircuit") -> None:
        """Remove a previously registered parent circuit listener."""
        self._listeners.discard(circuit)

    def set_one_shot(self, one_shot: bool = True) -> "DSFilter":
        """Fluent builder setter for one-shot behavior."""
        self.one_shot = one_shot
        return self

    def _should_auto_detach_on_precheck_hit(self) -> bool:
        """Mirror send()/finish() semantics: keep attached while parent circuits listen."""
        return not self._listeners

    def attach(self) -> "DSFilter":
        """Reconnect endpoint subscriptions remembered in _base_eps."""
        self._attach_recursive(set())
        return self

    def is_attached(self) -> bool:
        """Return whether this filter is currently connected to endpoints."""
        return self._is_attached

    def _attach_recursive(self, visited: Set[int]) -> None:
        """Internal recursive attach helper with cycle guard."""
        obj_id = id(self)
        if obj_id in visited:
            return
        visited.add(obj_id)
        self._is_attached = True
        for ep, cfg in tuple(self._base_eps.items()):
            if ep in self._eps:
                continue
            tier = cfg['tier']
            params = dict(cfg.get('params', {}))
            self._eps[ep] = {'tier': tier, 'params': params}
            ep.add_subscriber(self, tier, **params)

    def detach(self) -> None:
        """Disconnect endpoint subscriptions and listener links."""
        self._detach_recursive(set())

    def _detach_recursive(self, visited: Set[int]) -> None:
        """Internal recursive detach helper with cycle guard."""
        obj_id = id(self)
        if obj_id in visited:
            return
        visited.add(obj_id)
        self._is_attached = False
        for circuit in tuple(self._listeners):
            self.unregister_listener(circuit)
        for ep, cfg in tuple(self._eps.items()):
            ep.remove_subscriber(self, cfg['tier'], **cfg.get('params', {}))
        self._eps.clear()

    def _match_event(self, event: EventType) -> Tuple[bool, EventType]:
        """Evaluate condition against event and normalize matched value payload."""
        if self._cond_is_future:
            if not self.cond.finished():
                return False, None
            if self.cond.exc is not None:
                return False, None
            if self.cond.value is None and self.signal_timeout:
                return True, None
            if self.pulse:
                return event == self.cond, event
            return True, self.cond.value
        if self.cond == event:
            return True, event
        if self._cond_is_icond:
            signaled, value = self.cond.check(event)
            if not signaled:
                return False, None
            cond_value = getattr(self.cond, 'cond_value', None)
            if callable(cond_value):
                return True, cond_value()
            return True, value
        if self._cond_is_callable and self.cond(event):
            return True, event
        return False, None

    def _update_state(self, matched: bool, value: EventType, token: int) -> Tuple[bool, EventType]:
        """Update latched/pulsed state and return normalized signal tuple."""
        if self.pulse:
            if matched:
                self.value = value
                self._pulse_token = token
                self._pulse_value = value
                return True, value
            return False, None

        if self.signaled and not self.reevaluate:
            return True, self.value

        self.signaled = matched
        if matched:
            self.value = value
            return True, self.value
        return False, None

    def _emit_match(self, value: EventType) -> None:
        """Publish a matched hit to own finish endpoint.

        Caller is responsible for deciding whether the current event should emit.
        """
        if self.signal_to_endpoint:
            wakeup = value if self.pulse else TestObject
            self._finish_tx.signal(wakeup)

    @TrackEvent
    def send(self, event: EventType) -> bool:
        """Receive endpoint event, update state, emit wakeup, notify parent circuits."""
        token = self.sim.num_events
        if self._two_phase and self._listeners:
            # Two-phase leaf inside a circuit never commits autonomously: the
            # endpoint event triggers an immediate root evaluation, which guards
            # all branches and commits exactly the selected ones. When some root
            # fires, this leaf consumed the endpoint event (preserving CONSUME
            # tier priority over subscribers behind it); otherwise the event
            # stays unconsumed for other subscribers.
            return self._try_root_fire(token)
        was_signaled = self.signaled
        signaled, value = self.check(event, token=token)
        if signaled and (self.pulse or self.reevaluate or not was_signaled):
            self._emit_match(value)
        if self._listeners:
            for circuit in tuple(self._listeners):
                circuit.notify(self, token=token, signaled=signaled, value=value, event=event)
        # When a filter is part of a circuit (has parent circuit listeners), one_shot auto-detach
        # cannot be run when the parent circuit's AND hadn't been satisfied yet.
        # This prevents PULSED filters to permanently disconnect after their first pulse
        # never receiving subsequent pulses needed for the circuit to fire.
        if signaled and self.one_shot and self._is_attached and not self._listeners:
            self.detach()
        return signaled

    def __or__(self, other: "DSFilter") -> "DSCircuit":
        """Build OR circuit with another filter/circuit leaf."""
        return DSCircuit.build(self, other, any)

    def __and__(self, other: "DSFilter") -> "DSCircuit":
        """Build AND circuit with another filter/circuit leaf."""
        return DSCircuit.build(self, other, all)

    def __neg__(self) -> "DSFilter":
        if not self.positive:
            raise ValueError('You can negate a DSFilter only once')
        f = DSFilter(
            cond=self.cond,
            sigtype=self.SignalType.PULSED,
            signal_timeout=self.signal_timeout,
            eps=self._base_eps,
            signal_to_endpoint=self.signal_to_endpoint,
            one_shot=self.one_shot,
            sim=self.sim,
        )
        f.positive = False
        return f

    def __str__(self) -> str:
        retval = f'DSFilter({self.cond})'
        if not self.positive:
            retval = '-' + retval
        return retval

    def finished(self) -> bool:
        """Return current persistent signaled state."""
        return self.signaled

    def check(self, event: EventType, token: Optional[int] = None) -> Tuple[bool, EventType]:
        """Evaluate this filter for event (or probe with TestObject)."""
        if self.signaled and not self.reevaluate:
            return True, self.value
        if event is TestObject:
            if self.pulse:
                return False, None
            if self.signaled:
                return True, self.value
            if token is None:
                token = self.sim.num_events
            matched, value = self._match_event(event)
            return self._update_state(matched, value, token)
        if token is None:
            token = self.sim.num_events
        matched, value = self._match_event(event)
        return self._update_state(matched, value, token)

    def get_eps(self) -> Set["DSPub"]:
        """Expose wait endpoint used by observe_pre/wait infrastructure."""
        return {self._finish_tx}

    def reset(self) -> None:
        """Reset signal state and re-attach subscriptions if they were detached."""
        self.attach()
        self.signaled = False
        self.value = None
        self._pulse_token = -1
        self._pulse_value = None

    def finish(self, value: EventType) -> EventType:
        """Externally force signal state and notify endpoint/listeners."""
        token = self.sim.num_events
        self.exc = None
        self.value = value
        if self.pulse:
            self.signaled = False
            self._pulse_token = token
            self._pulse_value = value
            wakeup = value
        else:
            self.signaled = True
            wakeup = TestObject
        if self.signal_to_endpoint:
            self._finish_tx.signal(wakeup)
        for circuit in tuple(self._listeners):
            circuit.notify(self, token=token, signaled=True, value=value, event=value)
        if self.one_shot and self._is_attached and not self._listeners:
            self.detach()
        return value

    def cond_value(self) -> EventType:
        """Return last matched (or externally finished) value."""
        return self.value

    def _commit_two_phase(self) -> EventType:
        """Commit this leaf's outstanding guard claim and latch the result."""
        value = self.cond.commit_reserved()
        self.signaled = True
        self.value = value
        self._emit_match(value)
        return value

    def _try_root_fire(self, token: int) -> bool:
        """Ask the root circuit(s) above this leaf to evaluate right now.

        Returns True when some root fired - i.e. this leaf's endpoint event led
        to committed work and counts as consumed.
        """
        listeners = self._listeners
        if len(listeners) == 1:
            # Overwhelmingly common topology (leaf directly under its root):
            # skip the graph walk and its set/list allocations.
            (only,) = listeners
            if not only._listeners:
                if only._flat_two_phase_or:
                    # Router topology: only this leaf's eligibility can have
                    # changed - evaluate just this branch (see the method doc).
                    return only._publish_single_branch(self, token)
                return only._publish_evaluation(token)
        roots: Set["DSCircuit"] = set()
        stack: List["DSCircuit"] = list(listeners)
        while stack:
            circuit = stack.pop()
            if circuit._listeners:
                stack.extend(circuit._listeners)
            else:
                roots.add(circuit)
        fired = False
        for root in roots:
            fired = root._publish_evaluation(token) or fired
        return fired


class _TwoPhasePlan:
    '''Selection plan built by the pure pass of a two-phase circuit evaluation.

    entries hold, in guard order, either already-latched child values or pending
    guard claims; spans record which entry range belongs to which (sub)circuit so
    that nested payloads and OR round-robin cursors can be settled at commit time.
    Rollbacks are strictly LIFO (a failed subtree releases its suffix of entries
    before any further guards run), which keeps queue get-claims contiguous
    from the buffer head.

    A claim carries no object of its own (see ITwoPhaseCondition): a pending
    entry just marks that its leaf's condition owes one commit_reserved() or
    release_reserved() call. One plan instance is owned per circuit and reused
    across evaluations (clear() per pass) - safe because commits publish only
    via sim.signal (appended to the now-queue), so an evaluation pass can never
    synchronously re-enter another one.
    '''
    __slots__ = ('entries', 'spans')

    def __init__(self) -> None:
        self.entries: List[list] = []   # [signal, value, pending-claim-flag]
        self.spans: List[list] = []     # [circuit, entry_start, entry_end, winner-or-None]

    def clear(self) -> None:
        self.entries.clear()
        self.spans.clear()

    def mark(self) -> Tuple[int, int]:
        return (len(self.entries), len(self.spans))

    def rollback_to(self, mark: Tuple[int, int]) -> None:
        entries_len, spans_len = mark
        for entry in self.entries[entries_len:]:
            if entry[2]:
                entry[0].cond.release_reserved()
        del self.entries[entries_len:]
        del self.spans[spans_len:]

    def release_all(self) -> None:
        self.rollback_to((0, 0))

    def add_latched(self, signal: SignalType, value: EventType) -> None:
        self.entries.append([signal, value, False])

    def add_pending(self, signal: "DSFilter") -> None:
        self.entries.append([signal, None, True])

    def close_circuit(self, circuit: "DSCircuit", mark: Tuple[int, int], winner: Optional[int] = None) -> None:
        self.spans.append([circuit, mark[0], len(self.entries), winner])

    def commit(self) -> Dict[SignalType, EventType]:
        # Commit claims in guard order (see class docstring), then settle
        # the (sub)circuit latches from the innermost span outwards - spans are
        # appended post-order, so children come first.
        for entry in self.entries:
            if entry[2]:
                entry[1] = entry[0]._commit_two_phase()
                entry[2] = False
        for circuit, start, end, winner in self.spans:
            circuit.signaled = True
            circuit.value = self._payload(start, end)
            if winner is not None and circuit.selector == 'round_robin':
                circuit._sel_cursor = (winner + 1) % len(circuit.setters)
        return self._payload(0, len(self.entries))

    def _payload(self, start: int, end: int) -> Dict[SignalType, EventType]:
        payload: Dict[SignalType, EventType] = {}
        for signal, value, _ in self.entries[start:end]:
            if isinstance(signal, DSCircuit) and isinstance(value, dict):
                payload.update(value)
            else:
                payload[signal] = value
        return payload


class DSCircuit(_FilterWaitMixin, DSFuture, ICondition, CallableConditionMixin):
    '''Logical circuit composed from filters and nested circuits.'''

    SignalType = DSFilter.SignalType
    _NOTIFY = object()

    def __init__(
        self,
        expression: FilterExpression,
        signals: SignalList,
        sigtype: SignalType = SignalType.REEVALUATE,
        signal_to_endpoint: bool = True,
        one_shot: bool = True,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Create logical circuit from filters/circuits and expression (all/any)."""
        if len(signals) == 0:
            raise ValueError('DSCircuit requires at least one signal.')
        sim = kwargs.pop('sim', signals[0].sim)
        super().__init__(*args, sim=sim, **kwargs)
        self.expression = expression
        self.signals = list(signals)
        self.positive = True
        self.signaled = False
        self.value: EventType = None
        if sigtype == self.SignalType.PULSED:
            raise ValueError('DSCircuit does not support SignalType.PULSED.')
        self.reevaluate = sigtype == self.SignalType.REEVALUATE
        self.signal_to_endpoint = signal_to_endpoint
        self.one_shot = one_shot
        self.sim = sim
        self._is_attached = False
        self.selector = 'ordered'
        self._sel_cursor = 0
        self._plan = _TwoPhasePlan()
        self.set_signals()
        self._listeners: Set["DSCircuit"] = set()
        self._pending = False
        self._pending_token = -1

    @staticmethod
    def build(first: SignalType, second: SignalType, expr: FilterExpression) -> "DSCircuit":
        """Build/merge flattened circuits when expression/sign polarity allows it."""
        if (first.expression == expr) and (second.expression == expr):
            return DSCircuit(expr, first.signals + second.signals)
        if (second.expression == expr) and (first.expression == DSFilter.ONE_LINER):
            first, second = second, first
        if (first.expression == expr) and (second.expression == DSFilter.ONE_LINER):
            if first.positive == second.positive:
                assert type(first) == DSCircuit
                first.signals.append(second)
                first.set_signals()
                return first
            if not second.positive:
                assert type(first) == DSCircuit
                first.signals.append(second)
                first.set_signals()
                return first
        return DSCircuit(expr, [first, second])

    def register_listener(self, circuit: "DSCircuit") -> None:
        """Register parent circuit to receive deferred notify events."""
        self._listeners.add(circuit)

    def unregister_listener(self, circuit: "DSCircuit") -> None:
        """Unregister parent circuit listener."""
        self._listeners.discard(circuit)

    def set_one_shot(self, one_shot: bool = True, recursive: bool = True) -> "DSCircuit":
        """Fluent builder setter for one-shot behavior.

        By default, this propagates to all child filters/circuits in the tree.
        Keeping this only on the parent circuit is usually incorrect: child
        filters remain one-shot by default, so they can detach after first hit
        and stop feeding the parent even when the parent itself is configured
        as non-one-shot.
        """
        self.one_shot = one_shot
        if recursive:
            for s in self.signals:
                if isinstance(s, (DSFilter, DSCircuit)):
                    s.set_one_shot(one_shot)
        return self

    def set_selector(self, selector: str) -> "DSCircuit":
        """Fluent setter for OR-branch arbitration order in two-phase evaluation.

        'ordered' (default) tries setters left-to-right - an overflow chain.
        'round_robin' starts after the branch that fired last, giving fair
        distribution across branches. The cursor advances only when this
        circuit actually fires.
        """
        if selector not in ('ordered', 'round_robin'):
            raise ValueError("selector must be 'ordered' or 'round_robin'.")
        self.selector = selector
        return self

    def _should_auto_detach_on_precheck_hit(self) -> bool:
        """Mirror send()/flush() semantics: one-shot circuit detaches on first hit."""
        return True

    def attach(self) -> "DSCircuit":
        """Reconnect nested filter subscriptions and listener graph."""
        self._attach_recursive(set())
        return self

    def is_attached(self) -> bool:
        """Return whether this circuit listener graph is currently active."""
        return self._is_attached

    def _attach_recursive(self, visited: Set[int]) -> None:
        """Internal recursive attach helper with cycle guard."""
        obj_id = id(self)
        if obj_id in visited:
            return
        visited.add(obj_id)
        self._is_attached = True
        for s in self.signals:
            attach_recursive = getattr(s, '_attach_recursive', None)
            if callable(attach_recursive):
                attach_recursive(visited)
            else:
                attach_signal = getattr(s, 'attach', None)
                if callable(attach_signal):
                    attach_signal()
        self._attach_signals()

    def detach(self) -> None:
        """Recursively disconnect nested subscriptions and listener links."""
        self._detach_recursive(set())

    def _detach_recursive(self, visited: Set[int]) -> None:
        """Internal recursive detach helper with cycle guard."""
        obj_id = id(self)
        if obj_id in visited:
            return
        visited.add(obj_id)
        self._is_attached = False
        for s in self.signals:
            unregister = getattr(s, 'unregister_listener', None)
            if callable(unregister):
                unregister(self)
        for circuit in tuple(self._listeners):
            self.unregister_listener(circuit)
        for s in self.signals:
            detach_recursive = getattr(s, '_detach_recursive', None)
            if callable(detach_recursive):
                detach_recursive(visited)
        self._pending = False
        self._pending_token = -1

    def notify(
        self,
        source: SignalType,
        token: int,
        signaled: bool,
        value: EventType,
        event: EventType,
    ) -> None:
        """Queue deferred circuit re-evaluation for this simulation event token."""
        _ = (source, signaled, value, event)
        if token > self._pending_token:
            self._pending_token = token
        if not self._pending:
            self._pending = True
            self.sim.signal(self._NOTIFY, self)

    def _attach_signals(self) -> None:
        """Attach this circuit as listener to all direct child signals."""
        if not self._is_attached:
            return
        for s in self.signals:
            register = getattr(s, 'register_listener', None)
            if callable(register):
                register(self)

    # Child classification tags, computed once per structure change so the
    # per-evaluation dispatch needs no isinstance/duck checks.
    _KIND_PURE = 0
    _KIND_TWO_PHASE_LEAF = 1
    _KIND_TWO_PHASE_CIRCUIT = 2

    @staticmethod
    def _signal_has_two_phase(signal: SignalType) -> bool:
        """Duck probe for arbitrary signal types during one-time classification.

        DSFilter and DSCircuit both expose the ``_two_phase`` member; anything
        else (futures, processes) defaults to pure.
        """
        return getattr(signal, '_two_phase', False)

    def set_signals(self) -> None:
        """Split children into setters and resetters, classify them and wire listeners.

        Circuit structure only changes through this method (construction and
        build()-merging), so everything derived from structure is hoisted here:
        the per-setter kind tags, the subtree two-phase flag and the resetter
        validation that previously ran on every evaluation pass.
        """
        self.setters, self.resetters = [], []
        for s in self.signals:
            if s.positive:
                self.setters.append(s)
            else:
                self.resetters.append(s)
        for resetter in self.resetters:
            if self._signal_has_two_phase(resetter):
                raise ValueError('Two-phase conditions cannot be used as circuit resetters.')
        self._setter_kinds = []
        two_phase = False
        for s in self.setters:
            if isinstance(s, DSFilter) and s._two_phase:
                kind = self._KIND_TWO_PHASE_LEAF
            elif isinstance(s, DSCircuit) and s._two_phase:
                kind = self._KIND_TWO_PHASE_CIRCUIT
            else:
                kind = self._KIND_PURE
                # Defensive: an unknown signal type claiming two-phase still
                # marks the subtree.
                two_phase = two_phase or self._signal_has_two_phase(s)
            two_phase = two_phase or kind != self._KIND_PURE
            self._setter_kinds.append(kind)
        self._two_phase = two_phase
        # Fast-path eligibility (see _evaluate_flat_or): a flat OR of two-phase
        # leaves - exactly the router topology - needs no selection plan at all.
        self._flat_two_phase_or = (
            self.expression == any
            and not self.resetters
            and len(self.setters) > 0
            and all(kind == self._KIND_TWO_PHASE_LEAF for kind in self._setter_kinds)
        )
        # Identity map used by the single-branch wakeup to advance the
        # round-robin cursor without scanning setters.
        self._setter_index = {id(s): i for i, s in enumerate(self.setters)}
        self._attach_signals()

    def _reset_signal(self, signal: SignalType) -> None:
        """Reset one child signal via reset() if available, else by attributes."""
        reset = getattr(signal, 'reset', None)
        if callable(reset):
            reset()
            return
        if hasattr(signal, 'signaled'):
            signal.signaled = False
        if hasattr(signal, 'value'):
            signal.value = None

    def reset(self) -> None:
        """Reset this circuit and all setter children; re-attach subscriptions."""
        self.attach()
        self.signaled = False
        self.value = None
        for el in self.setters:
            self._reset_signal(el)

    def __or__(self, other: "DSCircuit") -> "DSCircuit":
        """Build OR circuit with another circuit/filter."""
        return DSCircuit.build(self, other, any)

    def __and__(self, other: "DSCircuit") -> "DSCircuit":
        """Build AND circuit with another circuit/filter."""
        return DSCircuit.build(self, other, all)

    def __neg__(self) -> "DSCircuit":
        self.positive = False
        return self

    def cond_value(self) -> Dict[Union[DSFilter, "DSCircuit"], EventType]:
        """Return current aggregated payload map for signaled branch."""
        if isinstance(self.value, dict):
            return self.value
        return {}

    def __str__(self) -> str:
        expression = ' | ' if self.expression == any else ' & '
        strings = [str(v) for v in self.setters + self.resetters]
        retval = expression.join(strings)
        sign = '' if self.positive else '-'
        return f'{sign}({retval})'

    def finished(self) -> bool:
        """Return current circuit signaled state."""
        return self.signaled

    def _state_for(self, signal: SignalType, token: Optional[int], drive_event: Optional[EventType]) -> Tuple[bool, EventType]:
        """Read child state for direct drive evaluation or deferred token-based flush."""
        if drive_event is not None:
            if isinstance(signal, ICondition):
                return signal.check(drive_event)
            signaled = signal.finished()
            if not signaled:
                return False, None
            if hasattr(signal, 'cond_value'):
                return True, signal.cond_value()
            return True, signal.value

        if isinstance(signal, DSFilter) and signal.pulse:
            active = token is not None and signal._pulse_token == token
            if active:
                return True, signal._pulse_value
            return False, None

        signaled = signal.finished()
        if not signaled:
            return False, None
        if hasattr(signal, 'cond_value'):
            return True, signal.cond_value()
        return True, signal.value

    @staticmethod
    def _payload_from_states(states: List[Tuple[SignalType, bool, EventType]]) -> Dict[Union[DSFilter, "DSCircuit"], EventType]:
        """Flatten child states into payload map of signal->value."""
        payload: Dict[Union[DSFilter, "DSCircuit"], EventType] = {}
        for signal, signaled, value in states:
            if not signaled:
                continue
            if isinstance(signal, DSCircuit) and isinstance(value, dict):
                payload.update(value)
            else:
                payload[signal] = value
        return payload

    def _evaluate(self, token: Optional[int], drive_event: Optional[EventType]) -> Tuple[bool, Optional[Dict[Union[DSFilter, "DSCircuit"], EventType]]]:
        """Evaluate full circuit logic, including resetter handling and payload build."""
        if self.signaled and not self.reevaluate:
            return True, self.cond_value()
        if self._two_phase:
            return self._evaluate_two_phase(token, drive_event)
        setter_states = [(*((s,) + self._state_for(s, token, drive_event)),) for s in self.setters]
        resetter_states = [(*((s,) + self._state_for(s, token, drive_event)),) for s in self.resetters]
        setter_flags = [state[1] for state in setter_states]
        resetter_flags = [state[1] for state in resetter_states]

        if not self.positive:
            signaled = len(setter_flags) > 0 and self.expression(setter_flags)
            if signaled:
                for el in self.setters:
                    self._reset_signal(el)
                payload = self._payload_from_states(setter_states)
                self.value = payload
                self.signaled = False
                return True, payload
            self.value = None
            self.signaled = False
            return False, None

        reset_signal = len(resetter_flags) > 0 and self.expression(resetter_flags)
        if reset_signal:
            for el in self.setters:
                self._reset_signal(el)
            self.signaled = False
            self.value = None
            return False, None

        signaled = len(setter_flags) > 0 and self.expression(setter_flags)
        if signaled:
            payload = self._payload_from_states(setter_states)
            self.signaled = True
            self.value = payload
            return True, payload
        self.signaled = False
        self.value = None
        return False, None

    def _evaluate_two_phase(self, token: Optional[int], drive_event: Optional[EventType]) -> Tuple[bool, Optional[Dict[Union[DSFilter, "DSCircuit"], EventType]]]:
        """Two-pass evaluation for trees containing side-effecting conditions.

        Pass 1 (_select_into) is pure: it guards every branch needed to decide
        eligibility, claiming resources via reservations so sibling guards see
        each other. Pass 2 (plan.commit) performs exactly the selected
        operations - one branch for OR, all branches for AND - so an OR of
        puts routes to exactly one queue and an AND of puts/gets is
        all-or-nothing, atomically within the current simulation instant.
        """
        if not self.positive:
            raise ValueError('Two-phase conditions cannot be used under a negated circuit.')
        if self._flat_two_phase_or:
            return self._evaluate_flat_or(drive_event)
        # Reuse the circuit-owned plan: commits cannot synchronously re-enter
        # evaluation (they publish via the deferred now-queue), so the plan is
        # never in use when a new pass on this circuit starts.
        plan = self._plan
        plan.clear()
        if not self._select_into(plan, token, drive_event):
            plan.release_all()
            self.signaled = False
            self.value = None
            return False, None
        payload = plan.commit()
        self.signaled = True
        self.value = payload
        return True, payload

    def _evaluate_flat_or(self, drive_event: Optional[EventType]) -> Tuple[bool, Optional[Dict[Union[DSFilter, "DSCircuit"], EventType]]]:
        """One-pass evaluation for a flat OR whose setters are all two-phase
        leaves - the router topology, and by far the hottest circuit shape.

        WHY THIS IS SAFE WITHOUT THE _TwoPhasePlan MACHINERY
        The plan (guard everything -> select -> commit/rollback) exists to give
        OR exactly-one and AND all-or-nothing semantics ACROSS branches. A flat
        OR has no cross-branch atomicity to protect: the general path walks
        branches in selector order and stops at the first eligible one, so at
        most one branch is ever guarded successfully, and nothing runs between
        that guard and its commit (evaluation is synchronous, and commits
        publish only via the deferred now-queue, so nothing can observe or
        preempt the half-open state). Fusing guard+commit per branch is
        therefore observably identical to plan-select-then-commit, while
        skipping the plan bookkeeping, the rollback marks and the second pass.

        Everything semantically relevant is kept identical to the general path:
        - branches are probed in the same selector order (ordered from 0,
          round_robin from the cursor), and failed guards leave no claim
          behind (a failed guard() claims nothing by contract);
        - an already-latched leaf (committed by an earlier evaluation, not
          reset since) short-circuits as the winner exactly like the general
          path's add_latched entry;
        - the winner is committed via the same leaf _commit_two_phase() (latch
          + endpoint emit), the round_robin cursor advances only on a real
          commit, and the payload has the same {leaf: value} shape.
        Any other topology (AND, nested circuits, mixed pure/two-phase
        branches, resetters) keeps the general plan-based path.
        """
        setters = self.setters
        count = len(setters)
        probe = drive_event if drive_event is not None else TestObject
        first = self._sel_cursor % count if self.selector == 'round_robin' else 0
        for i in range(count):
            idx = (first + i) % count
            leaf = setters[idx]
            if leaf.signaled:
                value = leaf.value
            elif leaf.cond.guard(probe):
                value = leaf._commit_two_phase()
            else:
                continue
            if self.selector == 'round_robin':
                self._sel_cursor = (idx + 1) % count
            payload = {leaf: value}
            self.signaled = True
            self.value = payload
            return True, payload
        self.signaled = False
        self.value = None
        return False, None

    def _select_into(self, plan: _TwoPhasePlan, token: Optional[int], drive_event: Optional[EventType]) -> bool:
        """Pure selection pass: record latched values and guard reservations into *plan*.

        Returns eligibility of this node. On failure every reservation taken
        for this subtree has been released (rollbacks are LIFO, keeping queue
        reservations contiguous - see _TwoPhasePlan).
        """
        if self.signaled and not self.reevaluate:
            plan.add_latched(self, self.cond_value())
            return True
        # Two-phase resetters are rejected at construction time (set_signals).
        resetter_flags = [self._state_for(s, token, drive_event)[0] for s in self.resetters]
        if len(resetter_flags) > 0 and self.expression(resetter_flags):
            for el in self.setters:
                self._reset_signal(el)
            self.signaled = False
            self.value = None
            return False

        start = plan.mark()
        if self.expression == any:
            count = len(self.setters)
            first = self._sel_cursor % count if self.selector == 'round_robin' else 0
            for i in range(count):
                idx = (first + i) % count
                branch_mark = plan.mark()
                if self._child_select(self.setters[idx], self._setter_kinds[idx], plan, token, drive_event):
                    plan.close_circuit(self, start, winner=idx)
                    return True
                plan.rollback_to(branch_mark)
            return False
        for idx, s in enumerate(self.setters):
            if not self._child_select(s, self._setter_kinds[idx], plan, token, drive_event):
                plan.rollback_to(start)
                return False
        plan.close_circuit(self, start)
        return True

    def _child_select(self, signal: SignalType, kind: int, plan: _TwoPhasePlan, token: Optional[int], drive_event: Optional[EventType]) -> bool:
        """Select one child: guard two-phase leaves, recurse into two-phase circuits,
        read pure signals through the legacy state logic. *kind* is the tag
        precomputed by set_signals - no per-pass isinstance dispatch."""
        if kind == self._KIND_TWO_PHASE_LEAF:
            if signal.signaled:
                # Committed by an earlier evaluation and not reset since - latched.
                plan.add_latched(signal, signal.value)
                return True
            probe = drive_event if drive_event is not None else TestObject
            if not signal.cond.guard(probe):
                return False
            plan.add_pending(signal)
            return True
        if kind == self._KIND_TWO_PHASE_CIRCUIT:
            return signal._select_into(plan, token, drive_event)
        signaled, value = self._state_for(signal, token, drive_event)
        if signaled:
            plan.add_latched(signal, value)
        return signaled

    def _flush_notify(self) -> bool:
        """Perform deferred one-shot evaluation for the latest pending token."""
        token = self._pending_token if self._pending_token >= 0 else None
        self._pending = False
        self._pending_token = -1
        if self._listeners and self._two_phase:
            # This circuit sits inside a larger two-phase tree: commit authority
            # belongs to the root evaluation, so only propagate the wakeup.
            for circuit in tuple(self._listeners):
                circuit.notify(self, token=(token if token is not None else self.sim.num_events),
                               signaled=False, value=None, event=None)
            return False
        return self._publish_evaluation(token)

    def _publish_single_branch(self, leaf: "DSFilter", token: Optional[int]) -> bool:
        """O(1) wakeup for a flat two-phase OR root: evaluate only *leaf*, the
        branch whose endpoint event triggered this call.

        WHY EVALUATING ONE BRANCH IS ENOUGH
        A router branch's eligibility (queue has room / has items, pool has
        units / headroom) changes only when its channel's state changes, and
        every such change publishes an endpoint event to exactly the filters
        subscribed to that channel. So between the last evaluation of this
        root (the initial check_and_wait probe, or a previous wakeup - each of
        which found no eligible branch, else it would have fired) and this
        event, no OTHER branch can have become eligible: it received no event.
        Evaluating the notified branch alone is therefore equivalent to the
        full scan, at O(1) instead of O(branches) per wakeup.

        WHY SELECTOR SEMANTICS SURVIVE
        - 'ordered': a lower-index branch would only outrank *leaf* if it were
          eligible right now - excluded by the argument above.
        - 'round_robin': the full scan would also select the only eligible
          branch wherever the cursor points; the cursor advances past the
          winner exactly like the general path.
        If one event makes several branches eligible (channels sharing an
        injected endpoint), every subscribed filter receives its own send()
        and runs its own single-branch attempt in subscriber-arbitration
        order - no wakeup is ever lost, and exactly one branch commits per
        available claim.

        FALLBACKS keep byte-identical semantics for the rare states where the
        one-branch argument does not apply: a root already signaled (latched /
        reevaluate interplay) or a leaf latched from an earlier pass defers to
        the full evaluation instead.
        """
        if self.signaled or leaf.signaled:
            return self._publish_evaluation(token)
        # Probe with TestObject, matching _publish_evaluation's drive_event=None.
        if not leaf.cond.guard(TestObject):
            return False
        value = leaf._commit_two_phase()
        if self.selector == 'round_robin':
            self._sel_cursor = (self._setter_index[id(leaf)] + 1) % len(self.setters)
        payload = {leaf: value}
        self.signaled = True
        self.value = payload
        # Publish exactly like _publish_evaluation on a fired root.
        if self.signal_to_endpoint:
            self._finish_tx.signal(payload)
        if self._listeners:
            for circuit in tuple(self._listeners):
                circuit.notify(self, token=(token if token is not None else self.sim.num_events),
                               signaled=True, value=payload, event=payload)
        if self.one_shot and self._is_attached:
            self.detach()
        return True

    def _publish_evaluation(self, token: Optional[int]) -> bool:
        """Evaluate now and publish the outcome. Shared by the deferred flush
        and the immediate two-phase root fire triggered from a leaf."""
        signaled, payload = self._evaluate(token=token, drive_event=None)
        if signaled and self.signal_to_endpoint:
            self._finish_tx.signal(payload)
        if self._listeners:
            for circuit in tuple(self._listeners):
                circuit.notify(self, token=(token if token is not None else self.sim.num_events), signaled=signaled, value=payload, event=payload)
        if signaled and self.one_shot and self._is_attached:
            self.detach()
        return signaled

    @TrackEvent
    def send(self, event: EventType) -> bool:
        """Handle direct event drive or internal deferred _NOTIFY flush."""
        if event is self._NOTIFY:
            return self._flush_notify()
        token = self.sim.num_events
        signaled, payload = self._evaluate(token=token, drive_event=event)
        if signaled and self.signal_to_endpoint:
            self._finish_tx.signal(payload)
        if self._listeners:
            for circuit in tuple(self._listeners):
                circuit.notify(self, token=token, signaled=signaled, value=payload, event=event)
        if signaled and self.one_shot and self._is_attached:
            self.detach()
        return signaled

    def get_eps(self) -> Set["DSPub"]:
        """Expose wait endpoint used by observe_pre/wait infrastructure."""
        return {self._finish_tx}

    def check(self, event: EventType) -> Tuple[bool, EventType]:
        """Evaluate/probe this circuit and return (signaled, payload)."""
        if event is TestObject:
            if self.signaled:
                return True, self.cond_value()
            token = self.sim.num_events
            signaled, payload = self._evaluate(token=token, drive_event=event)
            if signaled:
                return True, payload
            return False, None
        if isinstance(event, dict) and len(event) > 0 and all(isinstance(k, (DSFilter, DSCircuit)) for k in event.keys()):
            return True, event
        if self.signaled and event == self.value:
            return True, self.cond_value()
        token = self.sim.num_events
        signaled, payload = self._evaluate(token=token, drive_event=event)
        if signaled:
            return True, payload
        return False, None
    

# In the following, self is in fact of type DSSimulation, but PyLance makes troubles with variable types
class SimFilterMixin:
    def filter(self: Any, *args: Any, **kwargs: Any) -> DSFilter:
        sim: DSSimulation = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in filter() method should be set to the same simulation instance.')
        return DSFilter(*args, **kwargs, sim=sim)

    def circuit(self: Any, *args: Any, **kwargs: Any) -> DSCircuit:
        sim: DSSimulation = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in circuit() method should be set to the same simulation instance.')
        return DSCircuit(*args, **kwargs, sim=sim)
