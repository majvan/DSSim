# Copyright 2020- majvan (majvan@gmail.com)
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
import inspect
from functools import wraps
from typing import List, Any, Union, Tuple, Callable, Generator, Coroutine, Optional, Iterator, TYPE_CHECKING
from dssim.timequeue import TimeQueue, ZeroTimeQueue
from dssim.base import NumericType, TimeType, DSAbsTime, EventType, EventRetType, DSComponentSingleton, ISubscriber, IFuture
from dssim.pubsub import SimPubsubMixin
from dssim.pubsub.future import SimFutureMixin
from dssim.pubsub.process import SimProcessMixin
from dssim.pubsub.components.container import SimContainerMixin
from dssim.pubsub.components.queue import SimQueueMixin
from dssim.lite.components.litequeue import SimLiteQueueMixin
from dssim.lite.components.literesource import SimLiteResourceMixin
from dssim.pubsub.components.resource import SimResourceMixin
from dssim.pubsub.components.state import SimStateMixin
from dssim.pubsub.cond import SimFilterMixin


class VoidSubscriber(ISubscriber):
    ''' A void subscriber which should never be called.

    If seen in the debugger, it typically means that the current subscriber
    does not run within any process.  The singleton instance is used as a
    safe non-null default for _parent_process.
    '''
    def __init__(self, name: str = 'Default void subscriber') -> None:
        self.name = name

    def send(self, event: EventType) -> None:
        ''' A void subscriber is typically not expected to be called.
        In special cases it can be called - for instance, for pure
        coro kicks up or when the scheduling of events happens outside
        coroutines - e.g. planning startup events.
        '''
        pass

void_subscriber = VoidSubscriber()


class _Awaitable:
    def __init__(self, val: EventType = None) -> None:
        self.val = val

    def __await__(self) -> Generator[EventType, None, EventType]:
        retval = yield self.val
        return retval


SchedulableType = Union[ISubscriber, Generator, Coroutine, Callable]


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



class SimWaitMixin:
    ''' Basic gwait/wait/sleep mixin for DSSimulation.

    Provides lightweight wait primitives that work purely at the simulation
    layer — no conditions, no pubsub, no DSProcess.

    SimProcessMixin (when present in DSSimulation's MRO before this class)
    overrides these with full condition-aware versions.
    '''

    def gwait(self: "DSSimulation", timeout: TimeType = float('inf')) -> "Generator[EventType, EventType, EventType]":
        ''' Wait for up to *timeout* time units.
        Returns the first event delivered to the caller, or None on timeout.
        '''
        # Fast path for the common LiteLayer2 pattern: unbounded wait.
        # This avoids timeout bookkeeping and one extra call frame per wakeup.
        if timeout == float('inf'):
            event = yield None
            if isinstance(event, Exception):
                raise event
            return event
        retval = yield from self._gwait_for_event(timeout)
        return retval

    async def wait(self: "DSSimulation", timeout: TimeType = float('inf')) -> "EventType":
        ''' Async variant of gwait.
        Returns the first event delivered to the caller, or None on timeout.
        '''
        # Fast path for the common LiteLayer2 pattern: unbounded wait.
        # This avoids timeout bookkeeping and one extra call frame per wakeup.
        if timeout == float('inf'):
            event = await _Awaitable(None)
            if isinstance(event, Exception):
                raise event
            return event
        retval = await self._wait_for_event(timeout)
        return retval

    def gsleep(self: "DSSimulation", timeout: TimeType = float('inf')) -> "Generator[EventType, EventType, EventType]":
        '''Sleep for up to *timeout* while ignoring non-exception events.'''
        if timeout == float('inf'):
            while True:
                _ = yield from self.gwait(float('inf'))
        end_time = self._compute_time(timeout)
        while True:
            remaining = end_time - self.time
            if remaining <= 0:
                return None
            event = yield from self.gwait(remaining)
            if event is None:
                return None

    async def sleep(self: "DSSimulation", timeout: TimeType = float('inf')) -> "EventType":
        '''Async sleep variant; ignores non-exception events until timeout.'''
        if timeout == float('inf'):
            while True:
                _ = await self.wait(float('inf'))
        end_time = self._compute_time(timeout)
        while True:
            remaining = end_time - self.time
            if remaining <= 0:
                return None
            event = await self.wait(remaining)
            if event is None:
                return None


