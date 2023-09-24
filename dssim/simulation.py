# Copyright 2020 NXP Semiconductors
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
from typing import List, Any, Union, Tuple, Callable, Generator, Coroutine, Optional, cast, overload, TYPE_CHECKING
from dssim.timequeue import TimeQueue
from dssim.base import NumericType, TimeType, DSAbsTime, EventType, EventRetType, CondType, StackedCond, DSComponentSingleton
from dssim.pubsub import DSConsumer, DSCallback, void_consumer, SimPubsubMixin
from dssim.future import DSFuture, SimFutureMixin
from dssim.process import DSProcessType, ProcessMetadata, DSProcess, SimProcessMixin
from dssim.components.container import SimContainerMixin, SimQueueMixin
from dssim.components.resource import SimResourceMixin
from dssim.components.state import SimStateMixin
from dssim.cond import SimFilterMixin


class _Awaitable:
    def __init__(self, val: EventType = None) -> None:
        self.val = val

    def __await__(self) -> Generator[EventType, None, EventType]:
        retval = yield self.val
        return retval


SchedulableType = Union[DSFuture, Generator, Coroutine, Callable, DSCallback]


class DSSimulation(DSComponentSingleton,
                   SimPubsubMixin,
                   SimFutureMixin,
                   SimProcessMixin,
                   SimFilterMixin,
                   SimContainerMixin,
                   SimQueueMixin,
                   SimResourceMixin,
                   SimStateMixin):
    ''' The simulation is a which schedules the nearest (in time) events. '''

    class _TestObject:
        ''' An artificial object to be used for check_and_wait- see description of the method '''
        pass

    def __init__(self, name: str = 'dssim', single_instance: bool = True) -> None:
        ''' The simulation holds the list of producers which share the same time queue.
        The list is only for the application informational purpose to be able to identify
        all the producers which belong to the same simulation entity.
        '''
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
    def pid(self) -> DSConsumer: return self._parent_process

    def _restart(self) -> None:
        self.time_queue = TimeQueue()
        self.num_events: int = 0
        # By default, we use fake consumer. It will be rewritten on the first 
        self._parent_process: DSConsumer = void_consumer

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

    @overload        
    def schedule(self, time: TimeType, schedulable: Union[Generator, Coroutine]) -> DSProcess: ...

    @overload        
    def schedule(self, time: TimeType, schedulable: DSProcessType) -> DSProcessType: ...

    @overload        
    def schedule(self, time: TimeType, schedulable: Callable) -> DSCallback: ...

    def schedule(self, time: TimeType, schedulable: SchedulableType) -> SchedulableType:
        ''' Schedules the start of a (new) process. '''
        if isinstance(schedulable, DSConsumer):
            process = schedulable
        elif inspect.iscoroutine(schedulable) or inspect.isgenerator(schedulable):
            process = DSProcess(schedulable, sim=self)
        elif callable(schedulable):
            process = DSCallback(schedulable, sim=self)
        else:
            raise ValueError(f'The provided function {schedulable} is probably missing @DSSchedulable decorator')
        if isinstance(process, DSProcess):
            process.schedule(time)
        else:
            self.schedule_event(time, None, process)
        return process

    def send_object(self, consumer: DSConsumer, event: EventType) -> EventType:
        ''' Send an event object to a consumer. Return value from the consumer. '''

        retval: EventType = False

        # We want to kick from this process to another process (see below). However, after
        # returning back to this process, we want to renew our process ID back to be used.
        # We do that by remembering the pid here and restoring at the end.
        pid = self._parent_process

        try:
            # We want to kick from this process another 'consumer' process. So we will change
            # the process ID (we call it self._parent_process). This is needed because if the new
            # created process would schedule a wait cycle for his own, he would like to know his own
            # process ID (see the wait method). That's why we have to set him his PID now.
            # In other words, the consumer.send() can invoke a context switch
            # without a handler- so this is the context switch handler, currently only
            # changing process ID.
            self._parent_process = consumer
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
            self._parent_process = pid
        return retval

    def try_send(self, consumer: DSConsumer, event: EventType) -> EventType:
        ''' Send an event object to a consumer process. Convert event from parameters to object. '''

        # We will be sending signal (event) to a consumer, which has some condition set
        # upon waiting for a pattern event.
        # The idea is that the consumer will get the event only if the condition is met-
        # an early check.
        conds = consumer.get_cond()
        signaled, event = conds.check(event)
        if not signaled:
            return False  # not signalled
        retval = self.send_object(consumer, event)
        return retval

    def signal(self, process: DSConsumer, event: EventType, time: TimeType = 0) -> EventType:
        ''' Schedules an event object into timequeue. Finally the target process will be signalled. '''
        time = self._compute_time(time)
        consumer = process if process is not None else self._parent_process  # schedule to a process or to itself
        self.time_queue.add_element(time, (consumer, event))
        return event

    def schedule_event(self, time: TimeType, event: EventType, consumer: Optional[DSConsumer] = None) -> EventType:
        ''' Schedules an event object into timequeue. Finally the target process will be signalled. '''
        time = self._compute_time(time)
        consumer = consumer or self._parent_process  # schedule to a process or to itself
        self.time_queue.add_element(time, (consumer, event))
        return event

    def _gwait_for_event(self, timeout: TimeType, val: EventRetType = None) -> Generator[EventType, EventType, EventType]:
        # Re-compute abs/relative time to abs for the timeout
        time = self._compute_time(timeout)
        # Schedule the timeout to the time queue. The condition is only for higher performance
        if time != float('inf'):
            self.time_queue.add_element(time, (self._parent_process, None))
        event: EventType = True
        try:
            t0 = self._simtime
            # Pass value to the feeder and wait for next event
            event = yield val
            meta: ProcessMetadata = cast(ProcessMetadata, self._parent_process.meta)
            meta.last_wait_time = self._simtime - t0  # Store waiting time

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

    def gwait(self, timeout: TimeType = float('inf'), cond: CondType = lambda e: False, val: EventRetType = True) -> Generator[EventType, EventType, EventType]:
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
        conds = self._parent_process.meta.cond
        # Set the condition object (lambda / object / ...) in the process metadata
        conds.push(cond)
        try:
            event = yield from self._gwait_for_event(timeout, val)
        finally:
            conds.pop()
        if hasattr(cond, 'cond_value'):
            event = cond.cond_value()
        return event

    def check_and_gwait(self, timeout: TimeType = float('inf'), cond: CondType = lambda e: False, val: EventRetType = True) -> Generator[EventType, EventType, EventType]:
        # This function can be used to run a pre-check for such conditions, which are
        # invariant to the passed event, for instance to check for a state of an object
        # so if the state matches, it returns immediately
        # Otherwise it jumps to the waiting process.
        conds = self._parent_process.meta.cond
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

    async def _wait_for_event(self, timeout: TimeType, val: EventRetType = None) -> EventType:
        # Re-compute abs/relative time to abs for the timeout
        time = self._compute_time(timeout)
        # Schedule the timeout to the time queue. The condition is only for higher performance
        if time != float('inf'):
            self.time_queue.add_element(time, (self._parent_process, None))
        event: EventType = True
        try:
            t0 = self._simtime
            # Pass value to the feeder and wait for next event
            event = await _Awaitable(val)
            meta: ProcessMetadata = cast(ProcessMetadata, self._parent_process.meta)
            meta.last_wait_time = self._simtime - t0  # Store waiting time

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

    async def wait(self, timeout: TimeType = float('inf'), cond: CondType = lambda e: False, val: EventRetType = True) -> EventType:
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
        conds = self._parent_process.meta.cond
        # Set the condition object (lambda / object / ...) in the process metadata
        conds.push(cond)
        try:
            event = await self._wait_for_event(timeout, val)
        finally:
            conds.pop()
        if hasattr(cond, 'cond_value'):
            event = cond.cond_value()
        return event

    async def check_and_wait(self, timeout: TimeType = float('inf'), cond: CondType = lambda e: False, val: EventRetType = True) -> EventType:
        # This function can be used to run a pre-check for such conditions, which are
        # invariant to the passed event, for instance to check for a state of an object
        # so if the state matches, it returns immediately
        # Otherwise it jumps to the waiting process.
        conds = self._parent_process.meta.cond
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

    def cleanup(self, consumer: DSConsumer) -> None:
        # The consumer has finished.
        # We make a cleanup of a waitable condition. There is still waitable condition kept
        # for the consumer. Since the process has finished, it will never need it, however
        # there may be events for the process planned.
        # Remove the condition
        meta = consumer.meta
        meta.cond = StackedCond()
        # Remove all the events for this consumer
        self.time_queue.delete_cond(lambda e: e[0] is consumer)

    def run(self, up_to: TimeType = float('inf'), future: EventType = object()) -> Tuple[float, int]:
        ''' This is the simulation machine. In a loop it takes first event and process it.
        The loop ends when the queue is empty or when the simulation time is over.
        '''
        ftime = up_to.to_number() if isinstance(up_to, DSAbsTime) else up_to
        while len(self.time_queue) > 0:
            # Get the first event on the queue
            tevent, (consumer, event_obj) = self.time_queue.get0()
            if tevent >= ftime:
                retval_time = self.time
                self._simtime = ftime
                break
            if event_obj == future:
                retval_time = self.time
                break
            self.num_events += 1
            self._simtime = tevent
            self.time_queue.pop()
            self.try_send(consumer, event_obj)
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
            to_process = frame.f_locals['consumer']
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

