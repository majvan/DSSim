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
from typing import Any, List, Dict, Iterator, Union, Optional, Generator, TYPE_CHECKING
from dssim.base import NumericType, TimeType, EventType, CondType, SignalMixin, DSAbortException, DSStatefulComponent
from dssim.pubsub import DSConsumer, DSProducer


if TYPE_CHECKING:
    from dssim.simulation import DSSimulation


class Container(DSStatefulComponent, SignalMixin):
    ''' The (FIFO) queue of events is a SW component which can dynamically
    be used to put an event in and get (or wait for- if the queue is empty)
    a queued event.
    Queue does not use any routing of signals.
    '''
    def __init__(self, capacity: Optional[int] = None, *args: Any, **kwargs: Any) -> None:
        ''' Init Queue component. No special arguments here. '''
        super().__init__(*args, **kwargs)
        self.capacity = capacity
        self.container: Dict[EventType, int] = {}  # object: count; the dict is used for quick search
        self.size = 0

    def _available(self, num_items: int) -> bool:
        return self.capacity is None or (len(self) + num_items <= self.capacity)

    def send(self, event: EventType) -> EventType:
        return self.put_nowait(event) is not None

    def put_nowait(self, *obj: EventType) -> Optional[EventType]:
        ''' Put an event into queue. The event can be consumed anytime in the future. '''
        num_items = len(obj)
        if self._available(num_items):
            for item in obj:
                self.container[item] = self.container.get(item, 0) + 1
            self.size += num_items
            self.tx_changed.schedule_event(0, 'queue changed')
            retval = obj
        else:
            retval = None
        return retval

    async def put(self, timeout: TimeType = float('inf'), *obj: EventType) -> EventType:
        ''' Put an event into queue. The event can be consumed anytime in the future. '''
        num_items = len(obj)
        with self.sim.consume(self.tx_changed):
            retval = await self.sim.check_and_wait(timeout, cond=lambda e: self._available(num_items))
        if retval is not None:
            for item in obj:
                self.container[item] = self.container.get(item, 0) + 1
            self.size += num_items
            self.tx_changed.schedule_event(0, 'queue changed')
        return retval

    def gput(self, timeout: TimeType = float('inf'), *obj: EventType) -> Generator[EventType, EventType, EventType]:
        ''' Put an event into queue. The event can be consumed anytime in the future. '''
        num_items = len(obj)
        with self.sim.consume(self.tx_changed):
            retval = yield from self.sim.check_and_gwait(timeout, cond=lambda e: self._available(num_items))
        if retval is not None:
            for item in obj:
                self.container[item] = self.container.get(item, 0) + 1
            self.size += num_items
            self.tx_changed.schedule_event(0, 'queue changed')
        return retval
    
    def _pop_element(self, element: EventType) -> EventType:
        el_count = self.container.get(element, 0)
        if el_count > 1:
            self.container[element] = el_count - 1
        elif el_count == 1:
            self.container.pop(element)
        else:
            retval = None
        return element
    
    def remove(self, element: EventType) -> None:
        retval = self._pop_element(element)
        if retval is not None:
            self.size -= 1

    def get_nowait(self, *obj: EventType) -> List[EventType]:
        ''' Get requested object from the container - as many as possible. '''
        retval = []
        if len(obj) > 0:
            for el in obj:
                el = self._pop_element(el)
                if el is not None:
                    retval.append(el)
        else:
            el = next(iter(self.container.keys()))
            el = self._pop_element(el)
            if el is not None:
                retval.append(el)
        num_items = len(retval)
        if num_items > 0:
            self.size -= num_items
            self.tx_changed.schedule_event(0, 'queue changed')
        return retval
    
    async def get(self, timeout: TimeType = float('inf'), *obj: EventType, all_or_nothing: bool = True) -> Optional[List[EventType]]:
        ''' Get requested objects from container.
        @param: all_or_nothing if True, it blocks till all the objects will be in the container and returns them (or timeout)
                               if False, it continuosly grabs the requested objects when available until all collected; it returns collected items
        '''
        if all_or_nothing:
            retval = None
            with self.sim.consume(self.tx_changed):
                if len(obj) > 0:
                    element = await self.sim.check_and_wait(timeout, cond=lambda e: all(el in self.container.keys() for el in obj))  # wait while first element does not match the cond
                    if element is not None:
                        retval = self.get_nowait(*obj)
                else:
                    # get any object first
                    element = await self.sim.check_and_wait(timeout, cond=lambda e: len(self) > 0)  # wait while first element does not match the cond                    
                    if element is not None:
                        retval = self.get_nowait()
        elif len(obj) > 0:
            retval = []
            abs_timeout = self.sim.to_abs_time(timeout)
            while self.sim.time < abs_timeout.to_number():
                element = await self.sim.check_and_wait(timeout, cond=lambda e: any(el in self.container.keys() for el in obj))
                if element is None:
                    break
                retval += self.get_nowait(*obj)
                if len(retval) == len(obj):
                    break
        else:
            retval = []
        return retval

    def gget(self, timeout: TimeType = float('inf'), *obj: EventType, all_or_nothing: bool = True) -> Generator[EventType, Optional[List[EventType]], Optional[List[EventType]]]:
        ''' Get requested objects from container.
        @param: all_or_nothing if True, it blocks till all the objects will be in the container and returns them (or timeout)
                               if False, it continuosly grabs the requested objects when available until all collected; it returns collected items
        '''
        if all_or_nothing:
            retval = None
            with self.sim.consume(self.tx_changed):
                if len(obj) > 0:
                    element = yield from self.sim.check_and_gwait(timeout, cond=lambda e: all(el in self.container.keys() for el in obj))  # wait while first element does not match the cond
                    if element is not None:
                        retval = self.get_nowait(*obj)
                else:
                    # get any object first
                    element = yield from self.sim.check_and_gwait(timeout, cond=lambda e: len(self) > 0)  # wait while first element does not match the cond                    
                    if element is not None:
                        retval = self.get_nowait()
        elif len(obj) > 0:
            retval = []
            abs_timeout = self.sim.to_abs_time(timeout)
            while self.sim.time < abs_timeout.to_number():
                element = yield from self.sim.check_and_gwait(timeout, cond=lambda e: any(el in self.container.keys() for el in obj))
                if element is None:
                    break
                retval += self.get_nowait(*obj)
                if len(retval) == len(obj):
                    break
        else:
            retval = []
        return retval

    def __len__(self) -> int:
        return self.size

    def __iter__(self) -> Iterator[EventType]:
        ''' Iterator to iterate through all elements which are in the container in a particular time. '''
        elements = []
        for item, count in self.container.items():
            elements += [item] * count
        return iter(elements)


