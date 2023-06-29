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
from typing import Any, List, Dict, Optional, Generator, TYPE_CHECKING
from dssim.base import TimeType, EventType, SignalMixin, DSAbortException
from dssim.pubsub import DSConsumer, DSProducer


if TYPE_CHECKING:
    from dssim.simulation import DSSimulation


class Container(DSConsumer, SignalMixin):
    ''' The (FIFO) queue of events is a SW component which can dynamically
    be used to put an event in and get (or wait for- if the queue is empty)
    a queued event.
    Queue does not use any routing of signals.
    '''
    def __init__(self, capacity: Optional[int] = None, *args: Any, **kwargs: Any) -> None:
        ''' Init Queue component. No special arguments here. '''
        super().__init__(*args, **kwargs)
        self.tx_changed = self.sim.producer(name=self.name+'.tx')
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
            return None
        return element

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
            while self.sim.time < float(abs_timeout):
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
            while self.sim.time < float(abs_timeout):
                element = yield from self.sim.check_and_gwait(timeout, cond=lambda e: any(el in self.container.keys() for el in obj))
                if element is None:
                    break
                retval += self.get_nowait(*obj)
                if len(retval) == len(obj):
                    break
        else:
            retval = []
        return retval

    def __len__(self):
        return self.size

    def __iter__(self):
        ''' Iterator to iterate through all elements which are in the container in a particular time. '''
        elements = []
        for item, count in self.container.items():
            elements += [item] * count
        return iter(elements)


# In the following, self is in fact of type DSSimulation, but PyLance makes troubles with variable types
class SimContainerMixin:
    def container(self: Any, *args: Any, **kwargs: Any) -> Container:
        sim: DSSimulation = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in container() method should be set to the same simulation instance.')
        return Container(*args, **kwargs, sim=sim)
