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


class DSAbortException(Exception):
    ''' Exception used to abort waiting process '''

    def __init__(self, producer=None, **info):
        super().__init__()
        self.producer = producer
        self.info = info


class DSTimeoutContextError(Exception):
    pass


class DSAbsTime:
    def __init__(self, value):
        self.value = value

class Awaitable:
    def __init__(self, val=None):
        self.val = val

    def __await__(self):
        retval = yield self.val
        return retval


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


class DSInterruptibleContext:
    def __init__(self, time, exc=None, *, sim):
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


class _StackedCond:
    def __init__(self):
        self.conds = []

    def push(self, cond):
        self.conds.append(cond)

    def pop(self):
        self.conds.pop()

    def check_always(self, event):
        ''' Returns pair of info ("event passing", "value of event") '''
        # Check the event first
        if event is None:  # timeout received
            return True, None
        elif isinstance(event, Exception):  # any exception raised
            return True, event
        else:  # the event does not match our condition
            return False, None

    def check_one(self, cond, event):
        ''' Returns pair of info ("event passing", "value of event") '''
        # Check the type of condition
        if cond == event:  # we are expecting exact event and it came
            return True, event
        elif callable(cond) and cond(event):  # there was a filter function set and the condition is met
            return True, event
        else:  # the event does not match our condition and hence will be ignored
            return False, None
    
    def check(self, event):
        signaled, retval = self.check_always(event)
        if signaled:
            return signaled, retval
        for cond in reversed(self.conds):
            signaled, retval = self.check_one(cond, event)
            if signaled:
                break
        return signaled, retval


class _ConsumerMetadata:
    def __init__(self):
        self.cond = _StackedCond()


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