class Queue(DSStatefulComponent, SignalMixin):
    ''' The (FIFO) queue of events is a SW component which can dynamically
    be used to put an event in and get (or wait for- if the queue is empty)
    a queued event.
    Queue does not use any routing of signals.
    '''
    def __init__(self, capacity: NumericType = float('inf'), *args: Any, **kwargs: Any) -> None:
        ''' Init Queue component. No special arguments here. '''
        super().__init__(*args, **kwargs)
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

    def __setitem__(self, index: int, data: EventType) -> None:
        self.queue[index] = data
        self.tx_changed.schedule_event(0, 'queue changed')

    def __iter__(self) -> Iterator[EventType]:
        return iter(self.queue)
    
# In the following, self is in fact of type DSProcessComponent, but PyLance makes troubles with variable types
class ContainerMixin:
    async def enter(self: Any, container: Union[Queue, Container], timeout: TimeType = float('inf')) -> EventType:
        try:
            retval = await container.put(timeout, self)
        except DSAbortException as exc:
            self.scheduled_process.abort()
        return retval

    def genter(self: Any, container: Union[Queue, Container], timeout: TimeType = float('inf')) -> Generator[EventType, EventType, EventType]:
        try:
            retval = yield from container.gput(timeout, self)
        except DSAbortException as exc:
            self.scheduled_process.abort()
        return retval

    def enter_nowait(self: Any, container: Union[Queue, Container]) -> Optional[EventType]:
        retval = container.put_nowait(self)
        return retval

    def leave(self: Any, container: Union[Queue, Container]) -> None:
        container.remove(self)

    async def pop(self: Any, container: Union[Queue, Container], timeout: TimeType = float('inf')) -> Optional[EventType]:
        try:
            elements = await container.get(timeout)
            if elements is None:
                retval = None
            else:
                assert len(elements) == 1
                retval = elements[0]
        except DSAbortException as exc:
            self.scheduled_process.abort()
        return retval

    def gpop(self: Any, container: Union[Queue, Container], timeout: TimeType = float('inf')) -> Generator[EventType, EventType, EventType]:
        try:
            elements = yield from container.gget(timeout)
            if elements is None:
                retval = None
            else:
                assert len(elements) == 1
                retval = elements[0]
        except DSAbortException as exc:
            self.scheduled_process.abort()
        return retval

    def pop_nowait(self: Any, container: Union[Queue, Container]) -> EventType:
        elements = container.get_nowait()
        if elements is None:
            retval = None
        else:
            assert len(elements) == 1
            retval = elements[0]
        return retval


# In the following, self is in fact of type DSSimulation, but PyLance makes troubles with variable types
class SimContainerMixin:
    def container(self: Any, *args: Any, **kwargs: Any) -> Container:
        sim: DSSimulation = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in container() method should be set to the same simulation instance.')
        return Container(*args, **kwargs, sim=sim)


# In the following, self is in fact of type DSSimulation, but PyLance makes troubles with variable types
class SimQueueMixin:
    def queue(self: Any, *args: Any, **kwargs: Any) -> Queue:
        sim: DSSimulation = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in queue() method should be set to the same simulation instance.')
        return Queue(*args, **kwargs, sim=sim)
