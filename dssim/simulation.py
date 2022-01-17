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
import types
import sys
from functools import wraps
from collections.abc import Iterable
from inspect import isgeneratorfunction
from dssim.timequeue import TimeQueue


class DSAbortException(Exception):
    ''' Exception used to abort waiting process '''

    def __init__(self, producer, **info):
        super().__init__()
        self.producer = producer
        self.info = info


class DSSimulation:
    ''' The simulation is a which schedules the nearest (in time) events. '''

    def __init__(self):
        ''' The simulation holds the list of producers which share the same time queue.
        The list is only for the application informational purpose to be able to identify
        all the producers which belong to the same simulation entity.
        '''
        self._restart(time=0)

    def restart(self, time=0):
        self._restart(time=time)

    def _restart(self, time):
        self.time_queue = TimeQueue()
        self.num_events = 0
        self.time = time
        self.parent_process = None
        self.time_process = self._time_process()
        self._kick(self.time_process)

    def _time_process(self):
        ''' For the events which were produced with a non-process producer, we run
        additional process which signals them in the scheduled time.
        '''
        while True:
            event = yield from self._wait_for_event(cond=lambda e: True)
            # Get producer which really produced the event and signal to associated consumers
            event['producer'].signal(**event)

    def schedule_event(self, time, event, process=None):
        ''' Schedules an event object into timequeue '''
        if time < 0:
            raise ValueError('The time is relative from now and cannot be negative')
        # producer = event['producer']  # Encapsulation of real producer done in the producer.
        if (process == self.time_process) and 'producer' not in event:
            raise ValueError('The event, if processed by time_process, is missing '
                             'encapsulation of producer. '
                             'Use DSProducer to schedule an event on time_process.')
        consumer = process or self.parent_process  # schedule to a process or to itself
        self.time_queue.add_element(time, (consumer, event))
        return event

    def delete(self, cond):
        ''' An interface method to delete events on the queue '''
        self.time_queue.delete(cond)

    def schedule_timeout(self, time, schedulable):
        ''' Schedules a None object. The None object is recognized as a timeout in the
        wait() method.
        '''
        if time < 0:
            raise ValueError('The time is relative from now and cannot be negative')
        self.time_queue.add_element(time, (schedulable, None))

    def schedule(self, time, schedulable):
        ''' Schedules the start of a (new) process. '''
        if not isinstance(schedulable, Iterable):
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
        else:
            new_process = self._scheduled_fcn(time, schedulable)
        self.parent_process = new_process
        self._kick(new_process)
        self.parent_process = old_process
        return new_process

    def _signal_object(self, schedulable, event):
        ''' Send an event object to a schedulable consumer '''
        retval = True
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
            schedulable.send(event)
        except StopIteration as exc:
            # There is nothing more, the schedulable has finished
            retval = False
        except ValueError as exc:
            global _exiting
            if 'generator already executing' in str(exc) and not _exiting:
                _exiting = True
                print_cyclic_signal_exception(exc)
            raise
        self.parent_process = pid
        return retval  # always successful

    def signal(self, schedulable, **event):
        ''' Send an event object to a consumer process. Convert event from parameters to object. '''
        return self._signal_object(schedulable, event)

    def abort(self, schedulable, **info):
        ''' Send abort exception to a consumer process. Convert event from parameters to object. '''
        return self._signal_object(schedulable, DSAbortException(self.parent_process, **info))

    def _scheduled_fcn(self, time, schedulable):
        ''' Start a schedulable process with possible delay '''
        if time:
            yield from self.wait(time)
        retval = yield from schedulable
        return retval

    # @DSSchedulable - not needed, removed to reduce code complexity
    def wait(self, timeout=float('inf'), cond=lambda c: False):
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
        schedulable = self.parent_process
        # Put myself (my process) on the queue
        self.schedule_timeout(timeout, schedulable)
        try:
            event = yield from self._wait_for_event(cond)
        except Exception as exc:
            # If we got any exception, we will never use the timeout anymore
            self.delete(lambda e: e[0] is schedulable)
            raise
        if event is not None:
            # If we terminated before timeout, then the timeout event is on time queue- remove it
            self.delete(lambda e: e[0] is schedulable)
        return event

    def _kick(self, schedulable):
        ''' Provides first kick (run) of a schedulable process. '''
        try:
            next(schedulable)
        except StopIteration as exp:
            pass

    def _wait_for_event(self, cond):
        ''' Provides a backend for the wait() method.
        Handles the reception of the event / an exception.
        '''
        while True:
            event = yield
            if event is None:  # timeout received
                return event
            if isinstance(event, Exception):  # any excpetion raised, including TimeoutException
                raise event
            if callable(cond) and cond(event):  # there was a filter condition function set and the conditions is met
                return event
            if cond == event:  # we are expecting exact event and it came
                return event

    def run(self, up_to=None):
        ''' This is the simulation machine. In a loop it takes first event and process it.
        The loop ends when the queue is empty or when the simulation time is over.
        '''
        if up_to is None:
            up_to = float('inf')
        while len(self.time_queue) > 0:
            # Get the first event on the queue
            tevent, (process, event_obj) = self.time_queue.get0()
            if tevent >= up_to:
                break
            self.num_events += 1
            self.time = tevent
            self.time_queue.pop()
            self._signal_object(process, event_obj)

        return self.num_events


