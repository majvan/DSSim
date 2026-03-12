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
Queue of events and logic around it.
The queue class also maintains current absolute time.
'''
from typing import Tuple, Union
from bisect import bisect_right
from dssim.base import EventType, ISubscriber
from collections import deque

TimeType = float
ElementType = Tuple[ISubscriber, Union[EventType, ISubscriber]]


class _VoidSubscriber:
    ''' Sentinel subscriber returned by get0() when the queue is empty. '''
    def send(self, event: EventType) -> None:
        raise RuntimeError('A void subscriber is never expected to be called.')

_void_subscriber = _VoidSubscriber()


class ZeroTimeQueue(deque):
    ''' This is a special queue intended for higher throughput. It does not hold the time
    and is solely used as a FIFO queue.
    The reason: many components schedule with t=0; the processing of the events with zero
    time is boosted with this queue.
    Another possibility in the future is to use thread - safe queue because processing
    the equal-time (in this case zero-time) events can be done in parallel.
    '''
    pass


class TimeQueue:
    ''' Maintains a queue of (time, element) pairs sorted by time.
    A single deque of tuples gives O(1) popleft and better cache locality
    compared to two parallel deques.
    Insertion appends for the common case (non-decreasing times) and falls
    back to bisect + deque.insert() for out-of-order events.
    '''
    def __init__(self) -> None:
        self._queue: deque = deque()  # deque of (time, element) tuples

    def add_element(self, time: float, element: ElementType) -> None:
        ''' Add an element to the queue at a time_delta from current time. '''
        if not self._queue or time >= self._queue[-1][0]:
            self._queue.append((time, element))
        else:
            i = bisect_right(self._queue, time, key=lambda x: x[0])
            self._queue.insert(i, (time, element))

    def get0(self) -> Tuple[TimeType, ElementType]:
        ''' Get the first element from the queue. '''
        if self._queue:
            return self._queue[0]
        # If there is nothing in the queue, report virtual None object in the inifinite time.
        # Note: another solution would be to add this virtual element into the queue. In that
        # case the bisect function would take a little more time when adding an element.
        return float("inf"), (_void_subscriber, None)

    def pop(self) -> Tuple[TimeType, ElementType]:
        ''' Pop the first element from the queue and return it to the caller. '''
        return self._queue.popleft()

    def delete_sub(self, sub: ISubscriber) -> None:
        '''Delete all queued events targeted to the provided subscriber.'''
        self._queue = deque((t, e) for t, e in self._queue if e[0] is not sub)

    def delete_val(self, val: ElementType) -> None:
        ''' Delete all the objects which have the provided value. '''
        self._queue = deque((t, e) for t, e in self._queue if e != val)

    def __len__(self) -> int:
        ''' Get length of the queue. '''
        return len(self._queue)