class SimScheduleMixin:
    ''' Base schedule() for ISubscriber — the minimal schedulable type.
    SimProcessMixin (when present) overrides schedule() for generators and
    callables and falls back to super().schedule() which resolves here.
    '''
    def schedule(self: "DSSimulation", time: TimeType, schedulable: ISubscriber) -> ISubscriber:
        ''' Schedules an ISubscriber directly onto the time queue. '''
        if inspect.iscoroutine(schedulable) or inspect.isgenerator(schedulable):
            self.schedule_event(time, None, schedulable)
            return schedulable
        elif isinstance(schedulable, ISubscriber):
            self.schedule_event(time, None, schedulable)
            return schedulable
        raise ValueError(f'The provided schedulable {schedulable} is not supported.'
                         'For processes, full-producers and full-subscribers, include SimProcessMixin.')


# Minimal layer2: plain-generator / coroutine scheduling with basic
# gwait/wait/sleep. No pubsub, no DSProcess.
LiteLayer2 = (
    SimWaitMixin,
    SimScheduleMixin,
    SimLiteQueueMixin,
    SimLiteResourceMixin,
)

# Default layer2 mixins — loaded when layer2 is not explicitly overridden.
# These require the pubsub layer (SimPubsubMixin) to be present.
PubSubLayer2 = (
    SimPubsubMixin,
    SimFutureMixin,
    SimProcessMixin,
    SimFilterMixin,
    SimContainerMixin,
    SimQueueMixin,
    SimResourceMixin,
    SimStateMixin,
)

# Cache of dynamically created subclasses keyed by (base_class, layer2_tuple).
# Avoids recreating the same class on every DSSimulation() call.
_dyn_class_cache: dict = {}


