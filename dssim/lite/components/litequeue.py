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
DSLiteQueue — a minimal queue for use with LiteLayer2.

Unlike :class:`DSQueue`, DSLiteQueue requires no pubsub layer and no condition
machinery.  It works purely with two simulation primitives:

  * ``sim.signal(event, subscriber)``
  * ``yield from sim.gwait()`` — a single unconditional yield

Internal event model
--------------------
Two singleton sentinels drive all wakeups:

* ``_GET_READY`` — scheduled to *this queue* when a put makes a previously
  empty buffer non-empty.  :meth:`send` receives it and delivers the head
  item to the first waiting getter.
* ``_PUT_READY`` — scheduled to *this queue* when a get makes a previously
  full buffer non-full.  :meth:`send` receives it and enqueues the first
  waiting putter's item, then wakes that putter.

Because DSLiteQueue itself is the ISubscriber target for both sentinels,
:meth:`send` acts as the internal dispatcher — no separate DSPub or
pubsub fan-out is involved.

Cascading wakeups
-----------------
After waking a getter: if buffer still non-empty and more getters are
waiting, schedule another ``_GET_READY`` to self.
After waking a putter: if buffer still non-full and more putters are
waiting, schedule another ``_PUT_READY`` to self.

Getters and putters never wait simultaneously (for capacity > 0):
putters block only when the buffer is full; getters block only when it is
empty.
'''
from __future__ import annotations
from collections import deque
from typing import Any, Iterator, Optional, Generator, TYPE_CHECKING

from dssim.base import NumericType, EventType, EventRetType, ISubscriber, DSComponent
from dssim.base_components import DSBaseOrder

if TYPE_CHECKING:
    from dssim.simulation import DSSimulation


# ---------------------------------------------------------------------------
# Sentinel singletons — identity comparison (is) keeps hot paths allocation-free
# ---------------------------------------------------------------------------
_GET_READY = object()   # "at least one item is available for a waiting getter"
_PUT_READY = object()   # "at least one slot is available for a waiting putter"


class DSLiteQueue(DSComponent, ISubscriber):
    '''Minimal FIFO queue for LiteLayer2 simulations.

    Parameters
    ----------
    capacity:
        Maximum number of items the queue can hold.  Default: unlimited.
    policy:
        A :class:`~dssim.base_components.DSBaseOrder`-compatible object
        that provides ``enqueue`` / ``dequeue`` / ``__len__`` / ``__bool__``
        methods.  Default: plain FIFO :class:`DSBaseOrder`.
    '''

    def __init__(self, capacity: NumericType = float('inf'),
                 policy: Optional[DSBaseOrder] = None, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.capacity = capacity
        self._buffer: DSBaseOrder = policy if policy is not None else DSBaseOrder()
        self._getters: deque = deque()   # waiting getter generators
        self._putters: deque = deque()   # (putter_generator, item) pairs

    # -----------------------------------------------------------------------
    # ISubscriber — internal sentinel dispatcher
    # -----------------------------------------------------------------------

    def send(self, event: EventType) -> EventRetType:
        '''Dispatch ``_GET_READY`` / ``_PUT_READY`` to the first waiter.

        Called by the simulation event loop when a sentinel scheduled via
        ``sim.signal`` is processed.  Never called directly.

        Waiters are plain generators already suspended at ``yield from
        sim.gwait()``.  We wake them directly via ``sim.send_object()``
        instead of re-scheduling through the now-queue — this avoids
        routing the item through ``sim.signal(event, subscriber)``
        where the ``subscriber or _parent_process`` fallback could misbehave
        if ``subscriber`` (i.e. ``self``) evaluates as falsy.
        '''
        if event is _GET_READY:
            # A getter is waiting and an item is available.
            if self._getters and self._buffer:
                getter = self._getters.popleft()
                was_full = len(self._buffer) >= self.capacity
                item = self._buffer.dequeue()
                # Wake the getter directly — it is a suspended generator.
                self.sim.send_object(getter, item)
                # A slot just opened — let a waiting putter through.
                if was_full and self._putters:
                    self.sim.signal(_PUT_READY, self)
                # More items and more getters — chain another wakeup.
                if self._getters and self._buffer:
                    self.sim.signal(_GET_READY, self)
        elif event is _PUT_READY:
            # A putter is waiting and a slot is available.
            if self._putters and len(self._buffer) < self.capacity:
                putter, item = self._putters.popleft()
                was_empty = len(self._buffer) == 0
                self._buffer.enqueue(item)
                # Wake the putter directly — it is a suspended generator.
                self.sim.send_object(putter, item)
                # Buffer just became non-empty — let a waiting getter through.
                if was_empty and self._getters:
                    self.sim.signal(_GET_READY, self)
                # More space and more putters — chain another wakeup.
                if self._putters and len(self._buffer) < self.capacity:
                    self.sim.signal(_PUT_READY, self)
        return None

    # -----------------------------------------------------------------------
    # Nowait (non-blocking) operations
    # -----------------------------------------------------------------------

    def put_nowait(self, item: Any) -> Optional[Any]:
        '''Put *item* immediately without entering the simulation loop.

        Returns *item* on success, or ``None`` if the buffer is full.
        '''
        if len(self._buffer) < self.capacity:
            was_empty = len(self._buffer) == 0
            self._buffer.enqueue(item)
            if was_empty and self._getters:
                self.sim.signal(_GET_READY, self)
            return item
        return None

    def get_nowait(self) -> Optional[Any]:
        '''Get the head item immediately without entering the simulation loop.

        Returns the item, or ``None`` if the buffer is empty.
        '''
        if self._buffer:
            was_full = len(self._buffer) >= self.capacity
            item = self._buffer.dequeue()
            if was_full and self._putters:
                self.sim.signal(_PUT_READY, self)
            return item
        return None

    # -----------------------------------------------------------------------
    # Generator (blocking) operations
    # -----------------------------------------------------------------------

    def gput(self, item: Any) -> Generator[Any, Any, Any]:
        '''Put *item*, suspending the caller if the buffer is full.

        When space is available the function returns without yielding —
        ``yield from q.gput(item)`` never suspends the caller.
        When the buffer is full, the caller suspends until a slot opens.

        Returns *item* in both cases.
        '''
        if len(self._buffer) < self.capacity:
            was_empty = len(self._buffer) == 0
            self._buffer.enqueue(item)
            if was_empty and self._getters:
                self.sim.signal(_GET_READY, self)
            return item
        # Buffer full — register as a waiter and suspend.
        caller = self.sim._parent_process
        self._putters.append((caller, item))
        yield from self.sim.gwait()
        # send(_PUT_READY) already enqueued *item* before waking us.
        return item

    def gget(self) -> Generator[Any, Any, Any]:
        '''Get the head item, suspending the caller if the buffer is empty.

        When an item is available the function returns without yielding —
        ``yield from q.gget()`` never suspends the caller.
        When the buffer is empty, the caller suspends until an item arrives.
        The item is delivered as the event value sent to the caller.

        Returns the item.
        '''
        if self._buffer:
            was_full = len(self._buffer) >= self.capacity
            item = self._buffer.dequeue()
            if was_full and self._putters:
                self.sim.signal(_PUT_READY, self)
            return item
        # Buffer empty — register as a waiter and suspend.
        caller = self.sim._parent_process
        self._getters.append(caller)
        item = yield from self.sim.gwait()
        # send(_GET_READY) delivered the item directly as the wakeup event.
        return item

    # -----------------------------------------------------------------------
    # Sequence protocol
    # -----------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._buffer)

    def __bool__(self) -> bool:
        # Must be True regardless of buffer contents — DSLiteQueue is a simulation
        # component, not a plain container.  Python would otherwise fall back to
        # __len__ and treat an empty queue as falsy, which breaks the
        # `subscriber or self._parent_process` fallback inside sim.signal.
        return True

    def __iter__(self) -> Iterator:
        return iter(self._buffer)

    def __contains__(self, item: Any) -> bool:
        return item in self._buffer


# In the following, self is in fact of type DSSimulation, but PyLance makes troubles with variable types
class SimLiteQueueMixin:
    def queue(self: Any, *args: Any, **kwargs: Any) -> DSLiteQueue:
        sim: 'DSSimulation' = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in queue() method should be set to the same simulation instance.')
        return DSLiteQueue(*args, **kwargs, sim=sim)
