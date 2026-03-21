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
from typing import List, Set, Any, Dict, Tuple, Union, Optional, Callable, Iterable, Generator, TYPE_CHECKING
import inspect
import copy
from enum import Enum
from dssim.base import TimeType, EventType, EventRetType
from dssim.pubsub.base import CondType, AlwaysTrue, ICondition, ISourceScoped, CallableConditionMixin, SubscriberMetadata, TestObject, SourceAwareEvent
from dssim.pubsub.future import DSFuture
from dssim.pubsub.process import DSProcess
from dssim.pubsub.pubsub import TrackEvent


if TYPE_CHECKING:
    from dssim.pubsub.pubsub import DSPub
    from dssim.simulation import DSSimulation


FilterExpression = Callable[[Iterable[object]], bool]
SignalType = Union["DSFilter", "DSCircuit"]
SignalList = List[SignalType]


def _split_source_aware(event: EventType) -> Tuple[EventType, Optional[object]]:
    if isinstance(event, SourceAwareEvent):
        return event.event, event.source
    return event, None


class _ConditionWaitMixin:
    def gwait(self, timeout: TimeType = float('inf'), val: EventRetType = True) -> Generator[EventType, EventType, EventType]:
        # Self-contained gated wait: subscribe to condition endpoints while blocked.
        with self.sim.observe_pre(self):
            retval = yield from self.sim.gwait(timeout=timeout, cond=self, val=val)
        return retval

    async def wait(self, timeout: TimeType = float('inf'), val: EventRetType = True) -> EventType:
        # Self-contained gated wait: subscribe to condition endpoints while blocked.
        with self.sim.observe_pre(self):
            return await self.sim.wait(timeout=timeout, cond=self, val=val)

    def check_and_gwait(self, timeout: TimeType = float('inf'), val: EventRetType = True) -> Generator[EventType, EventType, EventType]:
        # Pre-check first (without endpoint registration). Register producers only
        # when we actually need to block.
        signaled, event = self.check(TestObject)
        if signaled:
            return event
        with self.sim.observe_pre(self):
            retval = yield from self.sim.gwait(timeout=timeout, cond=self, val=val)
        return retval

    async def check_and_wait(self, timeout: TimeType = float('inf'), val: EventRetType = True) -> EventType:
        # Pre-check first (without endpoint registration). Register producers only
        # when we actually need to block.
        signaled, event = self.check(TestObject)
        if signaled:
            return event
        with self.sim.observe_pre(self):
            return await self.sim.wait(timeout=timeout, cond=self, val=val)


class DSEpsCond(ICondition, ISourceScoped, CallableConditionMixin):
    '''Reusable condition wrapper with explicit event publishers (endpoints).

    Useful for REEVALUATE filters when condition state can toggle over time and
    rechecks must be triggered by specific publishers.
    '''

    def __init__(self, cond: CondType = AlwaysTrue, eps: Iterable["DSPub"] = ()) -> None:
        self.cond = cond
        self._eps = tuple(eps)
        self.value: EventType = None

    def check(self, event: EventType) -> Tuple[bool, EventType]:
        if callable(self.cond):
            signaled = bool(self.cond(event))
        else:
            signaled = self.cond == event
        self.value = event if signaled else None
        return signaled, self.value

    def cond_value(self) -> EventType:
        return self.value

    def get_eps(self) -> Set["DSPub"]:
        return set(self._eps)

    def is_relevant_source(self, source: object) -> bool:
        if source is None:
            return True
        return any(ep is source for ep in self._eps)

    def __str__(self) -> str:
        return f'DSEpsCond({self.cond})'


