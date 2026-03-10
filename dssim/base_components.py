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
Plain (simulation-unaware) data structures used as building blocks for
simulation components.
'''
import heapq
from collections import deque
from typing import Any, Iterator, Callable


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

    def remove_if(self, cond: Callable) -> bool:
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

    def remove_if(self, cond: Callable) -> bool:
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
