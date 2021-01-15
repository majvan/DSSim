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
Core reusable building blocks used by simulation components.
'''
import heapq
from collections import deque
from typing import Any, Iterator, Callable, Dict, List, Optional

from dssim.base import NumericType


class DSBaseOrder:
    '''A performant ordered collection for simulation use.

    DSBaseOrder provides O(1) head/tail access and O(1) append/popleft operations
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
        return f'DSBaseOrder({list(self._data)})'

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


class DSLifoOrder(DSBaseOrder):
    '''LIFO (stack) variant of DSBaseOrder. Items are dequeued in reverse insertion order.'''

    def dequeue(self) -> Any:
        '''Remove and return item from tail (LIFO pop). O(1).'''
        return self.pop()

    def peek(self) -> Any:
        '''Return item at tail without removing it. O(1).'''
        return self.tail


class DSKeyOrder(DSBaseOrder):
    '''DSBaseOrder variant that dequeues items in ascending order of a key function.

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
        return f'DSKeyOrder({[e[2] for e in sorted(self._data)]})'

    def __getitem__(self, index: int) -> Any:
        '''Return item at *index* in ascending key order. O(n log n).'''
        return sorted(self._data)[index][2]

    def __setitem__(self, index: int, value: Any) -> None:
        '''Replace item at *index* in ascending key order with *value*. O(n log n).'''
        old_entry = sorted(self._data)[index]
        self._data.remove(old_entry)
        heapq.heappush(self._data, (self._key(value), self._counter, value))
        self._counter += 1

    # ---- raw-deque delegates (keep DSBaseOrder callers working) ----------------

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
        raise ValueError(f'{item!r} not in DSKeyOrder')

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


class _ResourceBookkeeper:
    '''Plain amount/capacity container for resource components.'''

    def __init__(
        self,
        amount: NumericType = 0,
        capacity: NumericType = float('inf'),
        owner: Optional[Any] = None,
    ) -> None:
        if amount > capacity:
            raise ValueError('Initial amount of the resource is greater than capacity.')
        # Keep a non-null owner reference so hot-path put/get can stay branch-free.
        self._owner = owner if owner is not None else self
        target = self._owner
        target.amount = amount
        target.capacity = capacity

    def put_n_nowait(self, amount: NumericType = 1) -> NumericType:
        target = self._owner
        if target.amount + amount > target.capacity:
            return 0
        target.amount += amount
        return amount

    def get_n_nowait(self, amount: NumericType = 1) -> NumericType:
        target = self._owner
        if amount > target.amount:
            return 0
        target.amount -= amount
        return amount


class DSBasePriorityResource:
    '''Priority holder bookkeeping shared by priority resource components.'''

    def __init__(self) -> None:
        # Owner state layout: [amount, priority]
        self.holders_by_owner: Dict[Any, List[NumericType]] = {}
        self.holders_by_priority: Dict[int, List[Any]] = {}
        self.reclaimed: Dict[Any, NumericType] = {}

    def held_amount(self, owner: Any) -> NumericType:
        state = self.holders_by_owner.get(owner)
        if state is None:
            return 0
        return state[0]

    def remove_from_bucket(self, owner: Any, priority: int) -> None:
        bucket = self.holders_by_priority.get(priority)
        if bucket is None:
            return
        try:
            bucket.remove(owner)
        except ValueError:
            return
        if not bucket:
            self.holders_by_priority.pop(priority, None)

    def set_holder_amount(self, owner: Any, amount: NumericType) -> None:
        state = self.holders_by_owner.get(owner)
        if state is None:
            return
        if amount <= 0:
            self.remove_from_bucket(owner, state[1])
            self.holders_by_owner.pop(owner, None)
            return
        state[0] = amount

    def remember_acquire(self, owner: Any, amount: NumericType, priority: int) -> None:
        state = self.holders_by_owner.get(owner)
        if state is None:
            self.holders_by_owner[owner] = [amount, priority]
            bucket = self.holders_by_priority.setdefault(priority, [])
            bucket.append(owner)
            return

        state[0] += amount
        old_priority = state[1]
        new_priority = min(old_priority, priority)
        if new_priority != old_priority:
            self.remove_from_bucket(owner, old_priority)
            state[1] = new_priority
            self.holders_by_priority.setdefault(new_priority, []).append(owner)
            return

        # Same-priority re-acquire: refresh recency (newest at end).
        bucket = self.holders_by_priority.setdefault(new_priority, [])
        try:
            bucket.remove(owner)
        except ValueError:
            pass
        bucket.append(owner)

    def consume_reclaimed_release(self, owner: Any, amount: NumericType) -> NumericType:
        reclaimed = self.reclaimed.get(owner, 0)
        if reclaimed <= 0:
            return amount
        consumed = reclaimed if reclaimed <= amount else amount
        left = reclaimed - consumed
        if left > 0:
            self.reclaimed[owner] = left
        else:
            self.reclaimed.pop(owner, None)
        return amount - consumed


class DSPriorityPreemption:
    '''Shared preemption dispatch algorithm for priority resources.'''

    def __init__(self, priority_state: DSBasePriorityResource) -> None:
        self.priority = priority_state

    def reclaim_from_victims(
        self,
        need: NumericType,
        requester: Any,
        req_priority: int,
        on_take: Callable[[NumericType], None],
        on_preempted: Callable[[Any, int, NumericType], None],
        on_reclaimed: Optional[Callable[[NumericType], None]] = None,
    ) -> NumericType:
        if need <= 0:
            return 0
        released = 0
        # preempt weakest holders first:
        # larger numeric priority first, and for equal priority newest first.
        candidates = []
        for holder_prio in sorted(self.priority.holders_by_priority.keys(), reverse=True):
            if holder_prio <= req_priority:
                continue
            bucket = self.priority.holders_by_priority[holder_prio]
            for owner in reversed(bucket):
                candidates.append((holder_prio, owner))

        for holder_prio, owner in candidates:
            if need <= 0:
                break
            if owner is requester:
                continue
            state = self.priority.holders_by_owner.get(owner)
            if state is None:
                continue
            if state[1] <= req_priority:
                continue
            held = state[0]
            if held <= 0:
                continue
            taken = held if held <= need else need
            self.priority.set_holder_amount(owner, held - taken)
            self.priority.reclaimed[owner] = self.priority.reclaimed.get(owner, 0) + taken
            on_take(taken)
            released += taken
            need -= taken
            on_preempted(owner, holder_prio, taken)
        if released > 0 and on_reclaimed is not None:
            on_reclaimed(released)
        return released
