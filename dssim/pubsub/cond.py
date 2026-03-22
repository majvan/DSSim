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
from dssim.pubsub.base import CondType, ICondition, CallableConditionMixin, SubscriberMetadata, TestObject, AlwaysTrue
from dssim.pubsub.future import DSFuture
from dssim.pubsub.pubsub import TrackEvent


if TYPE_CHECKING:
    from dssim.pubsub.pubsub import DSPub
    from dssim.simulation import DSSimulation


FilterExpression = Callable[[Iterable[object]], bool]
SignalType = Union["DSFilter", "DSCircuit"]
SignalList = List[SignalType]


class _ConditionProxy(ICondition, CallableConditionMixin):
    """Adapter that preserves ICondition semantics but avoids DSFuture shortcuts."""

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
        self._base_eps: Mapping["DSPub", Any] = MappingProxyType({})
        self._eps: Dict["DSPub", Any] = {}
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
                source_eps = {ep: ep.Phase.PRE for ep in get_eps()}
        self._base_eps = MappingProxyType(source_eps)

    def _normalize_base_eps(self, eps: Union[Iterable["DSPub"], Mapping["DSPub", Any]]) -> Dict["DSPub", Any]:
        if isinstance(eps, Mapping):
            return {ep: phase for ep, phase in eps.items()}
        return {ep: ep.Phase.PRE for ep in eps}

    def _refresh_cond_traits(self) -> None:
        """Cache condition traits used in the hot check()/_match_event() path."""
        self._cond_is_future = isinstance(self.cond, DSFuture)
        self._cond_is_icond = isinstance(self.cond, ICondition)
        self._cond_is_callable = callable(self.cond)

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
        for ep, phase in tuple(self._base_eps.items()):
            if ep in self._eps:
                continue
            self._eps[ep] = phase
            ep.add_subscriber(self, phase)

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
        for ep, phase in tuple(self._eps.items()):
            ep.remove_subscriber(self, phase)
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
            return True, self.cond_value()

        self.signaled = matched
        if matched:
            self.value = value
            return True, self.cond_value()
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
        was_signaled = self.signaled
        signaled, value = self.check(event, token=token)
        if signaled and (self.pulse or self.reevaluate or not was_signaled):
            self._emit_match(value)
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
            return True, self.cond_value()
        if event is TestObject:
            if self.pulse:
                return False, None
            if self.signaled:
                return True, self.cond_value()
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

    def set_signals(self) -> None:
        """Split children into setters and resetters and wire listeners."""
        self.setters, self.resetters = [], []
        for s in self.signals:
            if s.positive:
                self.setters.append(s)
            else:
                self.resetters.append(s)
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

    def _flush_notify(self) -> bool:
        """Perform deferred one-shot evaluation for the latest pending token."""
        token = self._pending_token if self._pending_token >= 0 else None
        self._pending = False
        self._pending_token = -1
        signaled, payload = self._evaluate(token=token, drive_event=None)
        if signaled and self.signal_to_endpoint:
            self._finish_tx.signal(payload)
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