class DSSimulation(DSComponentSingleton):  # basic schedule() for plain ISubscriber; always available
    ''' The simulation is a which schedules the nearest (in time) events.

    The second-layer mixins (SimProcessMixin, SimFutureMixin, ...) are loaded
    dynamically at construction time via the *layer2* parameter.  When layer2
    contains SimProcessMixin its gwait/wait/schedule override the base versions
    from SimWaitMixin / SimScheduleMixin through normal MRO resolution.

    Pass layer2=[] (or layer2=None) to get a minimal simulation with no
    process/pubsub layer — useful for plain-generator / coroutine usage.
    '''

    def _load_layer2(self, layer2) -> None:
        ''' Inject layer2 mixins into this instance by reassigning __class__.

        A cached dynamic subclass is reused across instances with the same
        (base_class, layer2) combination so class-creation overhead is paid
        only once.  The mixins are inserted before DSSimulation in the MRO so
        that e.g. SimProcessMixin.gwait overrides SimWaitMixin.gwait.
        '''
        key = (type(self), tuple(layer2))
        if key not in _dyn_class_cache:
            _dyn_class_cache[key] = type(
                type(self).__name__,
                tuple(layer2) + (type(self),),
                {},
            )
        self.__class__ = _dyn_class_cache[key]

    def __init__(self, name: str = 'dssim', single_instance: bool = True,
                 layer2=PubSubLayer2) -> None:
        if layer2:
            self._load_layer2(layer2)
        self.name = name
        self.names: dict = {}  # stores names of associated components
        if DSComponentSingleton.sim_singleton is None:
            DSComponentSingleton.sim_singleton = self  # The first sim environment will be the first initialized one
        elif not single_instance:
            print('Warning, you are initializing another instance of the simulation.'
                  'This case is supported, but it is not a typical case and you may'
                  'want not intentionally to do so. To suppress this warning, call'
                  'DSSimulation(single_instance=False)')
        self._simtime: NumericType = 0
        self._restart()

    def __repr__(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name

    def restart(self, time: TimeType = 0) -> None:
        self._simtime = time if isinstance(time, (float, int)) else time.value
        self._restart()

    @property
    def time(self) -> NumericType: return self._simtime

    @property
    def pid(self) -> ISubscriber: return self._parent_process

    def _restart(self) -> None:
        self.time_queue = TimeQueue()
        self.now_queue = ZeroTimeQueue()
        self.num_events: int = 0
        # By default, we use fake subscriber. It will be rewritten on the first 
        self._parent_process: ISubscriber = void_subscriber

    def _compute_time(self, time: TimeType) -> NumericType:
        ''' Recomputes a rel/abs time to absolute time value '''
        if isinstance(time, DSAbsTime):
            ftime = time.to_number()
            if ftime < self.time:
                raise ValueError('The time is absolute and cannot be lower than now')
        elif time < 0:
            raise ValueError('The time is relative from now and cannot be negative')
        else:
            ftime = self.time + time
        return ftime

    def to_abs_time(self, time: TimeType) -> DSAbsTime:
        if isinstance(time, DSAbsTime):
            return time
        return DSAbsTime(self._simtime + time)

    def send_object(self, subscriber: ISubscriber, event: EventType) -> EventType:
        ''' Send an event object to a subscriber. Return value from the subscriber. '''

        # We want to kick from this process to another process (see below). However, after
        # returning back to this process, we want to renew our process ID back to be used.
        # We do that by remembering the pid here and restoring at the end.
        pid = self._parent_process

        try:
            # We want to kick from this process another 'subscriber' process. So we will change
            # the process ID (we call it self._parent_process). This is needed because if the new
            # created process would schedule a wait cycle for his own, he would like to know his own
            # process ID (see the wait method). That's why we have to set him his PID now.
            # In other words, the subscriber.send() can invoke a context switch
            # without a handler- so this is the context switch handler, currently only
            # changing process ID.
            self._parent_process = subscriber
            retval = subscriber.send(event)
        except StopIteration as exc:
            if isinstance(subscriber, IFuture):
                # IFuture.finish() is responsible for sim.cleanup(self).
                retval = subscriber.finish(exc.value)
            else:
                retval = exc.value
                self.cleanup(subscriber)
        except ValueError as exc:
            if isinstance(subscriber, IFuture):
                retval = subscriber.fail(exc)
            global _exiting
            if 'generator already executing' in str(exc) and not _exiting:
                _exiting = True
                print_cyclic_signal_exception(exc)
            raise
        finally:
            self._parent_process = pid
        return retval

    def schedule_event(self, time: TimeType, event: EventType, subscriber: Optional[ISubscriber] = None) -> EventType:
        ''' Schedules an event object into timequeue. Finally the target process will be signalled. '''
        time = self._compute_time(time)
        subscriber = subscriber or self._parent_process  # schedule to a process or to itself
        self.time_queue.add_element(time, (subscriber, event))
        return event

    def signal(self, event: EventType, subscriber: Optional[ISubscriber] = None) -> None:
        ''' Schedules an event object onto the now-queue for zero-time dispatch. '''
        subscriber = subscriber or self._parent_process  # schedule to a process or to itself
        self.now_queue.append((subscriber, event))

    def _gwait_for_event(self, timeout: TimeType, val: EventRetType = None) -> Generator[EventType, EventType, EventType]:
        # Re-compute abs/relative time to abs for the timeout
        time = float('inf') if timeout == float('inf') else self._compute_time(timeout)
        # Schedule the timeout to the time queue. The condition is only for higher performance
        if time != float('inf'):
            self.time_queue.add_element(time, (self._parent_process, None))
        event: EventType = True
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
        finally:
            if event is not None and time != float('inf'):
                # If we terminated before timeout and the timeout event is on time queue- remove it
                self.time_queue.delete_val((self._parent_process, None))
        return event

    async def _wait_for_event(self, timeout: TimeType, val: EventRetType = None) -> EventType:
        # Re-compute abs/relative time to abs for the timeout
        time = float('inf') if timeout == float('inf') else self._compute_time(timeout)
        # Schedule the timeout to the time queue. The condition is only for higher performance
        if time != float('inf'):
            self.time_queue.add_element(time, (self._parent_process, None))
        event: EventType = True
        try:
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
                self.time_queue.delete_val((self._parent_process, None))
        return event

    def cleanup(self, subscriber: ISubscriber = None) -> None:
        subscriber = subscriber or self.pid
        # The subscriber has finished.
        # We make a cleanup of a waitable condition. There is still waitable condition kept
        # for the subscriber. Since the process has finished, it will never need it, however
        # there may be events for the process planned.
        # Reset the condition if the subscriber supports it
        if hasattr(subscriber, 'reset_cond'):
            subscriber.reset_cond()
        # Remove all the events for this subscriber
        self.now_queue = ZeroTimeQueue(item for item in self.now_queue if item[0] is not subscriber)
        self.time_queue.delete_sub(subscriber)

    def try_send_object(self, subscriber: ISubscriber, event: EventType) -> EventType:
        '''Condition-aware dispatch used by run().

        Unlike DSsubscriber.try_send(), this path keeps dispatch ownership in DSSimulation
        and still supports plain ISubscriber implementations that only expose send().
        '''
        if hasattr(subscriber, 'get_cond'):
            conds = subscriber.get_cond()
            signaled, event = conds.check(event)
            if not signaled:
                return False
        return self.send_object(subscriber, event)

    def run(self, up_to: TimeType = float('inf'), future: EventType = object()) -> Tuple[float, int]:
        ''' This is the simulation machine. In a loop it takes first event and process it.
        The loop ends when the queue is empty or when the simulation time is over.
        '''
        ftime = up_to.to_number() if isinstance(up_to, DSAbsTime) else up_to
        while len(self.time_queue) > 0:
            # Get the first event on the queue
            tevent, (subscriber, event_obj) = self.time_queue.get0()
            if tevent >= ftime:
                retval_time = self.time
                self._simtime = ftime
                break
            # The following lines are required for asyncio parity which requires
            # an event loop implementation of run_until_complete(future)
            if event_obj == future:
                return self.time, self.num_events
            self.num_events += 1
            self._simtime = tevent
            self.time_queue.pop()
            self.try_send_object(subscriber, event_obj)
            while self.now_queue:
                (subscriber, event_obj) = self.now_queue.popleft()
                # check for the future as well in the now_queue
                if event_obj == future:
                    return self.time, self.num_events
                self.num_events += 1
                self.try_send_object(subscriber, event_obj)
        else:
            retval_time = self.time
            self._simtime = ftime
        return retval_time, self.num_events


_exiting = False  # global var to prevent repeating nested exception frames

from types import FrameType

def print_cyclic_signal_exception(exc: Exception) -> None:
    ''' The function prints out detailed information about frame stack related
    to the simulation process, filtering out unnecessary info.
    '''
    exc_type, exc_value, exc_traceback = sys.exc_info()
    if exc_traceback is None:
        return
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
    stack = []
    process_stack = []
    f: Optional[FrameType] = exc_traceback.tb_frame
    while f is not None:
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
            to_process = frame.f_locals['subscriber']
            event = frame.f_locals['event']
            d: List = [method, line, filename, from_process, to_process, event, False, False]
            process_stack.append(d)
    # search for the processes to highlight (highlight the loop conflict)
    if not to_process:
        return
    print('Signal stack:')
    conflicting_process = to_process
    for pframe in reversed(process_stack):
        if pframe[3] == conflicting_process:
            pframe[-2] = True  # mark the last from_process which needs to be highlighted
            break
    process_stack[-1][-1] = True # mark the last to_process which needs to be highlighted
    for pframe in process_stack:
           method, line, filename, from_process, to_process, event, from_c, to_c = pframe
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