class ICondition:
    @abstractmethod
    def cond_value(self, event):
        return event


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
        self._consumer_metadata = {}
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

    def create_metadata(self, process):
        if hasattr(process, 'create_metadata'):
            meta = process.create_metadata()
        else:
            meta = _ConsumerMetadata()
            self._consumer_metadata[process] = meta
        return meta

    def get_consumer_metadata(self, process):
        retval = getattr(process, 'meta', None)
        if not retval:
            retval = self._consumer_metadata.get(process, None)
            retval = retval or self.create_metadata(process)
        return retval

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
        if not isinstance(schedulable, Iterable) and not inspect.iscoroutine(schedulable):
            raise ValueError('The provided function is probably missing @DSSchedulable decorator')
        if time < 0:
            raise ValueError('The time is relative from now and cannot be negative')
        # Create a new process which at the beginning waits (see _scheduled_fcn method) and
        # then start it.
        # This method was probably called by another scheduled process.
        # However to kick a new process, we just setup a new process ID to the simulation,
        # kick the process and then set back for the simulation the previous process ID.
        old_process = self.parent_process

        if hasattr(schedulable, '_schedule'):
            new_process = schedulable._schedule(time)
        elif inspect.iscoroutine(schedulable):
            new_process = self._scheduled_fcn(time, schedulable)
        elif inspect.isgenerator(schedulable):
            new_process = self._scheduled_gfcn(time, schedulable)
        else:
            raise ValueError(f'The assigned code {schedulable} is not generator, neither coroutine.')
        self.parent_process = new_process
        # The following will change the process default metadata cond
        self._kick(new_process)
        # Restore the default metadata cond by creating a new default one.
        # It is useful for processes which will not use await sim.wait(...)
        self.create_metadata(new_process)

        self.parent_process = old_process
        return new_process

    def check_condition(self, schedulable, event):
        conds = self.get_consumer_metadata(schedulable).cond
        retval, event = conds.check(event)
        return retval

    def send_object(self, schedulable, event):
        ''' Send an event object to a schedulable consumer '''

        retval = False

        # We want to kick from this process to another process (see below). However, after
        # returning back to this process, we want to renew our process ID back to be used.
        # We do that by remembering the pid here and restoring at the end.
        pid = self.parent_process

        try:
            # We want to kick from this process another 'schedulable' process. So we will change
            # the process ID (we call it self.parent_process). This is needed because if the new
            # created process would schedule a wait cycle for his own, he would like to know his own
            # process ID (see the wait method). That's why we have to set him his PID now.
            # In other words, the schedulable.send() will invoke a context switch
            # without a handler- so this is the context switch handler, currently only
            # changing process ID.
            self.parent_process = schedulable
            retval = schedulable.send(event)
        except StopIteration as exc:
            if isinstance(schedulable, DSFuture):
                retval = schedulable.finish(exc.value)
            else:
                retval = exc.value
                self.cleanup(schedulable)
        except ValueError as exc:
            if isinstance(schedulable, DSFuture):
                retval = schedulable.fail(exc)
            global _exiting
            if 'generator already executing' in str(exc) and not _exiting:
                _exiting = True
                print_cyclic_signal_exception(exc)
            raise
        finally:
            self.parent_process = pid
        return retval

    def send(self, schedulable, event):
        ''' Send an event object to a consumer process. Convert event from parameters to object. '''

        # We will be sending signal (event) to a schedulable, which has some condition set
        # upon waiting for a pattern event.
        # We do it early in order to know if the schedulable is going to reject the event or
        # not. The information from accepting / rejecting the event gives us valuable info.
        # pre_check means that the check of condition for the schedulable was already done
        if not self.check_condition(schedulable, event):
            return False  # not signalled
        retval = self.send_object(schedulable, event)
        return retval

    def abort(self, schedulable, **info):
        ''' Send abort exception to a consumer process. Convert event from parameters to object. '''
        self.send_object(schedulable, DSAbortException(self.parent_process, **info))

    def signal(self, process, event, time=0):
        ''' Schedules an event object into timequeue. Finally the target process will be signalled. '''
        time = self._compute_time(time)
        consumer = process if process is not None else self.parent_process  # schedule to a process or to itself
        self.time_queue.add_element(time, (consumer, event))
        return event

    def schedule_event(self, time, event, process=None):
        ''' Schedules an event object into timequeue. Finally the target process will be signalled. '''
        time = self._compute_time(time)
        consumer = process or self.parent_process  # schedule to a process or to itself
        self.time_queue.add_element(time, (consumer, event))
        return event


    async def _scheduled_fcn(self, time, schedulable):
        ''' Start a schedulable process with possible delay '''
        try:
            await self.wait(time)
        except DSAbortException as exc:
            return
        retval = await schedulable
        return retval

    def _scheduled_gfcn(self, time, schedulable):
        ''' Start a schedulable process with possible delay '''
        try:
            yield from self.gwait(time)
        except DSAbortException as exc:
            return
        retval = yield from schedulable
        return retval

    def _gwait_for_event(self, timeout, val=None):
        # Re-compute abs/relative time to abs for the timeout
        time = self._compute_time(timeout)
        # Schedule the timeout to the time queue. The condition is only for higher performance
        if time != float('inf'):
            self.time_queue.add_element(time, (self.parent_process, None))
        try:
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
        except Exception as exc:
            # If we got any exception, we will not use the other events anymore
            self.delete(lambda e: e == (self.parent_process, None))
            raise
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
        conds = self.get_consumer_metadata(self.parent_process).cond
        # Set the condition object (lambda / object / ...) in the process metadata
        conds.push(cond)
        event = yield from self._gwait_for_event(timeout, val)
        # Remove the last condition
        conds.pop()
        if hasattr(cond, 'cond_value'):
            event = cond.cond_value(event)
        return event

    def check_and_gwait(self, timeout=float('inf'), cond=lambda e: False, val=True):
        # This function can be used to run a pre-check for such conditions, which are
        # invariant to the passed event, for instance to check for a state of an object
        # so if the state matches, it returns immediately
        # Otherwise it jumps to the waiting process.
        conds = self.get_consumer_metadata(self.parent_process).cond
        # Set the condition object (lambda / object / ...) in the process metadata
        conds.push(cond)
        _, event = conds.check(self._TestObject())
        if not event:
            event = yield from self._gwait_for_event(timeout, val)
        if hasattr(cond, 'cond_value'):
            event = cond.cond_value(event)
        conds.pop()
        return event

    async def _wait_for_event(self, timeout, val=None):
        # Re-compute abs/relative time to abs for the timeout
        time = self._compute_time(timeout)
        # Schedule the timeout to the time queue. The condition is only for higher performance
        if time != float('inf'):
            self.time_queue.add_element(time, (self.parent_process, None))
        try:
            # Pass value to the feeder and wait for next event
            event = await Awaitable(val)
            # We received an event. In the lazy evaluation case, we would be now calling
            # _check_cond and returning or raising an event only if the condition matches,
            # otherwise we would be waiting in an infinite loop here.
            # However we do an early evaluation of conditions- they are checked before
            # calling send_object and we know that the conditions to return (or to raise an
            # exception) are satisfied. See the code there for more info.

            # Convert exception signal to a real exception
            if isinstance(event, Exception):
                raise event
        except Exception as exc:
            # If we got any exception, we will not use the other events anymore
            self.delete(lambda e: e == (self.parent_process, None))
            raise
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
        conds = self.get_consumer_metadata(self.parent_process).cond
        # Set the condition object (lambda / object / ...) in the process metadata
        conds.push(cond)
        event = await self._wait_for_event(timeout, val)
        # Remove the last condition
        conds.pop()
        if hasattr(cond, 'cond_value'):
            event = cond.cond_value(event)
        return event

    async def check_and_wait(self, timeout=float('inf'), cond=lambda e: False, val=True):
        # This function can be used to run a pre-check for such conditions, which are
        # invariant to the passed event, for instance to check for a state of an object
        # so if the state matches, it returns immediately
        # Otherwise it jumps to the waiting process.
        conds = self.get_consumer_metadata(self.parent_process).cond
        # Set the condition object (lambda / object / ...) in the process metadata
        conds.push(cond)
        _, event = conds.check(self._TestObject())
        if not event:
            event = await self._wait_for_event(timeout, val)
        if hasattr(cond, 'cond_value'):
            event = cond.cond_value(event)
        conds.pop()
        return event

    def _kick(self, schedulable):
        ''' Provides first kick (run) of a schedulable process. '''
        try:
            schedulable.send(None)  # next() would be enough for generators, but not for coroutines
        except StopIteration as exp:
            pass

    def cleanup(self, schedulable):
        # The schedulable has finished and is not waiting anymore.
        # We make a cleanup of a waitable condition. There is still waitable condition kept
        # for the schedulable. Since the process has finished, it will never need it, however
        # there may be events for the process planned.
        # Remove the condition
        meta = self.get_consumer_metadata(schedulable)
        meta.cond = _StackedCond()
        # Remove all the events for this schedulable
        self.time_queue.delete(lambda e:e[0] is schedulable)

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
            self.send(consumer, event_obj)
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
        conds = self.get_consumer_metadata(self.parent_process).cond
        conds.push(cond)
        try:
            yield
        finally:
            conds.pop()

    @contextmanager
    def interruptible(self, time, cond=lambda e: False):
        with self.extend_cond(cond):
            exc = DSTimeoutContextError()
            cm = DSInterruptibleContext(time, sim=self, exc=exc)
            try:
                yield cm
            except DSTimeoutContextError as e:
                if cm.exc is not e:
                    raise
                cm.set_interrupted()
            finally:
                cm.cleanup()


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
        self.create_metadata()
       
    def create_metadata(self):
        self.meta = _ConsumerMetadata()
        return self.meta

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
        super().__init__(**kwargs)
        # TODO: check if forward method is not a generator / process; otherwise throw an error
        self.forward_method = forward_method

    def create_metadata(self):
        self.meta = _ConsumerMetadata()
        self.meta.cond.push(lambda e:True)
        return

    def send(self, event):
        ''' The function calls the registered callback. '''
        retval = self.forward_method(event)
        return retval


