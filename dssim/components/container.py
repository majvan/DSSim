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
The file implements container and queue components.
'''
from collections import deque
from typing import Any, List, Dict, Iterator, Union, Optional, Generator, TYPE_CHECKING
from dssim.base import NumericType, TimeType, EventType, CondType, SignalMixin, DSAbortException
from dssim.components.base import DSStatefulComponent


if TYPE_CHECKING:
    from dssim.simulation import DSSimulation


class DSQueue:
    '''A performant ordered collection for simulation use.

    DSQueue provides O(1) head/tail access and O(1) append/popleft operations
    using a deque internally.  It is a plain data structure (no simulation
    awareness) designed to be composed into higher-level simulation components.
    '''

    def __init__(self) -> None:
        self._data: deque = deque()

    # ---- standard sequence protocol ----------------------------------------

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self) -> Iterator:
        return iter(list(self._data)) # make a copy to be able to alter the _data in a loop

    def __bool__(self) -> bool:
        return bool(self._data)

    def __contains__(self, item: Any) -> bool:
        return item in self._data

    def __repr__(self) -> str:
        return f'DSQueue({list(self._data)})'

    def __getitem__(self, index: int) -> Any:
        return self._data[index]

    def __setitem__(self, index: int, value: Any) -> None:
        self._data[index] = value

    # ---- convenience properties --------------------------------------------

    @property
    def head(self) -> Any:
        '''First item (FIFO front). Returns None when empty.'''
        return self._data[0] if self._data else None

    @property
    def tail(self) -> Any:
        '''Last item (FIFO rear). Returns None when empty.'''
        return self._data[-1] if self._data else None

    # ---- mutation -----------------------------------------------------------

    def append(self, item: Any) -> Any:
        '''Add item to tail (standard FIFO enqueue). O(1).'''
        self._data.append(item)
        return item

    def appendleft(self, item: Any) -> Any:
        '''Add item to head (priority enqueue). O(1).'''
        self._data.appendleft(item)
        return item

    def pop(self) -> Any:
        '''Remove and return item from tail. O(1). Raises IndexError if empty.'''
        return self._data.pop()

    def popleft(self) -> Any:
        '''Remove and return item from head (FIFO dequeue). O(1). Raises IndexError if empty.'''
        return self._data.popleft()

    # ---- policy interface (override in subclasses) -------------------------

    def enqueue(self, item: Any) -> Any:
        '''Policy hook: add item to collection. Default: FIFO (append to tail).'''
        return self.append(item)

    def dequeue(self) -> Any:
        '''Policy hook: remove and return next item. Default: FIFO (from head).'''
        return self.popleft()

    def peek(self) -> Any:
        '''Policy hook: return next item without removing it. Default: FIFO (head).'''
        return self.head

    def pop_at(self, index: int) -> Any:
        '''Remove and return item at given index. O(n).'''
        self._data.rotate(-index)
        item = self._data.popleft()
        self._data.rotate(index)
        return item

    def remove(self, item: Any) -> None:
        '''Remove first occurrence of item. O(n). Raises ValueError if not found.'''
        self._data.remove(item)

    def remove_if(self, cond: CondType) -> bool:
        '''Remove all items matching condition callable. Returns True if any were removed.'''
        to_remove = [e for e in self._data if cond(e)]
        for item in to_remove:
            self._data.remove(item)
        return bool(to_remove)

    def clear(self) -> None:
        '''Remove all items.'''
        self._data.clear()


class DSLifoQueue(DSQueue):
    '''LIFO (stack) variant of DSQueue. Items are dequeued in reverse insertion order.'''

    def dequeue(self) -> Any:
        '''Remove and return item from tail (LIFO pop). O(1).'''
        return self.pop()

    def peek(self) -> Any:
        '''Return item at tail without removing it. O(1).'''
        return self.tail


class DSKeyQueue(DSQueue):
    '''DSQueue variant that maintains items in ascending order of a key function.

    The item with the smallest key value is always at the head and dequeued first
    (min-priority semantics).  Use ``key=lambda item: -item.priority`` to get
    max-priority behaviour.

    ``enqueue`` performs a sorted insertion (O(n)); ``dequeue`` and ``peek``
    operate on the head in O(1).
    '''

    def __init__(self, key: Any = lambda item: item) -> None:
        super().__init__()
        self._key = key

    def enqueue(self, item: Any) -> Any:
        '''Insert item at the correct sorted position. O(n).'''
        key_val = self._key(item)
        for i, existing in enumerate(self._data):
            if self._key(existing) > key_val:
                self._data.insert(i, item)
                return item
        self._data.append(item)
        return item


class Container(DSStatefulComponent, SignalMixin):
    ''' The (FIFO) queue of events is a SW component which can dynamically
    be used to put an event in and get (or wait for- if the queue is empty)
    a queued event.
    Queue does not use any routing of signals.
    '''
    def __init__(self, capacity: Optional[int] = None, *args: Any, **policy_params: Any) -> None:
        ''' Init Queue component. No special arguments here. '''
        super().__init__(*args, **policy_params)
        self.capacity = capacity
        self.container: Dict[EventType, int] = {}  # object: count; the dict is used for quick search
        self.size = 0
        # Targeted producers: getters waiting for any object subscribe to tx_nempty;
        # putters and complex-condition getters subscribe to tx_changed.
        # self.tx_changed already defined
        self.tx_nempty = self.sim.producer(name=self.name + '.tx_nempty')

    def _available(self, num_items: int) -> bool:
        return self.capacity is None or (len(self) + num_items <= self.capacity)

    def _fire_nempty(self) -> None:
        if self.tx_nempty.has_subscribers():
            self.sim.schedule_event(0, self.tx_nempty, self.tx_nempty)

    def _fire_changed(self) -> None:
        if self.tx_changed.has_subscribers():
            self.sim.schedule_event(0, self.tx_changed, self.tx_changed)

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
            self._fire_changed()
        return retval

    async def get(self, timeout: TimeType = float('inf'), *obj: EventType, all_or_nothing: bool = True, **policy_params: Any) -> Optional[List[EventType]]:
        ''' Get requested objects from container.
        @param: all_or_nothing if True, it blocks till all the objects will be in the container and returns them (or timeout)
                               if False, it continuosly grabs the requested objects when available until all collected; it returns collected items
        '''
        if all_or_nothing:
            retval = None
            tx = self._pre_get(obj)
            with self.sim.consume(tx, **policy_params):
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
                tx = self._pre_get(obj)
                with self.sim.consume(tx, **policy_params):
                    element = await self.sim.check_and_wait(timeout, cond=lambda e: any(el in self.container.keys() for el in obj))
                if element is None:
                    break
                retval += self.get_nowait(*obj)
                if len(retval) == len(obj):
                    break
        else:
            retval = []
        return retval

    def gget(self, timeout: TimeType = float('inf'), *obj: EventType, all_or_nothing: bool = True, **policy_params: Any) -> Generator[EventType, Optional[List[EventType]], Optional[List[EventType]]]:
        ''' Get requested objects from container.
        @param: all_or_nothing if True, it blocks till all the objects will be in the container and returns them (or timeout)
                               if False, it continuosly grabs the requested objects when available until all collected; it returns collected items
        '''
        if all_or_nothing:
            retval = None
            tx = self._pre_get(obj)
            with self.sim.consume(tx, **policy_params):
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
                tx = self._pre_get(obj)
                with self.sim.consume(tx, **policy_params):
                    element = yield from self.sim.check_and_gwait(timeout, cond=lambda e: any(el in self.container.keys() for el in obj))
                if element is None:
                    break
                retval += self.get_nowait(*obj)
                if len(retval) == len(obj):
                    break
        else:
            retval = []
        return retval

    def _pre_get(self, obj: tuple):
        return self.tx_nempty if len(obj) == 0 else self.tx_changed

    # ---- DSStatefulComponent overrides ---------------------------------------

    def gwait(self, timeout: TimeType = float('inf'), cond: CondType = lambda e: True, **policy_params: Any) -> Generator[EventType, EventType, EventType]:
        with self.sim.consume(self.tx_changed, **policy_params):
            retval = yield from self.sim.gwait(timeout, cond=cond)
        return retval

    async def wait(self, timeout: TimeType = float('inf'), cond: CondType = lambda e: True, **policy_params: Any) -> EventType:
        with self.sim.consume(self.tx_changed, **policy_params):
            retval = await self.sim.wait(timeout, cond=cond)
        return retval

    def check_and_gwait(self, timeout: TimeType = float('inf'), cond: CondType = lambda e: True, **policy_params: Any) -> Generator[EventType, EventType, EventType]:
        with self.sim.consume(self.tx_changed, **policy_params):
            retval = yield from self.sim.check_and_gwait(timeout, cond=cond)
        return retval

    async def check_and_wait(self, timeout: TimeType = float('inf'), cond: CondType = lambda e: True, **policy_params: Any) -> EventType:
        with self.sim.consume(self.tx_changed, **policy_params):
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


_DEFAULT_COND = object()  # sentinel: caller passed no condition


class Queue(DSStatefulComponent, SignalMixin):
    '''A queue component backed by three DSQueue instances:

    - buffer:  items currently in transit (policy controlled by *policy*)
    - putters: processes blocked waiting to put (full buffer)
    - getters: processes blocked waiting to get (empty buffer)

    Exposes ``buffer``, ``putters`` and ``getters`` properties for
    observability / statistics.

    The *policy* parameter accepts a DSQueue instance that acts as the buffer.
    Pass ``None`` (default) for FIFO, ``DSLifoQueue()`` for LIFO, or any
    ``DSKeyQueue(key=...)`` for priority ordering.
    '''

    def __init__(self, capacity: NumericType = float('inf'), policy: DSQueue = None, *args: Any, **policy_params: Any) -> None:
        super().__init__(*args, **policy_params)
        self.capacity = capacity
        self._buffer = policy if policy is not None else DSQueue()
        # Three targeted producers reduce spurious wakeups:
        #   getters with simple cond → subscribe to tx_nempty
        #   putters with simple cond → subscribe to tx_nfull
        #   getters/putters with complex cond → subscribe to tx_changed
        # self.tx_changed already defined
        self.tx_nempty  = self.sim.producer(name=self.name + '.tx_nempty')
        self.tx_nfull = self.sim.producer(name=self.name + '.tx_nfull')

    # ---- send (SignalMixin interface) ---------------------------------------

    def send(self, event: EventType) -> bool:
        return self.put_nowait(event) is not None

    def _fire_nempty(self) -> None:
        if self.tx_nempty.has_subscribers():
            self.sim.schedule_event(0, self.tx_nempty, self.tx_nempty)

    def _fire_nfull(self) -> None:
        if self.tx_nfull.has_subscribers():
            self.sim.schedule_event(0, self.tx_nfull, self.tx_nfull)

    def _fire_changed(self) -> None:
        if self.tx_changed.has_subscribers():
            self.sim.schedule_event(0, self.tx_changed, self.tx_changed)

    # ---- put side ----------------------------------------------------------

    def put_nowait(self, *obj: EventType) -> Optional[tuple]:
        '''Put item(s) into buffer immediately. Returns the obj tuple on success, None if full.'''
        if len(self._buffer) + len(obj) <= self.capacity:
            for item in obj:
                self._buffer.enqueue(item)
            self._fire_nempty()
            self._fire_changed()
            return obj
        return None

    async def put(self, timeout: TimeType = float('inf'), *obj: EventType, **policy_params: Any) -> EventType:
        '''Put item(s) into buffer, waiting up to *timeout* if the buffer is full.'''
        with self.sim.consume(self.tx_changed, **policy_params):
            retval = await self.sim.check_and_wait(
                timeout,
                cond=lambda e: len(self._buffer) + len(obj) <= self.capacity,
            )
        if retval is not None:
            for item in obj:
                self._buffer.enqueue(item)
            self._fire_nempty()
            self._fire_changed()
        return retval

    def gput(self, timeout: TimeType = float('inf'), *obj: EventType, **policy_params: Any) -> Generator[EventType, EventType, EventType]:
        '''Put item(s) into buffer (generator version), waiting up to *timeout* if full.'''
        with self.sim.consume(self.tx_nfull, **policy_params):
            retval = yield from self.sim.check_and_gwait(
                timeout,
                cond=lambda e: len(self._buffer) + len(obj) <= self.capacity,
            )
        if retval is not None:
            for item in obj:
                self._buffer.enqueue(item)
            self._fire_nempty()
            self._fire_changed()
        return retval

    # ---- get side ----------------------------------------------------------

    def get_nowait(self, amount: int = 1, cond: CondType = lambda e: True) -> Optional[List[EventType]]:
        '''Get item(s) from buffer immediately.

        Returns a list of *amount* items when available and *cond* passes for
        the head item, or None otherwise.
        '''
        if len(self._buffer) >= amount and cond(self._buffer.peek()):
            retval = [self._buffer.dequeue() for _ in range(amount)]
            self._fire_nfull()
            self._fire_changed()
            return retval
        return None

    async def get(self, timeout: TimeType = float('inf'), amount: int =1, cond: CondType = lambda e: True, **policy_params: Any) -> Optional[List[EventType]]:
        '''Get item(s) from buffer, waiting up to *timeout* if not available.'''
        effective_cond = (lambda e: True) if cond is _DEFAULT_COND else cond
        with self.sim.consume(self.tx_changed, **policy_params):
            element = await self.sim.check_and_wait(
                timeout,
                cond=lambda e: len(self._buffer) >= amount and effective_cond(self._buffer.peek()),
            )
        if element is None:
            return None
        retval = [self._buffer.dequeue() for _ in range(amount)]
        self._fire_nfull()
        self._fire_changed()
        return retval

    def gget(self, timeout: TimeType = float('inf'), amount: int = 1, cond: CondType = _DEFAULT_COND, **policy_params: Any) -> Generator[EventType, Optional[List[EventType]], Optional[List[EventType]]]:
        '''Get item(s) from buffer (generator version), waiting up to *timeout* if not available.'''
        effective_cond = (lambda e: True) if cond is _DEFAULT_COND else cond
        tx = self._pre_get(cond)
        with self.sim.consume(tx, **policy_params):
            element = yield from self.sim.check_and_gwait(
                timeout,
                cond=lambda e: len(self._buffer) >= amount and effective_cond(self._buffer.peek()),
            )
        if element is None:
            return None
        retval = [self._buffer.dequeue() for _ in range(amount)]
        self._fire_nfull()
        self._fire_changed()
        return retval

    # ---- direct buffer manipulation ----------------------------------------

    def pop(self, index: int = 0, default: Optional[EventType] = None) -> Optional[EventType]:
        '''Remove and return item at *index* (default: head). Returns *default* if out of range.'''
        if len(self._buffer) > index:
            try:
                retval = self._buffer.pop_at(index)
                self._fire_nfull()
                self._fire_changed()
            except IndexError:
                retval = default
        else:
            retval = default
        return retval

    def remove(self, cond: CondType) -> None:
        '''Remove item(s) from buffer matching *cond*.

        *cond* may be a callable predicate or an exact item to match (== equality).
        '''
        if len(self._buffer) > 0:
            changed = self._buffer.remove_if(
                lambda e: (callable(cond) and cond(e)) or cond == e
            )
            if changed:
                self._fire_nfull()
                self._fire_changed()

    def _pre_get(self, cond):
        return self.tx_nempty if cond is _DEFAULT_COND else self.tx_changed

    # ---- DSStatefulComponent overrides ---------------------------------------

    def gwait(self, timeout: TimeType = float('inf'), cond: CondType = lambda e: True, **policy_params: Any) -> Generator[EventType, EventType, EventType]:
        with self.sim.consume(self.tx_changed, **policy_params):
            retval = yield from self.sim.gwait(timeout, cond=cond)
        return retval

    async def wait(self, timeout: TimeType = float('inf'), cond: CondType = lambda e: True, **policy_params: Any) -> EventType:
        with self.sim.consume(self.tx_changed, **policy_params):
            retval = await self.sim.wait(timeout, cond=cond)
        return retval

    def check_and_gwait(self, timeout: TimeType = float('inf'), cond: CondType = lambda e: True, **policy_params: Any) -> Generator[EventType, EventType, EventType]:
        with self.sim.consume(self.tx_changed, **policy_params):
            retval = yield from self.sim.check_and_gwait(timeout, cond=cond)
        return retval

    async def check_and_wait(self, timeout: TimeType = float('inf'), cond: CondType = lambda e: True, **policy_params: Any) -> EventType:
        with self.sim.consume(self.tx_changed, **policy_params):
            retval = await self.sim.check_and_wait(timeout, cond=cond)
        return retval

    # ---- sequence protocol -------------------------------------------------

    def __len__(self) -> int:
        return len(self._buffer)

    def __getitem__(self, index: int) -> EventType:
        return self._buffer[index]

    def __setitem__(self, index: int, data: EventType) -> None:
        self._buffer[index] = data
        self._fire_nempty()
        self._fire_changed()

    def __iter__(self) -> Iterator[EventType]:
        return iter(self._buffer)

    def __contains__(self, item: Any) -> bool:
        return item in self._buffer


# In the following, self is in fact of type DSProcessComponent, but PyLance makes troubles with variable types
class ContainerMixin:
    async def enter(self: Any, container: Union[Queue, Container], timeout: TimeType = float('inf'), **policy_params: Any) -> EventType:
        try:
            retval = await container.put(timeout, self, **policy_params)
        except DSAbortException as exc:
            self.scheduled_process.abort()
        return retval

    def genter(self: Any, container: Union[Queue, Container], timeout: TimeType = float('inf'), **policy_params) -> Generator[EventType, EventType, EventType]:
        try:
            retval = yield from container.gput(timeout, self, **policy_params)
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
            elements = await container.get(timeout, **policy_params)
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
            elements = yield from container.gget(timeout, **policy_params)
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
    def container(self: Any, *args: Any, **policy_params: Any) -> Container:
        sim: DSSimulation = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in container() method should be set to the same simulation instance.')
        return Container(*args, **policy_params, sim=sim)


# In the following, self is in fact of type DSSimulation, but PyLance makes troubles with variable types
class SimQueueMixin:
    def queue(self: Any, *args: Any, **policy_params: Any) -> Queue:
        sim: DSSimulation = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in queue() method should be set to the same simulation instance.')
        return Queue(*args, **policy_params, sim=sim)
