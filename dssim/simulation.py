# Copyright 2020 NXP Semiconductors
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
The file provides basic logic to run the simulation and supported methods.
'''
import sys
from functools import wraps
from collections.abc import Iterable
import inspect
from dssim.timequeue import TimeQueue
from abc import abstractmethod
from contextlib import contextmanager


class DSTrackableEvent:
    def __init__(self, value):
        self.value = value
        self.producers = []

    def track(self, producer):
        self.producers.append(producer)

    def __repr__(self):
        return f'DSTrackableEvent({self.value})'


def TrackEvent(fcn):
    def api(self, event, *args, **kwargs):
        if isinstance(event, DSTrackableEvent):
            event.producers.append(self)
        return fcn(self, event, *args, **kwargs)
    return api

class DSAbortException(Exception):
    ''' Exception used to abort waiting process '''

    def __init__(self, producer=None, **info):
        super().__init__()
        self.producer = producer
        self.info = info


class DSTimeoutContextError(Exception):
    pass


class DSInterruptibleContextError(Exception):
    def __init__(self, value, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.value = value


class DSAbsTime:
    def __init__(self, value):
        self.value = value


class _Awaitable:
    def __init__(self, val=None):
        self.val = val

    def __await__(self):
        retval = yield self.val
        return retval

class ICondition:
    def check(self): pass


class DSTransferableCondition(ICondition):
    def __init__(self, cond, transfer=lambda e:e):
        self.cond = StackedCond().push(cond)
        self.transfer = transfer
        self.value = None

    def check(self, value):
        signaled, retval = self.cond.check(value)
        if signaled:
            retval = self.transfer(retval)
        return signaled, retval


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


class StackedCond(ICondition):
    def __init__(self):
        self.conds = []
        self.value = None

    def push(self, cond):
        self.conds.append(cond)
        return self

    def pop(self):
        return self.conds.pop()

    def check_one(self, cond, event):
        ''' Returns pair of info ("event passing", "value of event") '''
        # Check the event first
        # Instead of the following generic rule, it is better to add it as a stacked condition
        # for "None" value, it will be caught later by cond == event rule.
        # if event is None:  # timeout received
        #     return True, None
        if isinstance(event, Exception):  # any exception raised
            return True, event
        # Check the type of condition
        if cond == event:  # we are expecting exact event and it came
            return True, event
        elif isinstance(cond, ICondition):
            return cond.check(event)
        elif callable(cond) and cond(event):  # there was a filter function set and the condition is met
            return True, event
        else:  # the event does not match our condition and hence will be ignored
            return False, None
    
    def check(self, event):
        signaled, retval = None, event
        for cond in self.conds:
            signaled, event = self.check_one(cond, retval)
            if signaled:
                if hasattr(cond, 'cond_value'):
                    retval = cond.cond_value()
                else:
                    retval = event
                self.value = retval
                break
        return signaled, retval

    def cond_value(self):
        return self.value


class _ConsumerMetadata:
    def __init__(self):
        self.cond = StackedCond()


class SignalMixin:
    def signal(self, event):
        ''' Signal event. '''
        return self.sim.signal(self, event)

    def signal_kw(self, **event):
        ''' Signal key-value event type as kwargs. '''
        return self.sim.signal(self, event)

    def schedule_event(self, time, event):
        ''' Signal event later. '''
        return self.sim.schedule_event(time, event, self)

    def schedule_kw_event(self, time, **event):
        ''' Signal event later. '''
        return self.sim.schedule_event(time, event, self)


class DSSimulation:
    ''' The simulation is a which schedules the nearest (in time) events. '''
    sim_singleton = None

    class _TestObject:
        ''' An artificial object to be used for check_and_wait- see description of the method '''
        pass

    def __init__(self, name='dssim', single_instance=True):
        ''' The simulation holds the list of producers which share the same time queue.
        The list is only for the application informational purpose to be able to identify
        all the producers which belong to the same simulation entity.
        '''
        self.name = name
        self._restart(time=0)
        if DSSimulation.sim_singleton is None:
            DSSimulation.sim_singleton = self  # The first sim environment will be the first initialized one
        elif not single_instance:
            print('Warning, you are initializing another instance of the simulation.'
                  'This case is supported, but it is not a typical case and you may'
                  'want not intentionally to do so. To suppress this warning, call'
                  'DSSimulation(single_instance=False)')

    def __repr__(self):
        return self.name

    def __str__(self):
        return self.name

    def restart(self, time=0):
        self._restart(time=time)

    def _restart(self, time):
        self.time_queue = TimeQueue()
        self.num_events = 0
        self.time = time
        self.parent_process = None

    def _compute_time(self, time):
        ''' Recomputes a rel/abs time to absolute time value '''
        if isinstance(time, DSAbsTime):
            time = time.value
            if time < self.time:
                raise ValueError('The time is absolute and cannot be lower than now')
        elif time < 0:
            raise ValueError('The time is relative from now and cannot be negative')
        else:
            time += self.time
        return time

    def delete(self, cond):
        ''' An interface method to delete events on the queue '''
        self.time_queue.delete(cond)

    def schedule(self, time, schedulable):
        ''' Schedules the start of a (new) process. '''
        if isinstance(schedulable, DSConsumer):
            process = schedulable
        elif inspect.iscoroutine(schedulable) or inspect.isgenerator(schedulable):
            process = DSProcess(schedulable, sim=self)
        elif callable(schedulable):
            process = DSCallback(schedulable, sim=self)
        else:
            raise ValueError(f'The provided function {schedulable} is probably missing @DSSchedulable decorator')
        if time < 0:
            raise ValueError('The time is relative from now and cannot be negative')
        if hasattr(process, '_schedule'):
            process._schedule(time)
        else:
            self.schedule_event(time, None, process)
        return process

    def check_condition(self, consumer, event):
        conds = consumer.get_cond()
        return conds.check(event)

    def send_object(self, consumer, event):
        ''' Send an event object to a consumer '''

        retval = False

        # We want to kick from this process to another process (see below). However, after
        # returning back to this process, we want to renew our process ID back to be used.
        # We do that by remembering the pid here and restoring at the end.
        pid = self.parent_process

        try:
            # We want to kick from this process another 'consumer' process. So we will change
            # the process ID (we call it self.parent_process). This is needed because if the new
            # created process would schedule a wait cycle for his own, he would like to know his own
            # process ID (see the wait method). That's why we have to set him his PID now.
            # In other words, the consumer.send() can invoke a context switch
            # without a handler- so this is the context switch handler, currently only
            # changing process ID.
            self.parent_process = consumer
            retval = consumer.send(event)
        except StopIteration as exc:
            if isinstance(consumer, DSFuture):
                retval = consumer.finish(exc.value)
            else:
                retval = exc.value
            self.cleanup(consumer)
        except ValueError as exc:
            if isinstance(consumer, DSFuture):
                retval = consumer.fail(exc)
            global _exiting
            if 'generator already executing' in str(exc) and not _exiting:
                _exiting = True
                print_cyclic_signal_exception(exc)
            raise
        finally:
            self.parent_process = pid
        return retval

    def try_send(self, consumer, event):
        ''' Send an event object to a consumer process. Convert event from parameters to object. '''

        # We will be sending signal (event) to a consumer, which has some condition set
        # upon waiting for a pattern event.
        # The idea is that the consumer will get the event only if the condition is met-
        # an early check.
        signaled, event = self.check_condition(consumer, event)
        if not signaled:
            return False  # not signalled
        retval = self.send_object(consumer, event)
        return retval

    def signal(self, process, event, time=0):
        ''' Schedules an event object into timequeue. Finally the target process will be signalled. '''
        time = self._compute_time(time)
        consumer = process if process is not None else self.parent_process  # schedule to a process or to itself
        self.time_queue.add_element(time, (consumer, event))
        return event

    def schedule_event(self, time, event, consumer=None):
        ''' Schedules an event object into timequeue. Finally the target process will be signalled. '''
        time = self._compute_time(time)
        consumer = consumer or self.parent_process  # schedule to a process or to itself
        self.time_queue.add_element(time, (consumer, event))
        return event

    def _gwait_for_event(self, timeout, val=None):
        # Re-compute abs/relative time to abs for the timeout
        time = self._compute_time(timeout)
        # Schedule the timeout to the time queue. The condition is only for higher performance
        if time != float('inf'):
            self.time_queue.add_element(time, (self.parent_process, None))
        try:
            event = True
            # Pass value to the feeder and wait for next event
            event = yield val
            # We received an event. In the lazy evaluation case, we would be now calling
            # _check_cond and returning or raising an event only if the condition matches,
            # otherwise we would be waiting in an infinite loop here.
            # However we do an early evaluation of conditions- they are checked before
            # calling send_object and we know that the conditions to return (or to raise an
            # exception) are satisfied. See the code there for more info.

            # Convert exception signal to a real exception
            if isinstance(event, Exception):
                raise event
        finally:
            if event is not None and time != float('inf'):
                # If we terminated before timeout and the timeout event is on time queue- remove it
                self.delete(lambda e: e == (self.parent_process, None))
        return event

    def gwait(self, timeout=float('inf'), cond=lambda e: False, val=True):
        ''' Wait for an event from producer for max. timeout time. The criteria which events to be
        accepted is given by cond. An accepted event returns from the wait function. An event which
        causes cond to be False is ignored and the function is waiting.
        '''

        # Get from simulation the current process ID. The current process ID is the ID of
        # the process which is parent - the most highest one in the yield stack structure.
        # With such process the scheduler on timeout will kick the parent process,
        # not a locally yield-ing subprocess.
        # The reason why it is important is that if scheduler kicked the subprocess's
        # _wait_for_event method, the return from the subprocess would not defer here, but rather
        # just ended and disappeared in scheduler. But we need that the scheduler is said to plan
        # another timeout for this process.
        conds = self.parent_process.meta.cond
        # Set the condition object (lambda / object / ...) in the process metadata
        conds.push(cond)
        try:
            event = yield from self._gwait_for_event(timeout, val)
        finally:
            conds.pop()
        if hasattr(cond, 'cond_value'):
            event = cond.cond_value()
        return event

    def check_and_gwait(self, timeout=float('inf'), cond=lambda e: False, val=True):
        # This function can be used to run a pre-check for such conditions, which are
        # invariant to the passed event, for instance to check for a state of an object
        # so if the state matches, it returns immediately
        # Otherwise it jumps to the waiting process.
        conds = self.parent_process.meta.cond
        # Set the condition object (lambda / object / ...) in the process metadata
        conds.push(cond)
        try:
            signaled, event = conds.check(self._TestObject())
            if not signaled:
                event = yield from self._gwait_for_event(timeout, val)
            else:
                event = conds.cond_value()
        finally:
            conds.pop()
        return event

    async def _wait_for_event(self, timeout, val=None):
        # Re-compute abs/relative time to abs for the timeout
        time = self._compute_time(timeout)
        # Schedule the timeout to the time queue. The condition is only for higher performance
        if time != float('inf'):
            self.time_queue.add_element(time, (self.parent_process, None))
        try:
            event = True
            # Pass value to the feeder and wait for next event
            event = await _Awaitable(val)
            # We received an event. In the lazy evaluation case, we would be now calling
            # _check_cond and returning or raising an event only if the condition matches,
            # otherwise we would be waiting in an infinite loop here.
            # However we do an early evaluation of conditions- they are checked before
            # calling send_object and we know that the conditions to return (or to raise an
            # exception) are satisfied. See the code there for more info.

            # Convert exception signal to a real exception
            if isinstance(event, Exception):
                raise event
        finally:
            if event is not None and time != float('inf'):
                # If we terminated before timeout and the timeout event is on time queue- remove it
                self.delete(lambda e: e == (self.parent_process, None))
        return event

    async def wait(self, timeout=float('inf'), cond=lambda e: False, val=True):
        ''' Wait for an event from producer for max. timeout time. The criteria which events to be
        accepted is given by cond. An accepted event returns from the wait function. An event which
        causes cond to be False is ignored and the function is waiting.
        '''

        # Get from simulation the current process ID. The current process ID is the ID of
        # the process which is parent - the most highest one in the yield stack structure.
        # With such process the scheduler on timeout will kick the parent process,
        # not a locally yield-ing subprocess.
        # The reason why it is important is that if scheduler kicked the subprocess's
        # _wait_for_event method, the return from the subprocess would not defer here, but rather
        # just ended and disappeared in scheduler. But we need that the scheduler is said to plan
        # another timeout for this process.
        conds = self.parent_process.meta.cond
        # Set the condition object (lambda / object / ...) in the process metadata
        conds.push(cond)
        try:
            event = await self._wait_for_event(timeout, val)
        finally:
            conds.pop()
        if hasattr(cond, 'cond_value'):
            event = cond.cond_value()
        return event

    async def check_and_wait(self, timeout=float('inf'), cond=lambda e: False, val=True):
        # This function can be used to run a pre-check for such conditions, which are
        # invariant to the passed event, for instance to check for a state of an object
        # so if the state matches, it returns immediately
        # Otherwise it jumps to the waiting process.
        conds = self.parent_process.meta.cond
        # Set the condition object (lambda / object / ...) in the process metadata
        conds.push(cond)
        try:
            signaled, event = conds.check(self._TestObject())
            if not signaled:
                event = await self._wait_for_event(timeout, val)
            else:
                event = conds.cond_value()
        finally:
            conds.pop()
        return event

    def cleanup(self, consumer):
        # The consumer has finished.
        # We make a cleanup of a waitable condition. There is still waitable condition kept
        # for the consumer. Since the process has finished, it will never need it, however
        # there may be events for the process planned.
        # Remove the condition
        meta = consumer.meta
        meta.cond = StackedCond()
        # Remove all the events for this consumer
        self.time_queue.delete(lambda e:e[0] is consumer)

    def run(self, up_to=None, future=object()):
        ''' This is the simulation machine. In a loop it takes first event and process it.
        The loop ends when the queue is empty or when the simulation time is over.
        '''
        if up_to is None:
            up_to = float('inf')
        while len(self.time_queue) > 0:
            # Get the first event on the queue
            tevent, (consumer, event_obj) = self.time_queue.get0()
            if tevent >= up_to:
                retval_time = self.time
                self.time = up_to
                break
            if event_obj == future:
                retval_time = self.time
                break
            self.num_events += 1
            self.time = tevent
            self.time_queue.pop()
            self.try_send(consumer, event_obj)
        else:
            retval_time = self.time
            self.time = up_to
        return retval_time, self.num_events

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


class DSComponent:
    ''' DSComponent is any component which uses simulation (sim) environment.
    The component shall have assigned a simulation instance (useful when
    creating more simulation instances in one application).
    If the sim instance is not specified, the one from singleton will be assigned.

    The interface has a rule that every instance shall have a (unique) name
    (useful for debugging when debugger displays interface name).
    If the name is not specified, it is created from the simulation instance
    and class name.
    '''
    def __init__(self, *args, name=None, sim=None, **kwargs):
        # It is recommended that core components specify the sim argument, i.e. sim should not be None
        self.sim = sim or DSSimulation.sim_singleton
        if not isinstance(getattr(self.sim, 'names', None), dict):
            self.sim.names = {}
        temp_name = name or f'{self.__class__}'
        if self.sim is None:
            raise ValueError(f'Interface {temp_name} does not have sim parameter set and no DSSimulation was created yet.')
        if name is None:
            name = temp_name
            counter = self.sim.names.get(name, 0)
            self.sim.names[name] = counter + 1
            name = name + f'{counter}'
        elif name in self.sim.names:
            raise ValueError(f'Interface with name {name} already registered in the simulation instance {self.sim.name}.')
        else:
            self.sim.names[name] = 0
        self.name = name

    def __repr__(self):
        return self.name


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


class DSConsumer(DSComponent):
    def __init__(self, *args, **kwargs):
        super().__init__(self, *args, **kwargs)
        self.create_metadata(**kwargs)
       
    def create_metadata(self, **kwargs):
        self.meta = _ConsumerMetadata()
        if 'cond' in kwargs:
            self.meta.cond.push(kwargs['cond'])
        return self.meta

    def get_cond(self):
        return self.meta.cond

    @TrackEvent
    @abstractmethod
    def send(self, event):
        ''' Receive event. This interface should be used only by DSSimulator instance as
        the main dispatcher for directly sending messages.
        Bypassing DSSimulator by calling the consumer send() directly would bypass the
        condition check and could also result into dependency issues.
        The name 'send' is required as python's generator.send() is de-facto consumer, too.
        '''
        raise NotImplementedError('Abstract method, use derived classes')


class DSCallback(DSConsumer):
    ''' A callback interface.
    The callback interface is called from the simulator when a process sends events.
    '''
    def __init__(self, forward_method, cond=lambda e: True, **kwargs):
        super().__init__(cond=cond, **kwargs)
        # TODO: check if forward method is not a generator / process; otherwise throw an error
        self.forward_method = forward_method

    @TrackEvent
    def send(self, event):
        ''' The function calls the registered callback. '''
        retval = self.forward_method(event)
        return retval


class DSKWCallback(DSCallback):

    @TrackEvent
    def send(self, event):
        ''' The function calls registered callback providing that the event is dict. '''
        retval = self.forward_method(**event)
        return retval

from dssim.pubsub import DSProducer

class DSFuture(DSConsumer, SignalMixin):
    ''' Typical future which can be used in the simulations.
    This represents a base for all awaitables.
    '''
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # We store the latest value or excpetion. Useful to check the status after finish.
        self.value, self.exc = None, None
        self._finish_tx = DSProducer(name=self.name+'.future', sim=self.sim)
    
    def create_metadata(self, **kwargs):
        self.meta = _ConsumerMetadata()
        self.meta.cond.push(self)  # sending to self => signaling the end of future
        return self.meta

    def get_future_eps(self):
        return {self._finish_tx,}

    def finished(self):
        return (self.value, self.exc) != (None, None)

    def abort(self, exc=None):
        ''' Aborts an awaitable with an exception. '''
        if exc is None:
            exc = DSAbortException(self)
        try:
            self.sim.try_send(self, exc)
        except StopIteration as e:
            self.finish(e)
        except Exception as e:
            self.fail(e)

    def gwait(self, timeout=float('inf')):
        retval = None
        if not self.finished():
            with self.sim.observe_pre(self):
                retval = yield from self.sim.gwait(timeout, cond=self)
        if self.exc is not None:
            raise self.exc
        return retval

    async def wait(self, timeout=float('inf')):
        retval = None
        if not self.finished():
            with self.sim.observe_pre(self):
                retval = await self.sim.wait(timeout, cond=self)
        if self.exc is not None:
            raise self.exc
        return retval

    def __await__(self):
        retval = yield from self.gwait()
        return retval

    def finish(self, value):
        self.value = value
        self.sim.cleanup(self)
        self._finish_tx.signal(self)
    
    def fail(self, exc):
        self.exc = exc
        self.sim.cleanup(self)
        self._finish_tx.signal(self)

    @TrackEvent
    def send(self, event):
        self.finish(event)
        return event


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
        self.meta = _ConsumerMetadata()
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
        

class DSExceptionContextManager:
    ''' This class is used to be able to schedule exception (i.e. timeout exc).
    in a context code so it could then exit the context.
    '''

_exiting = False  # global var to prevent repeating nested exception frames

def print_cyclic_signal_exception(exc):
    ''' The function prints out detailed information about frame stack related
    to the simulation process, filtering out unnecessary info.
    '''
    exc_type, exc_value, exc_traceback = sys.exc_info()
    print('Error:', exc)
    print('\nAn already running schedulable (DSProcess / generator) hedule_was\n'
          'signalled and therefore Python cannot handle such state.\n'
          'There are two possible solutions for this issue:\n'
          '1. You rewrite the code to remove cyclic signalling of processes.\n'
          '   This is recommended at least to try because this issue might\n'
          '   signify a real design flaw in the simulation / implementation.\n'
          '2. Instead of calling sim.send(process, event)\n'
          '   you schedule the event into the queue with zero delta time.\n'
          '   Example of the modification:\n'
          '   Previous code:\n'
          '   sim.send(process, status="Ok")\n'
          '   New code:\n'
          '   sim.signal({"status": "Ok"}, process)\n\n'
          '   Possibly, you used send() method on a component. Consider using\n'
          '   signal() instead on the component.\n\n')
    while True:
        if not exc_traceback.tb_next:
            break
        exc_traceback = exc_traceback.tb_next
    stack, process_stack = [], []
    f = exc_traceback.tb_frame
    while f:
        stack.append(f)
        f = f.f_back
    stack.reverse()
    to_process = None
    for frame in stack:
        if frame.f_code.co_filename != __file__:
            method = frame.f_code.co_name
            line = frame.f_lineno
            filename = frame.f_code.co_filename
        elif frame.f_code.co_name == 'send_object':
            from_process = frame.f_locals['pid']
            to_process = frame.f_locals['consumer']
            event = frame.f_locals['event']
            d = [method, line, filename, from_process, to_process, event, False, False]
            process_stack.append(d)
    # search for the processes to highlight (highlight the loop conflict)
    if not to_process:
        return
    print('Signal stack:')
    conflicting_process = to_process
    for frame in reversed(process_stack):
        if frame[3] == conflicting_process:
            frame[-2] = True  # mark the last from_process which needs to be highlighted
            break
    process_stack[-1][-1] = True # mark the last to_process which needs to be highlighted
    for frame in process_stack:
           method, line, filename, from_process, to_process, event, from_c, to_c = frame
           print(f'{method} in {filename}:{line}')
           if from_c:
               print(f'  From:  \033[0;31m{from_process}\033[0m')
           else:
               print(f'  From:  {from_process}')
           if to_c:
               print(f'  To:    \033[0;31m{to_process}\033[0m')
           else:
               print(f'  To:    {to_process}')
           print(f'  Event: {event}')
    print()