class DSKWCallback(DSCallback):

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
    
    def create_metadata(self):
        self.meta = _ConsumerMetadata()
        # By default, a future accepts event from self
        self.meta.cond.push(self)
        return self.meta

    def get_future_eps(self):
        return {self._finish_tx,}

    def finished(self):
        return (self.value, self.exc) != (None, None)

    def abort(self, exc=None):
        ''' Aborts an awaitable with an exception. '''
        if exc is None:
            exc = DSAbortException(self.sim.parent_process)
        try:
            self.send(exc)
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

    def send(self, event):
        self.finish(event)
        return event


class DSProcess(DSFuture, SignalMixin):
    ''' Typical task used in the simulations.
    This class "extends" generator / coroutine for additional info.
    The best practise is to use DSProcess instead of generators.
    '''
    def __init__(self, generator, *args, **kwargs):
        ''' Initializes DSProcess. The input has to be a generator function. '''
        self.generator = generator
        self.scheduled_generator = generator
        if self.started():  # check if the generator / coro has already been started...
            # TODO: if we want to support this use case, we should merge the metadata from the generator
            raise ValueError('The DSProcess can be used only on non-started generators / coroutines')
        super().__init__(*args, **kwargs)

    def __iter__(self):
        ''' Required to use the class to get events from it. '''
        return self

    def __next__(self):
        ''' Gets next state, without pushing any particular event. '''
        self.value = self.scheduled_generator.send(None)
        return self.value

    def send(self, event):
        ''' Pushes an event to the task and gets new state. '''
        self.value = self.scheduled_generator.send(event)
        return self.value

    def _scheduled_gfcn(self, time):
        ''' Start a schedulable process with possible delay '''
        yield from self.sim.gwait(time)
        retval = yield from self.generator
        return retval

    async def _scheduled_fcn(self, time):
        ''' Start a schedulable process with possible delay '''
        await self.sim.wait(time)
        retval = await self.generator
        return retval

    def _schedule(self, time):
        ''' This api is used with sim.schedule(...) '''
        if inspect.iscoroutine(self.generator):
            self.scheduled_generator = self._scheduled_fcn(time)
        elif inspect.isgenerator(self.generator):
            self.scheduled_generator = self._scheduled_gfcn(time)
        else:
            raise ValueError(f'The assigned code {self.generator} to the process {self} is not generator, neither coroutine.')
        return self

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

    async def join(self, timeout=float('inf')):
        with self.sim.observe_pre(self):
            retval = await self.sim.check_and_wait(cond=lambda e:self.finished())
        return retval
    
    def gjoin(self, timeout=float('inf')):
        with self.sim.observe_pre(self):
            retval = yield from self.sim.check_and_gwait(cond=lambda e:self.finished())
        return retval


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
            to_process = frame.f_locals['schedulable']
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
