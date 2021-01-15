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
from typing import Deque, Dict, List, Optional, Tuple, Union
from heapq import heappop, heappush
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


class TQBinTree(ITimeQueue):
    ''' Maintains a queue of (time, deque(elements)) buckets sorted by time.

    Each bucket stores all events with the same timestamp in FIFO order:
        (time, deque([(subscriber, event), ...]))

    This lets same-time events be drained from the first bucket without a
    separate now-queue structure.
    '''
    def __init__(self) -> None:
        # Internal representation uses a min-heap of timestamps plus one FIFO
        # bucket (deque) per timestamp for O(log n) insertion of new times.
        self._heap: List[TimeType] = []
        self._buckets: Dict[TimeType, Deque[ElementType]] = {}

    @property
    def _queue(self) -> Deque[Tuple[TimeType, Deque[ElementType]]]:
        '''Compatibility view used by tests/debugging.

        Returns buckets sorted by time. Runtime code should use dedicated
        methods on TimeQueue instead of traversing this view directly.
        '''
        return deque((t, self._buckets[t]) for t in sorted(self._buckets))

    def add_element(self, time: float, element: ElementType) -> None:
        '''Add one non-zero-time (subscriber,event) element at absolute `time`.'''
        bucket = self._buckets.get(time)
        if bucket is not None:
            bucket.append(element)
            return
        self._buckets[time] = deque([element])
        heappush(self._heap, time)

    def get_first_time(self) -> TimeType:
        '''Return timestamp of the first bucket (expected deque is not empty).'''
        while self._heap and self._heap[0] not in self._buckets:
            heappop(self._heap)
        return self._heap[0]

    def pop_first_bucket(self) -> Deque[ElementType]:
        '''Pop and return the first bucket deque (expected deque is not empty).'''
        while self._heap:
            t = heappop(self._heap)
            bucket = self._buckets.pop(t, None)
            if bucket is not None:
                return bucket
        return deque()

    def insertleft(self, time: TimeType, events: Deque[ElementType]) -> None:
        '''Insert a prepared bucket at `time` preserving same-time FIFO order.'''
        if events:
            bucket = self._buckets.get(time)
            if bucket is not None:
                # Preserve already-scheduled order at this timestamp.
                bucket.extend(events)
            else:
                self._buckets[time] = events
                heappush(self._heap, time)

    def delete_sub(self, sub: ISubscriber) -> None:
        '''Delete all queued events targeted to the provided subscriber.'''
        new_buckets: Dict[TimeType, Deque[ElementType]] = {}
        for t, events in self._buckets.items():
            filtered = deque(e for e in events if e[0] is not sub)
            if filtered:
                new_buckets[t] = filtered
        self._buckets = new_buckets
        self._heap = sorted(new_buckets.keys())

    def delete_val(self, val: ElementType) -> None:
        ''' Delete all the objects which have the provided value. '''
        new_buckets: Dict[TimeType, Deque[ElementType]] = {}
        for t, events in self._buckets.items():
            filtered = deque(e for e in events if e != val)
            if filtered:
                new_buckets[t] = filtered
        self._buckets = new_buckets
        self._heap = sorted(new_buckets.keys())

    def event_count(self) -> int:
        '''Get number of queued events (not number of time buckets).'''
        return sum(len(events) for events in self._buckets.values())

    def __bool__(self) -> bool:
        '''O(1) non-empty check used by the simulation hot path.'''
        return bool(self._buckets)
