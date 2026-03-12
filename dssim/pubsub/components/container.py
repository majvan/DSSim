# Copyright 2023- majvan (majvan@gmail.com)
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
The file implements the Container simulation component.
'''
from typing import Any, List, Dict, Iterator, Optional, Generator, TYPE_CHECKING
from dssim.base import TimeType, EventType, SignalMixin
from dssim.pubsub.base import CondType, DSAbortException, AlwaysTrue
from dssim.pubsub.components.base import DSStatefulComponent

if TYPE_CHECKING:
    from dssim.simulation import DSSimulation


class Container(DSStatefulComponent, SignalMixin):
    ''' The (FIFO) queue of events is a SW component which can dynamically
    be used to put an event in and get (or wait for- if the queue is empty)
    a queued event.
    Queue does not use any routing of signals.
    '''
    def __init__(self, capacity: Optional[int] = None, *args: Any, **policy_params: Any) -> None:
        ''' Init Container component. No special arguments here. '''
        super().__init__(*args, **policy_params)
        self.capacity = capacity
        self.container: Dict[EventType, int] = {}  # object: count; the dict is used for quick search
        self.size = 0
        # Targeted producers: getters waiting for any object subscribe to tx_nempty;
        # putters and complex-condition getters subscribe to tx_changed.
        # self.tx_changed already defined
        self.tx_nempty = self.sim.publisher(name=self.name + '.tx_nempty')
        self.LAMBDA1 = lambda _: self.size >= 1

    def _available(self, num_items: int) -> bool:
        return self.capacity is None or (self.size + num_items <= self.capacity)

    def _fire_nempty(self) -> None:
        if self.tx_nempty.has_subscribers():
            self.sim.signal(self.tx_nempty, self.tx_nempty)

    def _fire_changed(self) -> None:
        if self.tx_changed.has_subscribers():
            self.sim.signal(self.tx_changed, self.tx_changed)

    def send(self, event: EventType) -> EventType:
        return self.put_nowait(event) is not None

    def put_nowait(self, *obj: EventType) -> Optional[EventType]:
        ''' Put an event into queue. The event can be consumed anytime in the future. '''
        num_items = len(obj)
        if self._available(num_items):
            for item in obj:
                self.container[item] = self.container.get(item, 0) + 1
            self.size += num_items
            self._fire_nempty()
            self._fire_changed()
            retval = obj
        else:
            retval = None
        return retval

    async def put(self, timeout: TimeType = float('inf'), *obj: EventType, **policy_params: Any) -> EventType:
        ''' Put an event into queue. The event can be consumed anytime in the future. '''
        num_items = len(obj)
        with self.sim.consume(self.tx_changed, **policy_params):
            retval = await self.sim.check_and_wait(timeout, cond=lambda e: self._available(num_items))
        if retval is not None:
            for item in obj:
                self.container[item] = self.container.get(item, 0) + 1
            self.size += num_items
            self._fire_nempty()
            self._fire_changed()
        return retval

    def gput(self, timeout: TimeType = float('inf'), *obj: EventType, **policy_params: Any) -> Generator[EventType, EventType, EventType]:
        ''' Put an event into queue. The event can be consumed anytime in the future. '''
        num_items = len(obj)
        with self.sim.consume(self.tx_changed, **policy_params):
            retval = yield from self.sim.check_and_gwait(timeout, cond=lambda e: self._available(num_items))
        if retval is not None:
            for item in obj:
                self.container[item] = self.container.get(item, 0) + 1
            self.size += num_items
            self._fire_nempty()
            self._fire_changed()
        return retval

    def _pop_element(self, element: EventType) -> EventType:
        el_count = self.container.get(element, 0)
        retval = None
        if el_count > 1:
            self.container[element] = el_count - 1
            retval = element
        elif el_count == 1:
            self.container.pop(element)
            retval = element
        return retval

    def remove(self, element: EventType) -> None:
        retval = self._pop_element(element)
        if retval is not None:
            self.size -= 1

    def get_nowait(self) -> Optional[EventType]:
        ''' Get any first object from the container immediately. Returns None if empty. '''
        if self.size == 0:
            return None
        el = next(iter(self.container.keys()))
        retval = self._pop_element(el)
        if retval is not None:
            self.size -= 1
            self._fire_changed()
        return retval

    def get_n_nowait(self, *obj: EventType) -> List[EventType]:
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
            self._fire_changed()
        return retval

    async def get_n(self, timeout: TimeType = float('inf'), *obj: EventType, all_or_nothing: bool = True, **policy_params: Any) -> Optional[List[EventType]]:
        ''' Get requested objects from container.
        @param: all_or_nothing if True, it blocks till all the objects will be in the container and returns them (or timeout)
                               if False, it continuosly grabs the requested objects when available until all collected; it returns collected items
        '''
        if all_or_nothing:
            retval = None
            if len(obj) > 0:
                with self.sim.consume(self.tx_changed, **policy_params):
                    element = await self.sim.check_and_wait(timeout, cond=lambda e: all(el in self.container.keys() for el in obj))  # wait while first element does not match the cond
                    if element is not None:
                        retval = self.get_n_nowait(*obj)
            else:
                with self.sim.consume(self.tx_nempty, **policy_params):
                    # get any object first
                    element = await self.sim.check_and_wait(timeout, cond=lambda e: self.size > 0)  # wait while first element does not match the cond
                    if element is not None:
                        retval = self.get_n_nowait()
        elif len(obj) > 0:
            retval = []
            abs_timeout = self.sim.to_abs_time(timeout)
            while self.sim.time < abs_timeout.to_number():
                with self.sim.consume(self.tx_changed, **policy_params):
                    element = await self.sim.check_and_wait(timeout, cond=lambda e: any(el in self.container.keys() for el in obj))
                if element is None:
                    break
                retval += self.get_n_nowait(*obj)
                if len(retval) == len(obj):
                    break
        else:
            retval = []
        return retval

    async def get(self, timeout: TimeType = float('inf'), **policy_params: Any) -> Optional[List[EventType]]:
        ''' Simplified version of get_n => gets any first object '''
        with self.sim.consume(self.tx_nempty, **policy_params):
            retval = await self.sim.check_and_wait(timeout, cond=self.LAMBDA1)
            if retval is not None:
                el = next(iter(self.container.keys()))
                retval = self._pop_element(el)
                self.size -= 1
                self._fire_changed()
        return retval

    def gget_n(self, timeout: TimeType = float('inf'), *obj: EventType, all_or_nothing: bool = True, **policy_params: Any) -> Generator[EventType, Optional[List[EventType]], Optional[List[EventType]]]:
        ''' Get requested objects from container.
        @param: all_or_nothing if True, it blocks till all the objects will be in the container and returns them (or timeout)
                               if False, it continuosly grabs the requested objects when available until all collected; it returns collected items
        '''
        if all_or_nothing:
            retval = None
            if len(obj) > 0:
                with self.sim.consume(self.tx_changed, **policy_params):
                    element = yield from self.sim.check_and_gwait(timeout, cond=lambda e: all(el in self.container.keys() for el in obj))  # wait while first element does not match the cond
                    if element is not None:
                        retval = self.get_n_nowait(*obj)
            else:
                with self.sim.consume(self.tx_nempty, **policy_params):
                    # get any object first
                    element = yield from self.sim.check_and_gwait(timeout, cond=lambda e: self.size > 0)  # wait while first element does not match the cond
                    if element is not None:
                        retval = self.get_n_nowait()
        elif len(obj) > 0:
            retval = []
            abs_timeout = self.sim.to_abs_time(timeout)
            while self.sim.time < abs_timeout.to_number():
                with self.sim.consume(self.tx_changed, **policy_params):
                    element = yield from self.sim.check_and_gwait(timeout, cond=lambda e: any(el in self.container.keys() for el in obj))
                if element is None:
                    break
                retval += self.get_n_nowait(*obj)
                if len(retval) == len(obj):
                    break
        else:
            retval = []
        return retval

    def gget(self, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, Optional[EventType], Optional[EventType]]:
        ''' Simplified version of gget_n => gets any first object; return the object '''
        with self.sim.consume(self.tx_nempty, **policy_params):
            retval = yield from self.sim.check_and_gwait(timeout, cond=self.LAMBDA1)
            if retval is not None:
                el = next(iter(self.container.keys()))
                retval = self._pop_element(el)
                self.size -= 1
                self._fire_changed()
        return retval

    def _get_tx_endpoint(self, cond):
        return self.tx_nempty if cond is AlwaysTrue else self.tx_changed

    # ---- DSStatefulComponent overrides ---------------------------------------

    def gwait(self, timeout: TimeType = float('inf'), cond: CondType = AlwaysTrue, **policy_params: Any) -> Generator[EventType, EventType, EventType]:
        tx = self._get_tx_endpoint(cond)
        with self.sim.consume(tx, **policy_params):
            retval = yield from self.sim.gwait(timeout, cond=cond)
        return retval

    async def wait(self, timeout: TimeType = float('inf'), cond: CondType = AlwaysTrue, **policy_params: Any) -> EventType:
        tx = self._get_tx_endpoint(cond)
        with self.sim.consume(tx, **policy_params):
            retval = await self.sim.wait(timeout, cond=cond)
        return retval

    def check_and_gwait(self, timeout: TimeType = float('inf'), cond: CondType = AlwaysTrue, **policy_params: Any) -> Generator[EventType, EventType, EventType]:
        tx = self._get_tx_endpoint(cond)
        with self.sim.consume(tx, **policy_params):
            retval = yield from self.sim.check_and_gwait(timeout, cond=cond)
        return retval

    async def check_and_wait(self, timeout: TimeType = float('inf'), cond: CondType = AlwaysTrue, **policy_params: Any) -> EventType:
        tx = self._get_tx_endpoint(cond)
        with self.sim.consume(tx, **policy_params):
            retval = await self.sim.check_and_wait(timeout, cond=cond)
        return retval

    def __len__(self) -> int:
        return self.size

    def __iter__(self) -> Iterator[EventType]:
        ''' Iterator to iterate through all elements which are in the container in a particular time. '''
        elements = []
        for item, count in self.container.items():
            elements += [item] * count
        return iter(elements)


# In the following, self is in fact of type DSAgent, but PyLance makes troubles with variable types
class ContainerMixin:
    async def enter(self: Any, container: Container, timeout: TimeType = float('inf'), **policy_params: Any) -> EventType:
        try:
            retval = await container.put(timeout, self, **policy_params)
        except DSAbortException as exc:
            self.scheduled_process.abort()
        return retval

    def genter(self: Any, container: Container, timeout: TimeType = float('inf'), **policy_params) -> Generator[EventType, EventType, EventType]:
        try:
            retval = yield from container.gput(timeout, self, **policy_params)
        except DSAbortException as exc:
            self.scheduled_process.abort()
        return retval

    def enter_nowait(self: Any, container: Container) -> Optional[EventType]:
        retval = container.put_nowait(self)
        return retval

    def leave(self: Any, container: Container) -> None:
        container.remove(self)

    async def pop(self: Any, container: Container, timeout: TimeType = float('inf'), **policy_params: Any) -> Optional[EventType]:
        try:
            retval = await container.get(timeout, **policy_params)
        except DSAbortException as exc:
            self.scheduled_process.abort()
        return retval

    def gpop(self: Any, container: Container, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, EventType, EventType]:
        try:
            retval = yield from container.gget(timeout, **policy_params)
        except DSAbortException as exc:
            self.scheduled_process.abort()
        return retval

    def pop_nowait(self: Any, container: Container) -> EventType:
        return container.get_nowait()


# In the following, self is in fact of type DSSimulation, but PyLance makes troubles with variable types
class SimContainerMixin:
    def container(self: Any, *args: Any, **kwargs: Any) -> Container:
        sim: 'DSSimulation' = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in container() method should be set to the same simulation instance.')
        return Container(*args, **kwargs, sim=sim)
