# Copyright 2021-2022 NXP Semiconductors
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
This file implements process for simulation + functionality required in
the applications using processes.
'''
from __future__ import annotations
from typing import Any, Tuple, Union, Optional, Generator, Coroutine, Iterator, Callable, TypeVar, TYPE_CHECKING
from types import TracebackType
from contextlib import contextmanager
from functools import wraps
import inspect
from dssim.base import TimeType, EventType, EventRetType, SignalMixin, ISubscriber
from dssim.pubsub_base import CondType, AlwaysFalse, AlwaysTrue, DSAbortException, DSTransferableCondition, SubscriberMetadata
from dssim.pubsub import DSSub, DSCallback, TrackEvent, DSPub
from dssim.future import DSFuture


if TYPE_CHECKING:
    from dssim.simulation import DSSimulation, SchedulableType

DSProcessType = TypeVar('DSProcessType', bound='DSProcess')

# Singleton sentinel used as the scheduled event for process start-up.
# Using a shared object (instead of a per-process _ScheduleEvent instance) lets
# _Starter.send() remove it from the cond stack by identity regardless of its
# position — so user-pushed conditions between schedule() and start are safe.
_StartProcess = object()

# An artificial object to be used for check_and_wait- see description of the method
_TestObject = object()


class DSProcess(DSFuture, SignalMixin):
    ''' Typical task used in the simulations.
    This class "extends" generator / coroutine for additional info.
    The best practise is to use DSProcess instead of generators.
    '''
    class _Starter(DSSub):
        ''' One-shot bootstrap subscriber for DSProcess.
        Scheduled in place of the process itself so DSProcess.send() can be
        branch-free: no "first call?" check on every event delivered to the process.
        '''
        def __init__(self, process: 'DSProcess') -> None:
            self._process = process
            super().__init__(sim=process.sim, cond=AlwaysTrue)

        def send(self, event: EventType) -> EventRetType:
            p = self._process
            if p._started:
                return None  # already initialized — no-op (idempotent guard)
            p._started = True
            p.get_cond().conds.remove(_StartProcess)  # remove by identity, order-independent
            p.meta.cond.push(None)  # add timeout sentinel (None == timeout)
            return p.sim.send_object(p, None)  # deliver first generator.send(None)

    def __init__(self, generator: Union[Generator, Coroutine], *args: Any, **kwargs: Any) -> None:
        ''' Initializes DSProcess. The input has to be a generator function. '''
        self.generator = generator
        self._scheduled = False
        self._started = False
        self._finished = False
        self._starter = None
        # One-time validation that the generator / coroutine has not been started yet.
        # Uses inspect here intentionally — this path is cold (called once at construction).
        if inspect.iscoroutine(generator):
            if inspect.getcoroutinestate(generator) != inspect.CORO_CREATED:
                raise ValueError('The DSProcess can be used only on non-started generators / coroutines')
        elif inspect.isgenerator(generator):
            if inspect.getgeneratorstate(generator) != inspect.GEN_CREATED:
                raise ValueError('The DSProcess can be used only on non-started generators / coroutines')
        else:
            raise ValueError(f'The assigned code {generator} to the process is not a generator, neither a coroutine.')
        super().__init__(*args, **kwargs)

    def create_metadata(self, **kwargs: Any) -> SubscriberMetadata:
        self.meta = SubscriberMetadata()
        return self.meta

    # TODO: this feature is not required
    def __iter__(self: DSProcessType) -> DSProcessType:
        ''' Required to use the class to get events from it. '''
        return self

    def __next__(self) -> EventRetType:
        ''' Gets next state, without pushing any particular event. '''
        self.value = self.generator.send(None)
        return self.value

    @TrackEvent
    def send(self, event: EventType) -> EventRetType:
        ''' Pushes an event to the task and gets new state. '''
        self.value = self.generator.send(event)
        return self.value

    def gwait(self, timeout: TimeType = float('inf'), cond: CondType = AlwaysFalse, val: EventRetType = True) -> Generator[EventType, EventType, EventType]:
        ''' Wait for an event for max. timeout time, accepting only events where cond is True.
        When cond is a DSFuture (or DSProcess), automatically subscribes to its finish endpoint
        so the caller wakes up when the future completes.
        '''
        if isinstance(cond, DSFuture):
            if cond.finished():
                if cond.exc is not None:
                    raise cond.exc
                return cond
            with self.sim.observe_pre(cond):
                conds = self.meta.cond  # capture ref: sim.cleanup() replaces self.meta.cond
                conds.push(cond)
                try:
                    event = yield from self.sim._gwait_for_event(timeout, val)
                finally:
                    conds.pop()
            if cond.exc is not None:
                raise cond.exc
            if hasattr(cond, 'cond_value'):
                return cond.cond_value()
            return event
        conds = self.meta.cond  # capture ref: sim.cleanup() replaces self.meta.cond, so finally must use the original
        conds.push(cond)
        try:
            event = yield from self.sim._gwait_for_event(timeout, val)
        finally:
            conds.pop()
        if hasattr(cond, 'cond_value'):
            event = cond.cond_value()
        return event

    async def wait(self, timeout: TimeType = float('inf'), cond: CondType = AlwaysFalse, val: EventRetType = True) -> EventType:
        ''' Async variant of gwait.
        When cond is a DSFuture (or DSProcess), automatically subscribes to its finish endpoint.
        '''
        if isinstance(cond, DSFuture):
            if cond.finished():
                if cond.exc is not None:
                    raise cond.exc
                return cond
            with self.sim.observe_pre(cond):
                conds = self.meta.cond  # capture ref: sim.cleanup() replaces self.meta.cond
                conds.push(cond)
                try:
                    event = await self.sim._wait_for_event(timeout, val)
                finally:
                    conds.pop()
            if cond.exc is not None:
                raise cond.exc
            if hasattr(cond, 'cond_value'):
                return cond.cond_value()
            return event
        conds = self.meta.cond  # capture ref: sim.cleanup() replaces self.meta.cond, so finally must use the original
        conds.push(cond)
        try:
            event = await self.sim._wait_for_event(timeout, val)
        finally:
            conds.pop()
        if hasattr(cond, 'cond_value'):
            event = cond.cond_value()
        return event

    def check_and_gwait(self, timeout: TimeType = float('inf'), cond: CondType = AlwaysFalse, val: EventRetType = True) -> Generator[EventType, EventType, EventType]:
        ''' Pre-check cond before waiting; return immediately if already satisfied. '''
        conds = self.meta.cond  # capture ref: sim.cleanup() replaces self.meta.cond
        conds.push(cond)
        try:
            signaled, event = conds.check(_TestObject)
            if not signaled:
                event = yield from self.sim._gwait_for_event(timeout, val)
            else:
                event = conds.cond_value()
        finally:
            conds.pop()
        return event

    async def check_and_wait(self, timeout: TimeType = float('inf'), cond: CondType = AlwaysFalse, val: EventRetType = True) -> EventType:
        ''' Async variant of check_and_gwait. '''
        conds = self.meta.cond  # capture ref: sim.cleanup() replaces self.meta.cond
        conds.push(cond)
        try:
            signaled, event = conds.check(_TestObject)
            if not signaled:
                event = await self.sim._wait_for_event(timeout, val)
            else:
                event = conds.cond_value()
        finally:
            conds.pop()
        return event

    def schedule(self: DSProcessType, time: Optional[TimeType] = 0) -> DSProcess:
        ''' This api is to schedule the process '''
        if not self._scheduled:
            self._scheduled = True
            # _Starter handles the first-kick initialization so send() stays branch-free
            self._starter = self._Starter(self)
            # Guard: push _StartProcess sentinel onto the cond stack to reject
            # spurious events delivered to the process before it actually starts
            self.get_cond().push(_StartProcess)
            self.sim.schedule_event(time, _StartProcess, self._starter)
        return self

    def abort(self, exc: Optional[Exception] = None) -> None:
        ''' Aborts the process.

        If the process has not yet started (still sitting in the time queue),
        fail() removes the starter entry from the queue and marks the process
        as failed — no generator code ever runs.  If the process has already
        started, the base-class behaviour applies (send DSAbortException into
        the running generator).
        '''
        if not self.started():
            if exc is None:
                exc = DSAbortException(self)
            self.fail(exc)
        else:
            super().abort(exc)

    def started(self) -> bool:
        return self._started

    def finished(self) -> bool:
        ''' The finished evaluation cannot be the same as with the Futures because a process
        changes its value / exc more times during its runtime.
        '''
        return self._finished

    def finish(self, value: EventType) -> EventType:
        self._finished = True
        self.value = value
        if self._starter is not None:
            self.sim.time_queue.delete_cond(lambda e: e[0] is self._starter)
            self._starter = None
        self.sim.cleanup(self)
        # The last event is the process itself. This enables to wait for a process as an asyncio's Future
        self._finish_tx.signal(self)
        return self.value

    def fail(self, exc: Exception) -> Exception:
        self._finished = True
        self.exc = exc
        if self._starter is not None:
            self.sim.time_queue.delete_cond(lambda e: e[0] is self._starter)
            self._starter = None
        self.sim.cleanup(self)
        self._finish_tx.signal(self)
        return self.exc


# In the following, self is in fact of type DSSimulation, but PyLance makes troubles with variable types
class SimProcessMixin:
    def schedule(self: DSSimulation, time: TimeType, schedulable: 'SchedulableType') -> 'SchedulableType':
        ''' Schedules generators, coroutines, and callables.
        Falls back to super().schedule() (SimScheduleMixin) for plain ISubscriber.
        '''
        if inspect.iscoroutine(schedulable) or inspect.isgenerator(schedulable):
            # Already-instantiated generator/coroutine
            process = DSProcess(schedulable, sim=self)
            process.schedule(time)
            return process
        elif isinstance(schedulable, DSProcess):
            # DSProcess uses its own schedule() which sets up the _Starter bootstrap
            schedulable.schedule(time)
            return schedulable
        elif isinstance(schedulable, ISubscriber):
            # Plain ISubscriber — deliver a None event at the scheduled time
            self.schedule_event(time, None, schedulable)
            return schedulable
        elif callable(schedulable):
            # Plain callable — wrap as a one-shot callback subscriber
            callback = DSCallback(schedulable, sim=self)
            self.schedule_event(time, None, callback)
            return callback
        raise ValueError(f'The provided schedulable {schedulable} is not supported.')

    def process(self: Any, *args: Any, **kwargs: Any) -> DSProcess:
        sim: DSSimulation = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in process() method should be set to the same simulation instance.')
        return DSProcess(*args, **kwargs, sim=sim)

    def gwait(self: Any, timeout: TimeType = float('inf'), cond: CondType = AlwaysFalse, val: EventRetType = True) -> Generator[EventType, EventType, EventType]:
        ''' Wait for an event from publisher for max. timeout time. The criteria which events to be
        accepted is given by cond. An accepted event returns from the wait function. An event which
        causes cond to be False is ignored and the function is waiting.
        '''
        retval = yield from self._parent_process.gwait(timeout, cond, val)
        return retval

    def check_and_gwait(self: Any, timeout: TimeType = float('inf'), cond: CondType = AlwaysFalse, val: EventRetType = True) -> Generator[EventType, EventType, EventType]:
        retval = yield from self._parent_process.check_and_gwait(timeout, cond, val)
        return retval

    async def wait(self: Any, timeout: TimeType = float('inf'), cond: CondType = AlwaysFalse, val: EventRetType = True) -> EventType:
        ''' Wait for an event from publisher for max. timeout time. The criteria which events to be
        accepted is given by cond. An accepted event returns from the wait function. An event which
        causes cond to be False is ignored and the function is waiting.
        '''
        retval = await self._parent_process.wait(timeout, cond, val)
        return retval

    async def check_and_wait(self: Any, timeout: TimeType = float('inf'), cond: CondType = AlwaysFalse, val: EventRetType = True) -> EventType:
        retval = await self._parent_process.check_and_wait(timeout, cond, val)
        return retval

    def observe_pre(self: Any, *components: Union[DSFuture, DSPub], **policy_params: Any) -> DSSubscriberContextManager:
        return DSSubscriberContextManager(self.pid, DSPub.Phase.PRE, components, **policy_params)

    def consume(self: Any, *components: Union[DSFuture, DSPub], **policy_params: Any) -> DSSubscriberContextManager:
        return DSSubscriberContextManager(self.pid, DSPub.Phase.CONSUME, components, **policy_params)

    def observe_consumed(self: Any, *components: Union[DSFuture, DSPub], **policy_params: Any) -> DSSubscriberContextManager:
        return DSSubscriberContextManager(self.pid, DSPub.Phase.POST_HIT, components, **policy_params)

    def observe_unconsumed(self: Any, *components: Union[DSFuture, DSPub], **policy_params: Any) -> DSSubscriberContextManager:
        return DSSubscriberContextManager(self.pid, DSPub.Phase.POST_MISS, components, **policy_params)

    @contextmanager
    def extend_cond(self: Any, cond: CondType) -> Iterator:
        conds = self.pid.meta.cond
        conds.push(cond)
        try:
            yield
        finally:
            conds.pop()

    @contextmanager
    def timeout(self: Any, time: TimeType) -> Iterator:
        exc = DSTimeoutContextError()
        cm = DSTimeoutContext(time, sim=self, exc=exc)
        try:
            yield cm
        except DSTimeoutContextError as e:
            if cm.exc is not e:
                raise
            cm.set_interrupted()
        finally:
            cm.cleanup()

    @contextmanager
    def interruptible(self: Any, cond: CondType = AlwaysFalse) -> Iterator:
        cm = DSInterruptibleContext(cond, sim=self)
        with self.extend_cond(cm.cond):
            try:
                yield cm
            except DSInterruptibleContextError as e:
                cm.set_interrupted(e.value)



class DSTimeoutContextError(Exception):
    pass


class DSInterruptibleContextError(Exception):
    def __init__(self, value: EventType, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.value = value


class DSSubscriberContextManager:
    def __init__(self, process: DSProcess, queue_id: DSPub.Phase, components: Tuple[Union[DSFuture, DSPub], ...], **kwargs: Any) -> None:
        self.process = process
        eps = set()
        for c in components:
            if isinstance(c, DSFuture):
                eps |= set(c.get_future_eps())
            else:  # component is DSPub
                eps.add(c)
        Phase = DSPub.Phase
        self.pre = eps if queue_id == Phase.PRE else set()
        self.consume = eps if queue_id == Phase.CONSUME else set()
        self.postp = eps if queue_id == Phase.POST_HIT else set()
        self.postn = eps if queue_id == Phase.POST_MISS else set()
        self.kwargs = kwargs

    def __enter__(self) -> "DSSubscriberContextManager":
        ''' Connects publisher endpoint with new subscriptions '''
        Phase = DSPub.Phase
        for publisher in self.pre:
            publisher.add_subscriber(self.process, Phase.PRE, **self.kwargs)
        for publisher in self.consume:
            publisher.add_subscriber(self.process, Phase.CONSUME, **self.kwargs)
        for publisher in self.postp:
            publisher.add_subscriber(self.process, Phase.POST_HIT, **self.kwargs)
        for publisher in self.postn:
            publisher.add_subscriber(self.process, Phase.POST_MISS, **self.kwargs)
        return self

    def __exit__(self, exc_type: Optional[type[Exception]], exc_value: Exception, tb: TracebackType) -> None:
        Phase = DSPub.Phase
        for publisher in self.pre:
            publisher.remove_subscriber(self.process, Phase.PRE, **self.kwargs)
        for publisher in self.consume:
            publisher.remove_subscriber(self.process, Phase.CONSUME, **self.kwargs)
        for publisher in self.postp:
            publisher.remove_subscriber(self.process, Phase.POST_HIT, **self.kwargs)
        for publisher in self.postn:
            publisher.remove_subscriber(self.process, Phase.POST_MISS, **self.kwargs)

    def __add__(self, other: "DSSubscriberContextManager") -> "DSSubscriberContextManager":
        self.pre = self.pre | other.pre
        self.consume = self.consume | other.consume
        self.postp = self.postp | other.postp
        self.postn = self.postn | other.postn
        return self


class DSTimeoutContext:
    def __init__(self, time: Optional[TimeType], exc: DSTimeoutContextError = DSTimeoutContextError(), *, sim: DSSimulation) -> None:
        self.sim = sim
        self.time = time
        self.exc = exc
        self._interrupted: bool = False
        if time is not None:
            self.sim.schedule_event(time, exc)

    def reschedule(self, time: TimeType) -> None:
        self.cleanup()
        self.time = time
        self.sim.schedule_event(time, self.exc)

    def cleanup(self) -> None:
        if self.time is not None:
            self.sim.time_queue.delete_val((self.sim.pid, self.exc))
    
    def set_interrupted(self) -> None:
        self._interrupted = True

    def interrupted(self) -> bool:
        return self._interrupted


class DSInterruptibleContext:
    def __init__(self, cond: CondType, *, sim: DSSimulation) -> None:
        self.sim = sim
        self.value: EventType = None
        self.cond = DSTransferableCondition(cond, transfer=lambda e: DSInterruptibleContextError(e))
        self._interrupted: bool = False

    def set_interrupted(self, value: EventType):
        self._interrupted = True
        self.value = value

    def interrupted(self) -> bool:
        return self._interrupted
