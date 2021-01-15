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
from dssim.timequeue import TQBinTree, NowQueue, ITimeQueue
from dssim.base import NumericType, TimeType, EventType, EventRetType, DSComponentSingleton, ISubscriber, IFuture
from dssim.pubsub import SimPubsubMixin
from dssim.pubsub.future import SimFutureMixin
from dssim.pubsub.process import SimProcessMixin
from dssim.pubsub.components.container import SimContainerMixin
from dssim.pubsub.components.queue import SimQueueMixin
from dssim.lite.pubsub import SimLitePubsubMixin
from dssim.lite.components.litequeue import SimLiteQueueMixin
from dssim.lite.components.literesource import SimLiteResourceMixin
from dssim.lite.components.litetime import SimLiteTimeMixin
from dssim.lite.process import SimLiteProcessMixin, SimLiteWaitMixin
from dssim.pubsub.components.resource import SimResourceMixin
from dssim.pubsub.components.state import SimStateMixin
from dssim.pubsub.components.time import SimTimeMixin
from dssim.pubsub.cond import SimFilterMixin


class VoidSubscriber(ISubscriber):
    ''' A void subscriber which should never be called.

    If seen in the debugger, it typically means that the current subscriber
    does not run within any process.  The singleton instance is used as a
    safe non-null default for pid.
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
    SimLiteWaitMixin,
    SimLiteProcessMixin,
    SimScheduleMixin,
    SimLitePubsubMixin,
    SimLiteQueueMixin,
    SimLiteResourceMixin,
    SimLiteTimeMixin,
)

# Default pubsub layer2 mixins.
PubSubLayer2 = (
    SimPubsubMixin,
    SimFutureMixin,
    SimProcessMixin,
    SimFilterMixin,
    SimContainerMixin,
    SimQueueMixin,
    SimResourceMixin,
    SimStateMixin,
    SimTimeMixin,
)

# Cache of dynamically created subclasses keyed by (base_class, layer2_tuple).
# Avoids recreating the same class on every DSSimulation() call.
_dyn_class_cache: dict = {}


class DSSimulation(DSComponentSingleton):  # basic schedule() for plain ISubscriber; always available
    ''' The simulation is a which schedules the nearest (in time) events.

    The second-layer mixins (SimProcessMixin, SimFutureMixin, ...) are loaded
    dynamically at construction time via the *layer2* parameter.  When layer2
    contains SimProcessMixin its gwait/wait/schedule override the base versions
    from SimLiteWaitMixin / SimScheduleMixin through normal MRO resolution.

    Pass layer2=[] (or layer2=None) to get a minimal simulation with no
    process/pubsub layer — useful for plain-generator / coroutine usage.

    Pass timequeue=<queue class> to switch event time-queue
    implementation (default: dssim.timequeue.TQBinTree).
    '''

    def _load_layer2(self, layer2) -> None:
        ''' Inject layer2 mixins into this instance by reassigning __class__.

        A cached dynamic subclass is reused across instances with the same
        (base_class, layer2) combination so class-creation overhead is paid
        only once.  The mixins are inserted before DSSimulation in the MRO so
        that e.g. SimProcessMixin.gwait overrides SimLiteWaitMixin.gwait.
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
                 layer2=PubSubLayer2, timequeue: type[ITimeQueue] = TQBinTree) -> None:
        if layer2:
            self._load_layer2(layer2)
        self.name = name
        if not inspect.isclass(timequeue) or not issubclass(timequeue, ITimeQueue):
            raise TypeError('timequeue must be a class implementing ITimeQueue.')
        self._timequeue_class = timequeue
        self.names: dict = {}  # stores names of associated components
        if DSComponentSingleton.sim_singleton is None:
            DSComponentSingleton.sim_singleton = self  # The first sim environment will be the first initialized one
        elif not single_instance:
            print('Warning, you are initializing another instance of the simulation.'
                  'This case is supported, but it is not a typical case and you may'
                  'want not intentionally to do so. To suppress this warning, call'
                  'DSSimulation(single_instance=False)')
        self.time: NumericType = 0
        self._restart()

    def __repr__(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name

    def restart(self, time: TimeType = 0) -> None:
        self.time = time
        self._restart()

    def _restart(self) -> None:
        self.time_queue = self._timequeue_class()
        self.now_queue = NowQueue()
        self.num_events: int = 0
        # By default, we use fake subscriber. It will be rewritten on the first 
        self.pid: ISubscriber = void_subscriber

    def compute_time(self, time: TimeType) -> NumericType:
        ''' Convert absolute time value to a relative timeout from now. '''
        if time < self.time:
            raise ValueError('The time is absolute and cannot be lower than now')
        return time - self.time

    def send_object(self, subscriber: ISubscriber, event: EventType) -> EventType:
        ''' Send an event object to a subscriber. Return value from the subscriber. '''

        # We want to kick from this process to another process (see below). However, after
        # returning back to this process, we want to renew our process ID back to be used.
        # We do that by remembering the pid here and restoring at the end.
        pid = self.pid

        try:
            # We want to kick from this process another 'subscriber' process. So we will change
            # the process ID (we call it self.pid). This is needed because if the new
            # created process would schedule a wait cycle for his own, he would like to know his own
            # process ID (see the wait method). That's why we have to set him his PID now.
            # In other words, the subscriber.send() can invoke a context switch
            # without a handler- so this is the context switch handler, currently only
            # changing process ID.
            self.pid = subscriber
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
            self.pid = pid
        return retval

    def schedule_event(self, time: TimeType, event: EventType, subscriber: Optional[ISubscriber] = None) -> EventType:
        ''' Schedules an event object into timequeue. Finally the target process will be signalled. '''
        time = self.time + time
        subscriber = subscriber or self.pid  # schedule to a process or to itself
        self.time_queue.add_element(time, (subscriber, event))
        return event

    def signal(self, event: EventType, subscriber: Optional[ISubscriber] = None) -> None:
        '''Schedule event for immediate dispatch at current simulation time.'''
        subscriber = subscriber or self.pid  # schedule to a process or to itself
        self.now_queue.append((subscriber, event))

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
        self.now_queue = NowQueue(item for item in self.now_queue if item[0] is not subscriber)
        self.time_queue.delete_sub(subscriber)

    def run(self, until: TimeType = float('inf'), future: EventType = object()) -> Tuple[float, int]:
        ''' This is the simulation machine. In a loop it takes first event and process it.
        The loop ends when the queue is empty or when the simulation time is over.
        '''
        ftime = until if until == float('inf') else self.time + self.compute_time(until)
        if self.now_queue:
            self.time_queue.insertleft(self.time, self.now_queue)
        while self.time_queue:
            tevent = self.time_queue.get_first_time()
            if tevent >= ftime:
                retval_time = self.time
                self.time = ftime
                break
            self.time = tevent
            self.now_queue = self.time_queue.pop_first_bucket()

            # Step 2: drain now_queue
            while self.now_queue:
                (subscriber, event_obj) = self.now_queue.popleft()
                # check for the future as well in the now_queue
                if event_obj == future:
                    return self.time, self.num_events
                self.num_events += 1
                self.send_object(subscriber, event_obj)
        else:
            retval_time = self.time
            self.time = ftime
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
