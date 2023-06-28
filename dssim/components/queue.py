# Copyright 2021 NXP Semiconductors
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
A queue of events with runtime flexibility of put / get events.
'''
from typing import Any, List, Optional, Generator, TYPE_CHECKING
from dssim.base import TimeType, EventType, CondType, SignalMixin, DSAbortException
from dssim.pubsub import DSConsumer, DSProducer


if TYPE_CHECKING:
    from dssim.simulation import DSSimulation


class Queue(DSConsumer, SignalMixin):
    ''' The (FIFO) queue of events is a SW component which can dynamically
    be used to put an event in and get (or wait for- if the queue is empty)
    a queued event.
    Queue does not use any routing of signals.
    '''
    def __init__(self, capacity: float = float('inf'), *args: Any, **kwargs: Any) -> None:
        ''' Init Queue component. No special arguments here. '''
        super().__init__(*args, **kwargs)
        self.tx_changed = self.sim.producer(name=self.name+'.tx')
        self.capacity = capacity
        self.queue: List[EventType] = []

    def send(self, event: EventType) -> EventType:
        return self.put_nowait(event) is not None

    def put_nowait(self, *obj: EventType) -> Optional[EventType]:
        ''' Put an event into queue. The event can be consumed anytime in the future. '''
        if len(self) + len(obj) <= self.capacity:
            self.queue += list(obj)
            self.tx_changed.schedule_event(0, 'queue changed')
            retval = obj
        else:
            retval = None
        return retval

    async def put(self, timeout: TimeType = float('inf'), *obj: EventType) -> EventType:
        ''' Put an event into queue. The event can be consumed anytime in the future. '''
        with self.sim.consume(self.tx_changed):
            retval = await self.sim.check_and_wait(timeout, cond=lambda e:len(self) + len(obj) <= self.capacity)
        if retval is not None:
            self.queue += list(obj)
            self.tx_changed.schedule_event(0, 'queue changed')
        return retval

    def gput(self, timeout: TimeType = float('inf'), *obj: EventType) -> Generator[EventType, EventType, EventType]:
        ''' Put an event into queue. The event can be consumed anytime in the future. '''
        with self.sim.consume(self.tx_changed):
            retval = yield from self.sim.check_and_gwait(timeout, cond=lambda e:len(self) + len(obj) <= self.capacity)
        if retval is not None:
            self.queue += list(obj)
            self.tx_changed.schedule_event(0, 'queue changed')
        return retval

    def get_nowait(self, amount: int = 1, cond: CondType = lambda e: True) -> Optional[List[EventType]]:
        if len(self) >= amount and cond(self.queue[:amount]):
            retval = self.queue[:amount]
            self.queue = self.queue[amount + 1:]
            self.tx_changed.schedule_event(0, 'queue changed')
        else:
            retval = None
        return retval

    async def get(self, timeout: TimeType = float('inf'), amount: int =1, cond: CondType = lambda e: True) -> Optional[List[EventType]]:
        ''' Get an event from queue. If the queue is empty, wait for the closest event. '''
        with self.sim.consume(self.tx_changed):
            element = await self.sim.check_and_wait(timeout, cond=lambda e:len(self) >= amount and cond(self.queue[0]))  # wait while first element does not match the cond
        if element is None:
            retval = None
        else:
            retval = self.queue[:amount]
            self.queue = self.queue[amount:]
            self.tx_changed.schedule_event(0, 'queue changed')
        return retval

    def gget(self, timeout: TimeType = float('inf'), amount: int = 1, cond: CondType = lambda e: True) -> Generator[EventType, Optional[List[EventType]], Optional[List[EventType]]]:
        ''' Get an event from queue. If the queue is empty, wait for the closest event. '''
        with self.sim.consume(self.tx_changed):
            element = yield from self.sim.check_and_gwait(timeout, cond=lambda e:len(self) >= amount and cond(self.queue[0]))  # wait while first element does not match the cond
        if element is None:
            retval = None
        else:
            retval = self.queue[:amount]
            self.queue = self.queue[amount:]
            self.tx_changed.schedule_event(0, 'queue changed')
        return retval

    def pop(self, index: int = 0, default: Optional[EventType] = None) -> Optional[EventType]:
        retval = None
        if len(self.queue) > index:
            try:
                retval = self.queue.pop(index)
                self.tx_changed.schedule_event(0, 'queue changed')
            except IndexError as e:
                retval = default
        return retval

    def remove(self, cond: CondType) -> None:
        ''' Removes event(s) from queue '''
        # Get list of elements to be removed
        length = len(self.queue)
        if length > 0:
            # Remove all others except the first one
            self.queue = [e for e in self.queue if not ((callable(cond) and cond(e) or (cond == e)))]
            # now find what we may emit: "queue changed"
            if length != len(self.queue):
                self.tx_changed.schedule_event(0, 'queue changed')

    def __len__(self):
        return len(self.queue)

    def __getitem__(self, index: int) -> EventType:
        return self.queue[index]

    def __setitem__(self, index, data):
        self.queue[index] = data
        self.tx_changed.schedule_event(0, 'queue changed')

    def __iter__(self):
        return iter(self.queue)


# In the following, self is in fact of type DSProcessComponent, but PyLance makes troubles with variable types
class QueueMixin:
    async def enter(self: Any, queue: Queue, timeout: TimeType = float('inf')) -> EventType:
        try:
            retval = await queue.put(timeout, self)
        except DSAbortException as exc:
            self.scheduled_process.abort()
        return retval

    def genter(self: Any, queue: Queue, timeout: TimeType = float('inf')) -> Generator[EventType, EventType, EventType]:
        try:
            retval = yield from queue.gput(timeout, self)
        except DSAbortException as exc:
            self.scheduled_process.abort()
        return retval

    def enter_nowait(self: Any, queue: Queue) -> EventType:
        retval = queue.put_nowait(self)
        return retval

    def leave(self: Any, queue: Queue) -> None:
        queue.remove(self)

    async def pop(self: Any, queue: Queue, timeout: TimeType = float('inf')) -> Optional[EventType]:
        try:
            elements = await queue.get(timeout)
            if elements is None:
                retval = None
            else:
                assert len(elements) == 1
                retval = elements[0]
        except DSAbortException as exc:
            self.scheduled_process.abort()
        return retval

    def gpop(self: Any, queue: Queue, timeout: TimeType = float('inf')) -> Generator[EventType, EventType, EventType]:
        try:
            elements = yield from queue.gget(timeout)
            if elements is None:
                retval = None
            else:
                assert len(elements) == 1
                retval = elements[0]
        except DSAbortException as exc:
            self.scheduled_process.abort()
        return retval

    def pop_nowait(self: Any, queue: Queue) -> EventType:
        elements = queue.get_nowait()
        if elements is None:
            retval = None
        else:
            assert len(elements) == 1
            retval = elements[0]
        return retval


# In the following, self is in fact of type DSSimulation, but PyLance makes troubles with variable types
class SimQueueMixin:
    def queue(self: Any, *args: Any, **kwargs: Any) -> Queue:
        sim: DSSimulation = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in queue() method should be set to the same simulation instance.')
        return Queue(*args, **kwargs, sim=sim)
