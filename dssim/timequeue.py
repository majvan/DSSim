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
Queue of events and logic around it.
The queue class also maintains current absolute time.
'''
from typing import List, Tuple, Union, Callable, TYPE_CHECKING
from bisect import bisect_right
from dssim.base import EventType
from dssim.pubsub import void_consumer

if TYPE_CHECKING:
    from dssim.pubsub import DSConsumer

TimeType = float
ElementType = Tuple["DSConsumer", Union[EventType, "DSConsumer"]]

class TimeQueue:
    ''' Maintains a list (queue) of objects (elements) associated with absolute time
    and provides methods for the queue.
    We have a tuple (absolute time, element) for the queue, but internally we are managing
    two queues, which have always the same size and they are ordered by an absolute time.
    '''
    def __init__(self) -> None:
        self.timequeue: List[TimeType] = []
        self.elementqueue: List[ElementType] = []

    def add_element(self, time: float, element: ElementType) -> None:
        ''' Add an element to the queue at a time_delta from current time. '''
        time = time
        i = bisect_right(self.timequeue, time)
        self.timequeue.insert(i, time)
        self.elementqueue.insert(i, element)

    def get0(self) -> Tuple[TimeType, ElementType]:
        ''' Get the first element from the queue. '''
        if self.timequeue:
            return self.timequeue[0], self.elementqueue[0]
        # If there is nothing in the queue, report virtual None object in the inifinite time.
        # Note: another solution would be to add this virtual element into the queue. In that
        # case the bisect function would take a little more time when adding an element.
        return float("inf"), (void_consumer, None)

    def pop(self) -> Tuple[TimeType, ElementType]:
        ''' Pop the first element from the queue and return it to the caller. '''
        time, element = self.timequeue.pop(0), self.elementqueue.pop(0)
        return time, element

    def delete(self, cond: Callable) -> None:
        ''' Delete all the objects which fit to the condition from the queue. '''
        new_timequeue = []
        new_elementqueue = []
        for time, element in zip(self.timequeue, self.elementqueue):
            if not cond(element):
                new_timequeue.append(time)
                new_elementqueue.append(element)
        self.timequeue = new_timequeue
        self.elementqueue = new_elementqueue

    def __len__(self) -> int:
        ''' Get length of the queue. '''
        return len(self.timequeue)
