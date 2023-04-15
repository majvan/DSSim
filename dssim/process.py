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
from contextlib import contextmanager
from functools import wraps
import inspect
from dssim.base import DSTransferableCondition, SignalMixin, TrackEvent
from dssim.pubsub import ConsumerMetadata
from dssim.future import DSFuture


class DSTimeoutContextError(Exception):
    pass

class DSInterruptibleContextError(Exception):
    def __init__(self, value, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.value = value


class DSSubscriberContextManager:
    def __init__(self, process, queue_id, components, **kwargs):
        self.process = process
        eps = set()
        for c in components:
            if isinstance(c, DSFuture):
                eps |= set(c.get_future_eps())
            else:  # component is DSProducer
                eps.add(c)
        self.pre = eps if queue_id == 'pre' else set()
        self.act = eps if queue_id == 'act' else set()
        self.post = eps if queue_id == 'post' else set()
        self.kwargs = kwargs

    def __enter__(self):
        ''' Connects publisher endpoint with new subscriptions '''
        for producer in self.pre:
            producer.add_subscriber(self.process, 'pre', **self.kwargs)
        for producer in self.act:
            producer.add_subscriber(self.process, 'act', **self.kwargs)
        for producer in self.post:
            producer.add_subscriber(self.process, 'post', **self.kwargs)
        return self

    def __exit__(self, exc_type, exc_value, tb):
        for producer in self.pre:
            producer.remove_subscriber(self.process, 'pre', **self.kwargs)
        for producer in self.act:
            producer.remove_subscriber(self.process, 'act', **self.kwargs)
        for producer in self.post:
            producer.remove_subscriber(self.process, 'post', **self.kwargs)

    def __add__(self, other):
        self.pre = self.pre | other.pre
        self.act = self.act | other.act
        self.post = self.post | other.post
        return self


class DSTimeoutContext:
    def __init__(self, time, exc=DSTimeoutContextError(), *, sim):
        self.sim = sim
        self.time = time  # None or a value
        self.exc = exc
        self._interrupted = False
        if time is not None:
            self.sim.schedule_event(time, exc)

    def reschedule(self, time):
        self.cleanup()
        self.time = time
        self.sim.schedule_event(time, self.exc)

    def cleanup(self):
        if self.time is not None:
            # We may compare also self.parent_process, but
            # the context manager relies on the assumption that the
            # the exception object is allocated only once in the
            # timequeue.
            self.sim.delete(cond=lambda e: e[1] is self.exc)
    
    def set_interrupted(self):
        self._interrupted = True

    def interrupted(self):
        return self._interrupted


class DSInterruptibleContext:
    def __init__(self, cond, *, sim):
        self.sim = sim
        self.value = None
        self.cond = DSTransferableCondition(cond, transfer=lambda e: DSInterruptibleContextError(e))
        self._interrupted = False
        self.event = None

    def set_interrupted(self, value):
        self._interrupted = True
        self.value = value

    def interrupted(self):
        return self._interrupted


class DSProcess(DSFuture, SignalMixin):
    ''' Typical task used in the simulations.
    This class "extends" generator / coroutine for additional info.
    The best practise is to use DSProcess instead of generators.
    '''
    class _ScheduleEvent: pass

    def __init__(self, generator, *args, **kwargs):
        ''' Initializes DSProcess. The input has to be a generator function. '''
        self.generator = generator
        self.scheduled_generator = generator
        self._scheduled = False
        if self.started():  # check if the generator / coro has already been started...
            # TODO: if we want to support this use case, we should merge the metadata from the generator
            raise ValueError('The DSProcess can be used only on non-started generators / coroutines')
        super().__init__(*args, **kwargs)

    def create_metadata(self, **kwargs):
        self.meta = ConsumerMetadata()
        return self.meta

    def __iter__(self):
        ''' Required to use the class to get events from it. '''
        return self

    def __next__(self):
        ''' Gets next state, without pushing any particular event. '''
        self.value = self.scheduled_generator.send(None)
        return self.value

    @TrackEvent
    def send(self, event):
        ''' Pushes an event to the task and gets new state. '''
        if self.started():
            self.value = self.scheduled_generator.send(event)
        else:
            self.get_cond().pop()  # for the first kick, we added temoprarily "_ScheduleEvent" condition (see _schedule) 
            # By default, a future accepts timeout events (None) and events to self
            self.meta.cond.push(None)
            self.value = self.scheduled_generator.send(None)
        return self.value

    def _schedule(self, time):
        ''' This api is used with sim.schedule(...) '''
        if not self._scheduled:
            self._scheduled = self._ScheduleEvent()
            self.get_cond().push(self._scheduled)
            self.sim.schedule_event(time, self._scheduled, self)
            retval = self
        else:
            retval = None
        return retval

    def schedule(self, time):
        ''' This api is to schedule directly task.schedule(...) '''
        return self.sim.schedule(time, self)
    
    def started(self):
        if inspect.iscoroutine(self.scheduled_generator):
            retval = inspect.getcoroutinestate(self.scheduled_generator) != inspect.CORO_CREATED
        elif inspect.isgenerator(self.scheduled_generator):
            retval = inspect.getgeneratorstate(self.scheduled_generator) != inspect.GEN_CREATED
        else:
            raise ValueError(f'The assigned code {self.generator} to the process {self} is not generator, neither coroutine.')
        return retval

    def finished(self):
        ''' The finished evaluation cannot be the same as with the Futures because a process
        changes its value / exc more times during its runtime.
        '''
        if inspect.iscoroutine(self.scheduled_generator):
            retval = inspect.getcoroutinestate(self.scheduled_generator) == inspect.CORO_CLOSED
        elif inspect.isgenerator(self.scheduled_generator):
            retval = inspect.getgeneratorstate(self.scheduled_generator) == inspect.GEN_CLOSED
        else:
            raise ValueError(f'The assigned code {self.generator} to the process {self} is not generator, neither coroutine.')
        return retval

    def finish(self, value):
        self.value = value
        self.sim.cleanup(self)
        # The last event is the process itself. This enables to wait for a process as an asyncio's Future 
        self._finish_tx.signal(self)
        return self.value
    
    def fail(self, exc):
        self.exc = exc
        self.sim.cleanup(self)
        self._finish_tx.signal(self)
        

class SimProcessMixin:
    def observe_pre(self, *components, **kwargs):
        return DSSubscriberContextManager(self.parent_process, 'pre', components, **kwargs)

    def consume(self, *components, **kwargs):
        return DSSubscriberContextManager(self.parent_process, 'act', components, **kwargs)

    def observe_post(self, *components, **kwargs):
        return DSSubscriberContextManager(self.parent_process, 'post', components, **kwargs)
    
    @contextmanager
    def extend_cond(self, cond):
        conds = self.parent_process.meta.cond
        conds.push(cond)
        try:
            yield
        finally:
            conds.pop()

    @contextmanager
    def timeout(self, time):
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
    def interruptible(self, cond=lambda e: False):
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
    def _fcn_in_generator(*args, **kwargs):
        if False:
            yield None  # dummy yield to make this to be generator
        return api_func(*args, **kwargs)
    
    @wraps(api_func)
    def scheduled_func(*args, **kwargs):
        if inspect.isgeneratorfunction(api_func) or inspect.iscoroutinefunction(api_func):
            extended_gen = api_func(*args, **kwargs)
        else:
            extended_gen = _fcn_in_generator(*args, **kwargs)
        return extended_gen
    
    return scheduled_func


