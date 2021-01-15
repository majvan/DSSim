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
from typing import Deque, Optional, Tuple, Union
from bisect import bisect_right
from dssim.base import EventType, ISubscriber
from dssim.timequeue.base import ITimeQueue
from collections import deque

TimeType = float
ElementType = Tuple[ISubscriber, Union[EventType, ISubscriber]]


class _VoidSubscriber:
    ''' Sentinel subscriber returned by get0() when the queue is empty. '''
    def send(self, event: EventType) -> None:
        raise RuntimeError('A void subscriber is never expected to be called.')

_void_subscriber = _VoidSubscriber()


class NowQueue(deque):
    ''' Special queue for "now-time" events.

    It does not hold event times and is used purely as FIFO for events
    scheduled at current simulation time.
    '''
    pass


class TQBisect(ITimeQueue):
    ''' Maintains a queue of (time, deque(elements)) buckets sorted by time.

    Each bucket stores all events with the same timestamp in FIFO order:
        (time, deque([(subscriber, event), ...]))

    This lets same-time events be drained from the first bucket without a
    separate now-queue structure.
    '''
    def __init__(self) -> None:
        self._queue: Deque[Tuple[TimeType, Deque[ElementType]]] = deque()

    def add_element(self, time: float, element: ElementType) -> None:
        '''Add one non-zero-time (subscriber,event) element at absolute `time`.'''
        if not self._queue:
            self._queue.append((time, deque([element])))
            return

        if time > self._queue[-1][0]:
            self._queue.append((time, deque([element])))
            return

        if time == self._queue[-1][0]:
            self._queue[-1][1].append(element)
            return

        i = bisect_right(self._queue, time, key=lambda x: x[0])
        if i > 0 and self._queue[i - 1][0] == time:
            self._queue[i - 1][1].append(element)
        else:
            self._queue.insert(i, (time, deque([element])))

    def get_first_time(self) -> TimeType:
        '''Return timestamp of the first bucket (expected deque is not empty).'''
        return self._queue[0][0]

    def pop_first_bucket(self) -> Deque[ElementType]:
        '''Pop and return the first bucket deque (expected deque is not empty).'''
        return self._queue.popleft()[1]

    def insertleft(self, time: TimeType, events: Deque[ElementType]) -> None:
        '''Insert a prepared bucket at `time` preserving same-time FIFO order.'''
        if events:
            if not self._queue:
                self._queue.appendleft((time, events))
                return
            first_time, first_events = self._queue[0]
            if first_time == time:
                # Preserve already-scheduled order at this timestamp.
                first_events.extend(events)
                return
            if first_time > time:
                self._queue.appendleft((time, events))
                return
            # Defensive fallback: keep time ordering if called with a later time.
            i = bisect_right(self._queue, time, key=lambda x: x[0])
            if i > 0 and self._queue[i - 1][0] == time:
                self._queue[i - 1][1].extend(events)
            else:
                self._queue.insert(i, (time, events))

    def delete_sub(self, sub: ISubscriber) -> None:
        '''Delete all queued events targeted to the provided subscriber.'''
        new_queue: Deque[Tuple[TimeType, Deque[ElementType]]] = deque()
        for t, events in self._queue:
            filtered = deque(e for e in events if e[0] is not sub)
            if filtered:
                new_queue.append((t, filtered))
        self._queue = new_queue

    def delete_val(self, val: ElementType) -> None:
        ''' Delete all the objects which have the provided value. '''
        new_queue: Deque[Tuple[TimeType, Deque[ElementType]]] = deque()
        for t, events in self._queue:
            filtered = deque(e for e in events if e != val)
            if filtered:
                new_queue.append((t, filtered))
        self._queue = new_queue

    def event_count(self) -> int:
        '''Get number of queued events (not number of time buckets).'''
        return sum(len(events) for _, events in self._queue)

    def __bool__(self) -> bool:
        '''O(1) non-empty check used by the simulation hot path.'''
        return bool(self._queue)
