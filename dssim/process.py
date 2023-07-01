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
from typing import Any, Tuple, Union, Optional, Generator, Coroutine, Iterator, TYPE_CHECKING
from types import TracebackType
from contextlib import contextmanager
from functools import wraps
import inspect
from dssim.base import TimeType, EventType, EventRetType, CondType
from dssim.base import DSTransferableCondition, SignalMixin
from dssim.pubsub import ConsumerMetadata, TrackEvent
from dssim.future import DSFuture


if TYPE_CHECKING:
    from dssim.pubsub import DSProducer
    from dssim.simulation import DSSimulation, SchedulableType


class DSProcess(DSFuture, SignalMixin):
    ''' Typical task used in the simulations.
    This class "extends" generator / coroutine for additional info.
    The best practise is to use DSProcess instead of generators.
    '''
    class _ScheduleEvent: pass

    def __init__(self, generator: Union[Generator, Coroutine], *args: Any, **kwargs: Any) -> None:
        ''' Initializes DSProcess. The input has to be a generator function. '''
        self.generator = generator
        self._scheduled = False
        if self.started():  # check if the generator / coro has already been started...
            raise ValueError('The DSProcess can be used only on non-started generators / coroutines')
        super().__init__(*args, **kwargs)

    def create_metadata(self, **kwargs: Any) -> ConsumerMetadata:
        self.meta = ConsumerMetadata()
        return self.meta

    # TODO: this feature is not required
    def __iter__(self) -> "DSProcess":
        ''' Required to use the class to get events from it. '''
        return self

    def __next__(self) -> EventRetType:
        ''' Gets next state, without pushing any particular event. '''
        self.value = self.generator.send(None)
        return self.value

    @TrackEvent
    def send(self, event: EventType) -> EventRetType:
        ''' Pushes an event to the task and gets new state. '''
        if self.started():
            self.value = self.generator.send(event)
        else:
            self.get_cond().pop()  # for the first kick, we added temporarily "_ScheduleEvent" condition (see _schedule) 
            # By default, a future accepts timeout events (None) and events to self
            self.meta.cond.push(None)
            self.value = self.generator.send(None)
        return self.value

    def _schedule(self, time: TimeType) -> None:
        ''' This api is used with sim.schedule(...) '''
        if not self._scheduled:
            schedule_event = self._ScheduleEvent()
            self._scheduled = True
            self.get_cond().push(schedule_event)
            self.sim.schedule_event(time, schedule_event, self)

    def schedule(self, time: TimeType) -> DSProcess:
        ''' This api is to schedule directly task.schedule(...) '''
        return self.sim.schedule(time, self)
    
    def started(self) -> bool:
        if inspect.iscoroutine(self.generator):
            retval = inspect.getcoroutinestate(self.generator) != inspect.CORO_CREATED
        elif inspect.isgenerator(self.generator):
            retval = inspect.getgeneratorstate(self.generator) != inspect.GEN_CREATED
        else:
            raise ValueError(f'The assigned code {self.generator} to the process {self} is not generator, neither coroutine.')
        return retval

    def finished(self) -> bool:
        ''' The finished evaluation cannot be the same as with the Futures because a process
        changes its value / exc more times during its runtime.
        '''
        if inspect.iscoroutine(self.generator):
            retval = inspect.getcoroutinestate(self.generator) == inspect.CORO_CLOSED
        elif inspect.isgenerator(self.generator):
            retval = inspect.getgeneratorstate(self.generator) == inspect.GEN_CLOSED
        else:
            raise ValueError(f'The assigned code {self.generator} to the process {self} is not generator, neither coroutine.')
        return retval

    def finish(self, value: EventType) -> EventType:
        self.value = value
        self.sim.cleanup(self)
        # The last event is the process itself. This enables to wait for a process as an asyncio's Future 
        self._finish_tx.signal(self)
        return self.value
    
    def fail(self, exc: Exception) -> Exception:
        self.exc = exc
        self.sim.cleanup(self)
        self._finish_tx.signal(self)
        return self.exc
        

