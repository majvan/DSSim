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
from dssim.timequeue import TimeQueue
from dssim.base import DSAbsTime, StackedCond, DSComponentSingleton
from dssim.pubsub import DSConsumer, DSCallback
from dssim.future import DSFuture
from dssim.process import DSProcess, SimProcessMixin

class _Awaitable:
    def __init__(self, val=None):
        self.val = val

    def __await__(self):
        retval = yield self.val
        return retval


class DSSimulation(SimProcessMixin, DSComponentSingleton):
    ''' The simulation is a which schedules the nearest (in time) events. '''

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
        if DSComponentSingleton.sim_singleton is None:
            DSComponentSingleton.sim_singleton = self  # The first sim environment will be the first initialized one
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
