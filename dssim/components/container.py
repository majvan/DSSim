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
import heapq
from collections import deque
from typing import Any, List, Dict, Iterator, Union, Optional, Generator, TYPE_CHECKING
from dssim.base import NumericType, TimeType, EventType, SignalMixin
from dssim.pubsub_base import CondType, DSAbortException, AlwaysTrue
from dssim.components.base import DSStatefulComponent
from dssim.pubsub import DSProducer


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
    '''DSQueue variant that dequeues items in ascending order of a key function.

    The item with the smallest key value is always dequeued first
    (min-priority semantics).  Use ``key=lambda item: -item.priority`` to get
    max-priority behaviour.  Items with equal keys are dequeued in FIFO order.

    Internally uses a binary min-heap (heapq) so that ``enqueue`` and
    ``dequeue`` are O(log n) and ``peek`` is O(1).

    Heap entries are ``(key_val, counter, item)`` triples.  The ``counter``
    is a monotonically increasing integer inserted between the key and the
    item so that heapq never needs to compare item objects directly: Python
    compares tuples left-to-right and stops at the first differing element,
    so a unique counter guarantees the comparison always resolves before
    reaching ``item``.  Without it, two items with equal keys would trigger
    ``item1 < item2``, raising ``TypeError`` for any non-comparable type.
    As a side-effect the counter also gives stable FIFO ordering among
    equal-key items for free.
    '''

    def __init__(self, key: Any = lambda item: item) -> None:
        super().__init__()
        self._data = []   # override deque with a list used as a heap
        self._key = key
        self._counter = 0  # see class docstring for why this is needed

    # ---- priority-queue policy interface -----------------------------------

    def enqueue(self, item: Any) -> Any:
        '''Insert item into heap. O(log n).'''
        heapq.heappush(self._data, (self._key(item), self._counter, item))
        self._counter += 1
        return item

    def dequeue(self) -> Any:
        '''Remove and return item with smallest key. O(log n).'''
        return heapq.heappop(self._data)[2]

    def peek(self) -> Any:
        '''Return item with smallest key without removing it. O(1).'''
        return self._data[0][2] if self._data else None

    # ---- convenience properties --------------------------------------------

    @property
    def head(self) -> Any:
        '''Smallest-key item (heap root). Returns None when empty.'''
        return self._data[0][2] if self._data else None

    @property
    def tail(self) -> Any:
        '''Last item in heap-array order (not sorted). Returns None when empty.'''
        return self._data[-1][2] if self._data else None

    # ---- sequence protocol -------------------------------------------------

    def __len__(self) -> int:
        return len(self._data)

    def __bool__(self) -> bool:
        return bool(self._data)

    def __iter__(self) -> Iterator:
        '''Iterate items in ascending key order (priority order). O(n log n).'''
        return iter([entry[2] for entry in sorted(self._data)])

    def __contains__(self, item: Any) -> bool:
        return any(entry[2] is item or entry[2] == item for entry in self._data)

    def __repr__(self) -> str:
        return f'DSKeyQueue({[e[2] for e in sorted(self._data)]})'

    def __getitem__(self, index: int) -> Any:
        '''Return item at *index* in ascending key order. O(n log n).'''
        return sorted(self._data)[index][2]

    def __setitem__(self, index: int, value: Any) -> None:
        '''Replace item at *index* in ascending key order with *value*. O(n log n).'''
        old_entry = sorted(self._data)[index]
        self._data.remove(old_entry)
        heapq.heappush(self._data, (self._key(value), self._counter, value))
        self._counter += 1

    # ---- raw-deque delegates (keep DSQueue callers working) ----------------

    def append(self, item: Any) -> Any:
        '''Delegate to enqueue (heap insert). O(log n).'''
        return self.enqueue(item)

    def appendleft(self, item: Any) -> Any:
        '''Delegate to enqueue; position is determined by key, not insertion side.'''
        return self.enqueue(item)

    def popleft(self) -> Any:
        '''Delegate to dequeue (smallest-key item). O(log n).'''
        return self.dequeue()

    # ---- mutation ----------------------------------------------------------

    def remove(self, item: Any) -> None:
        '''Remove first occurrence of item. O(n) scan + O(n) heapify.'''
        for i, entry in enumerate(self._data):
            if entry[2] is item or entry[2] == item:
                # swap with last, pop, rebuild
                self._data[i] = self._data[-1]
                self._data.pop()
                heapq.heapify(self._data)
                return
        raise ValueError(f'{item!r} not in DSKeyQueue')

    def remove_if(self, cond: CondType) -> bool:
        '''Remove all items satisfying *cond*. O(n) filter + O(n) heapify.'''
        before = len(self._data)
        self._data = [e for e in self._data if not cond(e[2])]
        if len(self._data) < before:
            heapq.heapify(self._data)
            return True
        return False

    def pop_at(self, index: int) -> Any:
        '''Remove and return item at *index* in ascending key order. O(n log n).'''
        entry = sorted(self._data)[index]
        self._data.remove(entry)
        heapq.heapify(self._data)
        return entry[2]

    def clear(self) -> None:
        '''Remove all items.'''
        self._data.clear()
        self._counter = 0


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
        self.tx_nempty = self.sim.producer(name=self.name + '.tx_nempty')
        self.LAMBDA1 = lambda _: self.size >= 1

    def _available(self, num_items: int) -> bool:
        return self.capacity is None or (self.size + num_items <= self.capacity)

    def _fire_nempty(self) -> None:
        if self.tx_nempty.has_subscribers():
            self.sim.schedule_event_now(self.tx_nempty, self.tx_nempty)

    def _fire_changed(self) -> None:
        if self.tx_changed.has_subscribers():
            self.sim.schedule_event_now(self.tx_changed, self.tx_changed)

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

    def __init__(self, capacity: NumericType = float('inf'), policy: DSQueue = None,
                 nempty_ep: Optional[DSProducer] = None, nfull_ep: Optional[DSProducer] = None,
                 *args: Any, **policy_params: Any) -> None:
        super().__init__(*args, **policy_params)
        self.capacity = capacity
        self._buffer = policy if policy is not None else DSQueue()
        # Three targeted producers reduce spurious wakeups:
        #   getters with simple cond → subscribe to tx_nempty
        #   putters with simple cond → subscribe to tx_nfull
        #   getters/putters with complex cond → subscribe to tx_changed
        # nempty_ep / nfull_ep allow injecting a custom notifier (e.g. NotifierPriority)
        # so that priority-ordered waiting works on the hot tx_nempty / tx_nfull paths.
        # self.tx_changed already defined by DSStatefulComponent (accepts change_ep=)
        self.tx_nempty = nempty_ep if nempty_ep is not None else self.sim.producer(name=self.name + '.tx_nempty')
        self.tx_nfull  = nfull_ep  if nfull_ep  is not None else self.sim.producer(name=self.name + '.tx_nfull')
        self.LAMBDA1 = lambda _: len(self._buffer) >= 1

    # ---- send (SignalMixin interface) ---------------------------------------

    def send(self, event: EventType) -> bool:
        return self.put_nowait(event) is not None

    def _fire_nempty(self) -> None:
        if self.tx_nempty.has_subscribers():
            self.sim.schedule_event_now(self.tx_nempty, self.tx_nempty)

    def _fire_nfull(self) -> None:
        if self.tx_nfull.has_subscribers():
            self.sim.schedule_event_now(self.tx_nfull, self.tx_nfull)

    def _fire_changed(self) -> None:
        if self.tx_changed.has_subscribers():
            self.sim.schedule_event_now(self.tx_changed, self.tx_changed)

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
        with self.sim.consume(self.tx_nfull, **policy_params):
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

    def get_n_nowait(self, amount: int = 1, cond: CondType = AlwaysTrue) -> Optional[List[EventType]]:
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

    def get_nowait(self, cond: CondType = AlwaysTrue) -> Optional[List[EventType]]:
        '''A version of get_n_nowait which does not return a list, but rather one element.'''
        if len(self._buffer) >= 1 and cond(self._buffer.peek()):
            retval = self._buffer.dequeue()
            self._fire_nfull()
            self._fire_changed()
            return retval
        return None

    async def get_n(self, timeout: TimeType = float('inf'), amount: int =1, cond: CondType = AlwaysTrue, **policy_params: Any) -> Optional[List[EventType]]:
        '''Get item(s) from buffer, waiting up to *timeout* if not available.'''
        tx = self._get_tx_endpoint(cond)
        if cond is AlwaysTrue:
            check = lambda _: len(self._buffer) >= amount
        else:
            check = lambda _: len(self._buffer) >= amount and cond(self._buffer.peek())
        with self.sim.consume(tx, **policy_params):
            element = await self.sim.check_and_wait(timeout, cond=check)
        if element is None:
            return None
        retval = [self._buffer.dequeue() for _ in range(amount)]
        self._fire_nfull()
        self._fire_changed()
        return retval

    async def get(self, timeout: TimeType = float('inf'), cond: CondType = AlwaysTrue, **policy_params: Any) -> Optional[List[EventType]]:
        '''A version of get_n which does not return a list, but rather one element.'''
        tx = self._get_tx_endpoint(cond)
        if cond is AlwaysTrue:
            check = self.LAMBDA1
        else:
            check = lambda _: len(self._buffer) >= 1 and cond(self._buffer.peek())
        with self.sim.consume(tx, **policy_params):
            element = await self.sim.check_and_wait(timeout, cond=check)
        if element is None:
            return None
        retval = self._buffer.dequeue()
        self._fire_nfull()
        self._fire_changed()
        return retval

    def gget_n(self, timeout: TimeType = float('inf'), amount: int = 1, cond: CondType = AlwaysTrue, **policy_params: Any) -> Generator[EventType, Optional[List[EventType]], Optional[List[EventType]]]:
        '''Get item(s) from buffer (generator version), waiting up to *timeout* if not available.'''
        tx = self._get_tx_endpoint(cond)
        if cond is AlwaysTrue:
            check = lambda _: len(self._buffer) >= amount
        else:
            check = lambda _: len(self._buffer) >= amount and cond(self._buffer.peek())
        with self.sim.consume(tx, **policy_params):
            element = yield from self.sim.check_and_gwait(timeout, cond=check)
        if element is None:
            return None
        retval = [self._buffer.dequeue() for _ in range(amount)]
        self._fire_nfull()
        self._fire_changed()
        return retval

    def gget(self, timeout: TimeType = float('inf'), cond: CondType = AlwaysTrue, **policy_params: Any) -> Generator[EventType, Optional[EventType], Optional[EventType]]:
        '''A version of gget_n which does not return a list, but rather one element.'''
        tx = self._get_tx_endpoint(cond)
        if cond is AlwaysTrue:
            check = self.LAMBDA1
        else:
            check = lambda _: len(self._buffer) >= 1 and cond(self._buffer.peek())
        with self.sim.consume(tx, **policy_params):
            element = yield from self.sim.check_and_gwait(timeout, cond=check)
        if element is None:
            return None
        retval = self._buffer.dequeue()
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

    async def pop(self: Any, container: Union[Queue, Container], timeout: TimeType = float('inf'), **policy_params: Any) -> Optional[EventType]:
        try:
            retval = await container.get(timeout, **policy_params)
        except DSAbortException as exc:
            self.scheduled_process.abort()
        return retval

    def gpop(self: Any, container: Union[Queue, Container], timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, EventType, EventType]:
        try:
            retval = yield from container.gget(timeout, **policy_params)
        except DSAbortException as exc:
            self.scheduled_process.abort()
        return retval

    def pop_nowait(self: Any, container: Union[Queue, Container]) -> EventType:
        return container.get_nowait()


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