# Creates already one instance of simulation. Typically only this instance is all we need
# for simulation.
# There is a possibility to create another simulation object and refer to that object.
# Useful if we want to restart the simulation, for example.
sim = DSSimulation()


class DSInterface:
    ''' Common interface for DSSim. It creates a rule that every interface shall have
    a name (useful for debugging when debugger displays interface name) and assigned
    simulation object (useful when creating more simulation objects in one application).
    '''
    _names = {}

    def __init__(self, name=None, sim=sim, **kwargs):
        if name is None:
            counter = DSInterface._names.get(str(self.__class__), [])
            num = len(counter)
            counter.append(num)
            DSInterface._names[str(self.__class__)] = counter
            self.name = '{}{}'.format(str(self.__class__), num)
        elif name in self._names:
            raise ValueError('Interface with such name already registered.')
        else:
            self.name = name
        self.sim = sim

    def __repr__(self):
        return self.name


class DSComponent(DSInterface):
    ''' An interface for a component of DSSim. So far DSInteface specification is good enough
    to define a component interface of DSSim. Extension in the future is possible.
    '''
    pass


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
        if isgeneratorfunction(api_func):
            extended_gen = api_func(*args, **kwargs)
        else:
            extended_gen = _fcn_in_generator(*args, **kwargs)
        return extended_gen
    
    return scheduled_func


class DSProcess(DSComponent):
    ''' Typical task used in the simulations.
    This class "extends" generator function for additional info.
    The best practise is to use DSProcess instead of generators.
    '''
    def __init__(self, generator, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ''' Initializes DSProcess. The input has to be a geneator function. '''
        self.generator = generator
        self.scheduled_generator = generator
        # We store the latest value. Useful to check the status after finish.
        self.value = None
        self.finished = False
        self.waiting_tasks = []  # taks waiting to finish this task

    def __iter__(self):
        ''' Required to use the class to get events from it. '''
        return self

    def __next__(self):
        ''' Gets next state, without pushing any particular event. '''
        try:
            self.value = next(self.scheduled_generator)
        except StopIteration as e:
            self.value = e.value
            self._finish()
            raise
        return self.value

    def send(self, event):
        ''' Pushes an event to the task and gets new state. '''
        try:
            self.value = self.scheduled_generator.send(event)
        except StopIteration as e:
            self.value = e.value
            self._finish()
            raise
        return self.value

    def abort(self, producer=None, **info):
        ''' Aborts a task. Additional reasoning info can be provided. '''
        try:
            self.value = self.send(DSAbortException(producer, **info))
        except StopIteration as e:
            self._finish()
        return self.value

    def _scheduled_fcn(self, time):
        ''' Start a schedulable process with possible delay '''
        if time:
            yield from self.sim.wait(time)
        retval = yield from self.generator
        return retval

    def _schedule(self, time):
        ''' This api is used with sim.schedule(...) '''
        self.scheduled_generator = self._scheduled_fcn(time)
        return self

    def schedule(self, time):
        ''' This api is to schedule directly task.schedule(3) '''
        self.sim.schedule(time, self)

    def _finish(self):
        self.finished = True
        for task in self.waiting_tasks:
            self.sim.signal(task, finished=True)  # push the blocked task

    def join(self, timeout=float('inf')):
        if self.finished:
            return 
        try:
            self.waiting_tasks.append(self.sim.parent_process)
            obj = yield from sim.wait(timeout, cond=lambda c:True)
        finally:
            try:
                waiting_task = self.waiting_tasks.remove(self.sim.parent_process)
            except ValueError as e:
                pass
        return obj


_exiting = False  # global var to prevent repeating nested exception frames

def print_cyclic_signal_exception(exc):
    ''' The function prints out detailed information about frame stack related
    to the simulation process, filtering out unnecessary info.
    '''
    exc_type, exc_value, exc_traceback = sys.exc_info()
    print('Error:', exc)
    print('\nAn already running schedulable (DSProcess / generator) was\n'
          'signalled and therefore Python cannot handle such state.\n'
          'There are two possible solutions for this issue:\n'
          '1. You rewrite the code to remove cyclic signalling of processes.\n'
          '   This is recommended at least to try because this issue might\n'
          '   signify a real design flaw in the simulation / implementation.\n'
          '2. Instead of calling sim.signal(process, **event)\n'
          '   you schedule the event into the queue with zero delta time.\n'
          '   Example of the modification:\n'
          '   Previous code:\n'
          '   sim.signal(process, status="Ok")\n'
          '   New code:\n'
          '   sim.schedule_event(0, {"status": "Ok"}, process)\n\n'
          'Signal stack:')
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
    for frame in stack:
        if frame.f_code.co_filename != __file__:
            method = frame.f_code.co_name
            line = frame.f_lineno
            filename = frame.f_code.co_filename
        elif frame.f_code.co_name == '_signal_object':
            from_process = frame.f_locals['pid']
            to_process = frame.f_locals['schedulable']
            event = frame.f_locals['event']
            d = [method, line, filename, from_process, to_process, event, False, False]
            process_stack.append(d)
    # search for the processes to highlight (highlight the loop conflict)
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