class DSFilter(_ConditionWaitMixin, DSFuture, ICondition, ISourceScoped, CallableConditionMixin):
    ''' A future which can be used in the circuit. It can be used as a signal to a
    circuit.

    Features:
    1. DSFilter can be reevaluated, i.e. the finished() is not monostable. It can
    once return True and the next call return False (if reevaluate is True).
    2. DSFilter can be pulsed, i.e. the finished() never returns True, but the call
    to DSFilter can return True (signaled). This requires the filter to be reevaluated.
    3. DSFilter can be negated. This is possible: filter = -DSFilter(...).
    Such expression will always change the filter policy to be pulsed.
    4. DSFilter can forward all the events to the attached cond (default for generators
    and coroutines).
    '''

    class SignalType(Enum):
        DEFAULT = 0  # Monostable. If once signaled, always signaled
        REEVALUATE = 1  # Reevaluated after every event, i.e. the value changes after every event
        PULSED = 2  # Returns "signaled" only when __call__(event) matches, but never stays in the state

    ONE_LINER = None
    cond_source_aware: bool = True
    dispatch_direct: bool = False
    dispatch_source_aware: bool = True

    def __init__(self, cond: CondType = None, sigtype: SignalType = SignalType.DEFAULT, signal_timeout: bool = False, forward_events: Optional[bool] = None, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.expression: Optional[FilterExpression] = self.ONE_LINER
        self.signals: SignalList = [self,]
        self.positive = True  # positive sign
        self.signaled = False
        self.value: EventType = None
        self.cond = cond
        # Reevaluation means that after every event we receive we have to re-evaluate
        # the condition
        # If not reevaluation set, then once filter matches, it is flipped to signaled
        self.pulse = sigtype in (self.SignalType.PULSED,)
        self.reevaluate = sigtype in (self.SignalType.REEVALUATE, self.SignalType.PULSED,)
        # Signalling timeout is for generators. If a generator returns with None, this means
        # that it timed out. If signal_timeout is True, such timeout would be understood
        # as a valid signal.
        self.signal_timeout = signal_timeout
        if inspect.isgenerator(self.cond) or inspect.iscoroutine(self.cond):
            # We create a new process from generator
            self.cond = self.sim.process(self.cond).schedule(0)  # convert to DSProcess so we could get return value
            # It is assumed that the coro / generator runs in the same 'context' as the current process.
            # The coro / generator gets events which were planned for the current running process by default.
            self.forward_events = (forward_events != False)  # True => True, None => True, False => False
        else:
            self.forward_events = (forward_events == True)  # True => True, None => False, False => False

    def create_metadata(self, **kwargs: Any) -> SubscriberMetadata:
        self.meta = SubscriberMetadata()
        # A condition accepts any event 
        self.meta.cond.push(lambda e:True)
        return self.meta

    @TrackEvent
    def send(self, event: EventType) -> bool:
        event, source = _split_source_aware(event)
        # DSFilter.send must use condition semantics (not DSFuture.finish semantics).
        if event is TestObject:
            return self.check(event, source)[0]
        was_signaled = self.signaled
        signaled, _ = self.check(event, source)
        # Wake waiters that observe this filter via _finish_tx.
        # Use the original payload so REEVALUATE conditions keep correct state.
        if signaled and (self.reevaluate or not was_signaled):
            # PULSED filters must deliver the real event so waiters receive the value.
            # REEVALUATE (non-pulse) fires TestObject so circuit.check(TestObject) re-reads
            # each filter's cached signaled state without cross-contaminating other filters.
            wakeup = event if self.pulse else TestObject
            self._finish_tx.signal(wakeup)
        return signaled

    def gwait(self, timeout: TimeType = float('inf'), val: EventRetType = True) -> Generator[EventType, EventType, EventType]:
        # Keep DSFilter wait semantics value-centric even when already signaled.
        if self.signaled:
            return self.cond_value()
        with self.sim.observe_pre(self):
            retval = yield from self.sim.gwait(timeout=timeout, cond=self, val=val)
        return retval

    async def wait(self, timeout: TimeType = float('inf'), val: EventRetType = True) -> EventType:
        # Keep DSFilter wait semantics value-centric even when already signaled.
        if self.signaled:
            return self.cond_value()
        with self.sim.observe_pre(self):
            return await self.sim.wait(timeout=timeout, cond=self, val=val)

    def __or__(self, other: "DSFilter") -> "DSCircuit":
        return DSCircuit.build(self, other, any)

    def __and__(self, other: "DSFilter") -> "DSCircuit":
        return DSCircuit.build(self, other, all)
   
    def __neg__(self) -> "DSFilter":
        if not self.positive:
            raise ValueError('You can negate a DSFilter only once')
        f = copy.copy(self)
        f.pulse, f.reevaluate = True, True
        f.positive = False
        return f

    def __str__(self) -> str:
        retval = f'DSFilter({self.cond})'
        if not self.positive:
            retval = '-' + retval
        return retval

    def finished(self) -> bool:
        return self.signaled

    def _check_event(self, event: EventType, allow_forward: bool) -> Tuple[bool, EventType]:
        signaled, value = False, None
        if isinstance(self.cond, DSFuture):
            # now we should get this signaled only after return
            if self.forward_events and allow_forward:
                # Process bootstrap must always be generator.send(None).
                # If the process is not started yet, discard the triggering
                # payload and use None to prime it.
                forwarded = event
                if isinstance(self.cond, DSProcess) and not self.cond.started():
                    forwarded = None
                # Route through simulation dispatch so condition-gated
                # subscribers and finished processes are handled uniformly.
                self.sim.send_object(self.cond, forwarded)
            if self.cond.finished():
                if self.cond.exc is not None:
                    pass
                elif self.cond.value is None and self.signal_timeout:
                    signaled, value = True, None
                elif self.pulse:
                    signaled, value = (event == self.cond), event
                else:
                    signaled, value = True, self.cond.value
        elif self.cond == event:
            signaled, value = True, event
        elif callable(self.cond) and self.cond(event):
            signaled, value = True, event
        # elif self is event:
        #     signaled, value = True, event
        if not self.pulse:
            # A resetting- circuit only pulses its signal, but does not keep the signal, neither value
            self.signaled = signaled
        if signaled:
            self._finish(value, async_future=False)
            return True, self.cond_value()
        return False, None

    def check(self, event: EventType, source: Optional[object] = None) -> Tuple[bool, EventType]:
        event, scoped_source = _split_source_aware(event)
        if source is None:
            source = scoped_source
        if isinstance(self.cond, ISourceScoped) and not self.cond.is_relevant_source(source):
            if self.signaled:
                return True, self.cond_value()
            return False, None
        if self.signaled and not self.reevaluate:
            return True, self.cond_value()
        # Probe mode used by check_and_wait/check_and_gwait.
        # Keep already-signaled state untouched, otherwise evaluate without
        # forwarding payload into nested futures/processes.
        if event is TestObject:
            if self.signaled:
                return True, self.cond_value()
            return self._check_event(event, allow_forward=False)
        return self._check_event(event, allow_forward=True)

    def get_eps(self) -> Set["DSPub"]:
        retval = {self._finish_tx,}
        get_eps = getattr(self.cond, 'get_eps', None)
        if callable(get_eps):
            retval |= set(get_eps())
        return retval

    def is_relevant_source(self, source: object) -> bool:
        if source is None:
            return True
        if isinstance(self.cond, ISourceScoped):
            return self.cond.is_relevant_source(source)
        return True

    def finish(self, value: EventType) -> None:
        self._finish(value, async_future=True)

    def _finish(self, value: EventType, async_future: bool) -> None:
        self.value = value
        if not self.pulse:
            self.signaled = True
        if async_future:
            # Async finish should wake waiters in probe mode so circuits evaluate
            # cached signaled states and do not accidentally reset sibling filters.
            self._finish_tx.signal(TestObject)

    def cond_value(self) -> EventType:
        return self.value


class DSCircuit(_ConditionWaitMixin, DSFuture, ICondition, CallableConditionMixin):
    ''' DSCircuit aggregates several DSFutures / DSCircuits into logical
    circuit (AND / OR).

    It evaluates the circuit after every event by propagating down (to the signals)
    all the events.
    '''

    cond_source_aware: bool = True
    dispatch_direct: bool = False
    dispatch_source_aware: bool = True

    def __init__(self, expression: FilterExpression, signals: SignalList, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.expression = expression
        self.signals = signals
        self.set_signals()
        self.positive = True
        self.signaled = False
        # The sim is required for awaitable
        self.sim = self.signals[0].sim  # get the sim from the first signal

    @staticmethod
    def build(first: SignalType, second: SignalType, expr: FilterExpression) -> "DSCircuit":
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
            # A reset circuit is mergeable only if it is one_liner. The reason
            # is that a reset circuit when signaled resets all his setters.
            if not second.positive:
                assert type(first) == DSCircuit
                first.signals.append(second)
                first.set_signals()
                return first
        return DSCircuit(expr, [first, second])

    def set_signals(self) -> None:
        self.setters, self.resetters = [], []
        for s in self.signals:
            if s.positive:
                self.setters.append(s)
            else:
                self.resetters.append(s)

    def __or__(self, other: "DSCircuit") -> "DSCircuit":
        return DSCircuit.build(self, other, any)

    def __and__(self, other: "DSCircuit") -> "DSCircuit":
        return DSCircuit.build(self, other, all)

    def __neg__(self) -> "DSCircuit":
        self.positive = False
        return self

    def cond_value(self) -> Dict[Union[DSFilter, "DSCircuit"], EventType]:
        retval: Dict[Union[DSFilter, "DSCircuit"], EventType] = {}
        for el in self.setters:
            if not el.finished():
                continue
            if isinstance(el, DSCircuit):
                embedded = el.cond_value()
                retval.update(embedded)
            elif hasattr(el, 'cond_value'):
                retval[el] = el.cond_value()
            else:
                retval[el] = el.value
        return retval
    
    def __str__(self) -> str:
        expression = ' | ' if self.expression == any else ' & '
        strings = [str(v) for v in self.setters + self.resetters]
        retval = expression.join(strings)
        sign = '' if self.positive else '-'
        return f'{sign}({retval})'

    def finished(self) -> bool:
        return self.signaled

    def _is_relevant_source(self, signal: SignalType, source: Optional[object]) -> bool:
        if source is None:
            return True
        if isinstance(signal, ISourceScoped):
            return signal.is_relevant_source(source)
        return True

    def _gather_results(self, event: EventType, futures: SignalList, source: Optional[object] = None) -> List[bool]:
        retval = []
        for fut in futures:
            if isinstance(fut, ICondition) and self._is_relevant_source(fut, source):
                signaled = fut.check(event, source)[0]
            else:
                signaled = fut.finished()
            retval.append(signaled)
        return retval

    def get_eps(self) -> Set["DSPub"]:
        retval = set()
        # Including self._finish_tx would create loop dependency when waiting on self (i.e. await self):
        # 1. When this is finished, it would signal _finish_tx
        # 2. _finish_tx would produce an event which would be caught by self and self would signal again
        # Another solution for this is not to produce signaled state if the event comes from self._finish_tx
        for s in self.signals:
            retval |= s.get_eps()
        return retval

    def check(self, event: EventType, source: Optional[object] = None) -> Tuple[bool, EventType]:
        ''' Handles logic for the event. Pushes the event to the inputs and then evaluates the circuit. '''
        event, scoped_source = _split_source_aware(event)
        if source is None:
            source = scoped_source
        signaled = False
        # In the following, we have to send the event to the whole circuit. The reason is that
        # once some gate is signaled, it could be reset later; however if the signal stops event
        # to be spread to other gates; the other gates could be activated as well with the same
        # event.
        if not self.positive:
            # For resetting signals we check if they are signaled
            if len(self.setters) > 0:
                results = self._gather_results(event, self.setters, source)
                signaled = self.expression(results)
            if signaled:
                # and if they are signaled, they reset the input setters
                for el in self.setters:
                    el.signaled = False
        else:
            # For normal (mixed signals) we check first if the logic of reseters reset the circuit
            if len(self.resetters) > 0:
                results = self._gather_results(event, self.resetters, source)
                reset_signal = self.expression(results)
            else:
                reset_signal = False
            if reset_signal:
                # If they do, they reset the input setters
                for el in self.setters:
                    el.signaled = False
                signaled = False
            else:
                if len(self.setters) > 0:
                    results = self._gather_results(event, self.setters, source)
                    signaled = self.expression(results)
            self.signaled = signaled
            if signaled:
                self.finish(self.cond_value())
        if signaled:
            return True, self.cond_value()
        return False, None
    

# In the following, self is in fact of type DSSimulation, but PyLance makes troubles with variable types
class SimFilterMixin:
    def eps_cond(self: Any, cond: CondType = AlwaysTrue, eps: Iterable["DSPub"] = ()) -> DSEpsCond:
        return DSEpsCond(cond=cond, eps=eps)

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