# In the following, self is in fact of type DSSimulation, but PyLance makes troubles with variable types
class SimProcessMixin:
    def process(self: Any, *args: Any, **kwargs: Any) -> DSProcess:
        sim: DSSimulation = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in process() method should be set to the same simulation instance.')
        return DSProcess(*args, **kwargs, sim=sim)

    def observe_pre(self: Any, *components: Union[DSFuture, DSProducer], **kwargs: Any) -> DSSubscriberContextManager:
        return DSSubscriberContextManager(self.pid, 'pre', components, **kwargs)

    def consume(self: Any, *components: Union[DSFuture, DSProducer], **kwargs: Any) -> DSSubscriberContextManager:
        return DSSubscriberContextManager(self.pid, 'act', components, **kwargs)

    def observe_consumed(self: Any, *components: Union[DSFuture, DSProducer], **kwargs: Any) -> DSSubscriberContextManager:
        return DSSubscriberContextManager(self.pid, 'post+', components, **kwargs)

    def observe_unconsumed(self: Any, *components: Union[DSFuture, DSProducer], **kwargs: Any) -> DSSubscriberContextManager:
        return DSSubscriberContextManager(self.pid, 'post-', components, **kwargs)

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
    def interruptible(self: Any, cond: CondType = lambda e: False) -> Iterator:
        cm = DSInterruptibleContext(cond, sim=self)
        with self.extend_cond(cm.cond):
            try:
                yield cm
            except DSInterruptibleContextError as e:
                cm.set_interrupted(e.value)


def DSSchedulable(api_func):
    ''' Decorator for schedulable functions / methods.
    DSSchedulable converts a function into a generator so it could be scheduled or
    used in DSProcess initializer.
    '''
    def _fcn_in_generator(*args: Any, **kwargs: Any) -> Iterator:
        if False:
            yield None  # dummy yield to make this to be generator
        return api_func(*args, **kwargs)
    
    @wraps(api_func)
    def scheduled_func(*args: Any, **kwargs: Any) -> Iterator:
        if inspect.isgeneratorfunction(api_func) or inspect.iscoroutinefunction(api_func):
            extended_gen = api_func(*args, **kwargs)
        else:
            extended_gen = _fcn_in_generator(*args, **kwargs)
        return extended_gen
    
    return scheduled_func


class DSTimeoutContextError(Exception):
    pass


class DSInterruptibleContextError(Exception):
    def __init__(self, value: EventType, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.value = value


class DSSubscriberContextManager:
    def __init__(self, process: DSProcess, queue_id: str, components: Tuple[Union[DSFuture, DSProducer], ...], **kwargs: Any) -> None:
        self.process = process
        eps = set()
        for c in components:
            if isinstance(c, DSFuture):
                eps |= set(c.get_future_eps())
            else:  # component is DSProducer
                eps.add(c)
        self.pre = eps if queue_id == 'pre' else set()
        self.act = eps if queue_id == 'act' else set()
        self.postp = eps if queue_id == 'post+' else set()
        self.postn = eps if queue_id == 'post-' else set()
        self.kwargs = kwargs

    def __enter__(self) -> "DSSubscriberContextManager":
        ''' Connects publisher endpoint with new subscriptions '''
        for producer in self.pre:
            producer.add_subscriber(self.process, 'pre', **self.kwargs)
        for producer in self.act:
            producer.add_subscriber(self.process, 'act', **self.kwargs)
        for producer in self.postp:
            producer.add_subscriber(self.process, 'post+', **self.kwargs)
        for producer in self.postn:
            producer.add_subscriber(self.process, 'post-', **self.kwargs)
        return self

    def __exit__(self, exc_type: Optional[type[Exception]], exc_value: Exception, tb: TracebackType) -> None:
        for producer in self.pre:
            producer.remove_subscriber(self.process, 'pre', **self.kwargs)
        for producer in self.act:
            producer.remove_subscriber(self.process, 'act', **self.kwargs)
        for producer in self.postp:
            producer.remove_subscriber(self.process, 'post+', **self.kwargs)
        for producer in self.postn:
            producer.remove_subscriber(self.process, 'post-', **self.kwargs)

    def __add__(self, other: "DSSubscriberContextManager") -> "DSSubscriberContextManager":
        self.pre = self.pre | other.pre
        self.act = self.act | other.act
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
            # We may compare also consumer, but
            # the context manager relies on the assumption that the
            # the exception object is allocated only once in the
            # timequeue.
            self.sim.delete(cond=lambda e: e[1] is self.exc)
    
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
