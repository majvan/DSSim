# Copyright 2026- majvan (majvan@gmail.com)
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
LiteResource / LitePriorityResource for LiteLayer2.

These components avoid pubsub/conditions and rely only on LiteLayer2 primitives:
  - sim.signal(event, subscriber)
  - yield from sim.gwait(...)
  - await sim.wait(...)
'''
from __future__ import annotations

from collections import deque
from typing import Any, Deque, Generator, List, Optional, TYPE_CHECKING

from dssim.base import DSComponent, NumericType, EventType, EventRetType, ISubscriber, TimeType
from dssim.base_components import DSResource, DSPriorityResource, DSPriorityPreemption


if TYPE_CHECKING:
    from dssim.simulation import DSSimulation


_DISPATCH = object()


class DSResourcePreempted(Exception):
    '''Raised when a resource holder is preempted by a higher-priority requester.'''

    def __init__(self, resource: Any, by: Any, owner: Any, priority: int, amount: Any) -> None:
        super().__init__(f'{owner} was preempted on {resource} by {by} (priority={priority}, amount={amount}).')
        self.resource = resource
        self.by = by
        self.owner = owner
        self.priority = priority
        self.amount = amount


class _Waiter:
    __slots__ = ('subscriber', 'amount', 'done')

    def __init__(self, subscriber: ISubscriber, amount: NumericType) -> None:
        self.subscriber = subscriber
        self.amount = amount
        self.done = False


class _PriorityWaiter(_Waiter):
    __slots__ = ('priority', 'seq')

    def __init__(self, subscriber: ISubscriber, amount: NumericType, priority: int, seq: int) -> None:
        super().__init__(subscriber, amount)
        self.priority = priority
        self.seq = seq


class _WaitTimeout:
    __slots__ = ('waiter',)

    def __init__(self, waiter: _Waiter) -> None:
        self.waiter = waiter


class LiteResource(DSComponent, ISubscriber):
    '''Minimal resource for LiteLayer2 simulations.

    * ``get`` consumes amount from the pool.
    * ``put`` adds amount to the pool.
    * blocked getters/putters are resumed directly via sim.send_object().
    '''

    def __init__(self, amount: NumericType = 0, capacity: NumericType = float('inf'),
                 *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._resource = DSResource(amount=amount, capacity=capacity, owner=self)
        self._getters: Deque[_Waiter] = deque()
        self._putters: Deque[_Waiter] = deque()
        self._dispatch_scheduled = False

    # ------------------------------------------------------------------
    # Internal queue policy hooks (LitePriorityResource overrides getter policy)
    # ------------------------------------------------------------------

    def _enqueue_getter(self, waiter: _Waiter, **policy_params: Any) -> None:
        self._getters.append(waiter)

    def _peek_getter(self) -> Optional[_Waiter]:
        return self._getters[0] if self._getters else None

    def _pop_getter(self) -> Optional[_Waiter]:
        return self._getters.popleft() if self._getters else None

    def _remove_getter(self, waiter: _Waiter) -> bool:
        try:
            self._getters.remove(waiter)
            return True
        except ValueError:
            return False

    def _enqueue_putter(self, waiter: _Waiter) -> None:
        self._putters.append(waiter)

    def _peek_putter(self) -> Optional[_Waiter]:
        return self._putters[0] if self._putters else None

    def _pop_putter(self) -> Optional[_Waiter]:
        return self._putters.popleft() if self._putters else None

    def _remove_putter(self, waiter: _Waiter) -> bool:
        try:
            self._putters.remove(waiter)
            return True
        except ValueError:
            return False

    # ------------------------------------------------------------------
    # Internal dispatch
    # ------------------------------------------------------------------

    def _request_dispatch(self) -> None:
        if not self._dispatch_scheduled:
            self._dispatch_scheduled = True
            self.sim.signal(_DISPATCH, self)

    def _dispatch_waiters(self) -> None:
        while True:
            progressed = False

            while True:
                waiter = self._peek_getter()
                if waiter is None or waiter.amount > self.amount:
                    break
                self._pop_getter()
                if waiter.done:
                    continue
                self.amount -= waiter.amount
                waiter.done = True
                self.sim.send_object(waiter.subscriber, waiter.amount)
                progressed = True

            while True:
                waiter = self._peek_putter()
                if waiter is None or self.amount + waiter.amount > self.capacity:
                    break
                self._pop_putter()
                if waiter.done:
                    continue
                self.amount += waiter.amount
                waiter.done = True
                self.sim.send_object(waiter.subscriber, waiter.amount)
                progressed = True

            if not progressed:
                break

    def _handle_timeout(self, event: _WaitTimeout) -> None:
        waiter = event.waiter
        if waiter.done:
            return
        waiter.done = True
        removed = self._remove_getter(waiter)
        if not removed:
            self._remove_putter(waiter)
        self.sim.send_object(waiter.subscriber, 0)

    # ------------------------------------------------------------------
    # ISubscriber
    # ------------------------------------------------------------------

    def send(self, event: EventType) -> EventRetType:
        if event is _DISPATCH:
            self._dispatch_scheduled = False
            self._dispatch_waiters()
        elif isinstance(event, _WaitTimeout):
            self._handle_timeout(event)
        return None

    # ------------------------------------------------------------------
    # Nowait operations
    # ------------------------------------------------------------------

    def put_nowait(self) -> NumericType:
        return self.put_n_nowait(1)

    def put_n_nowait(self, amount: NumericType = 1) -> NumericType:
        retval = self._resource.put_n_nowait(amount)
        if retval > 0 and self._getters:
            self._request_dispatch()
        return retval

    def get_nowait(self, **policy_params: Any) -> NumericType:
        return self.get_n_nowait(1, **policy_params)

    def get_n_nowait(self, amount: NumericType = 1, **policy_params: Any) -> NumericType:
        retval = self._resource.get_n_nowait(amount)
        if retval > 0 and self._putters:
            self._request_dispatch()
        return retval

    # ------------------------------------------------------------------
    # Blocking generator operations
    # ------------------------------------------------------------------

    def gput(self, timeout: TimeType = float('inf')) -> Generator[EventType, EventType, NumericType]:
        return (yield from self.gput_n(timeout=timeout, amount=1))

    def gput_n(self, timeout: TimeType = float('inf'), amount: NumericType = 1, **policy_params: Any) -> Generator[EventType, EventType, NumericType]:
        retval = self.put_n_nowait(amount)
        if retval > 0:
            return retval
        waiter = _Waiter(self.sim._parent_process, amount)
        self._enqueue_putter(waiter)
        if timeout != float('inf'):
            self.sim.schedule_event(timeout, _WaitTimeout(waiter), self)
        self._request_dispatch()
        event = yield from self.sim.gwait()
        return 0 if event is None else event

    def gget(self, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, EventType, NumericType]:
        return (yield from self.gget_n(timeout=timeout, amount=1, **policy_params))

    def gget_n(self, timeout: TimeType = float('inf'), amount: NumericType = 1, **policy_params: Any) -> Generator[EventType, EventType, NumericType]:
        retval = self.get_n_nowait(amount, **policy_params)
        if retval > 0:
            return retval
        waiter = _Waiter(self.sim._parent_process, amount)
        self._enqueue_getter(waiter, **policy_params)
        if timeout != float('inf'):
            self.sim.schedule_event(timeout, _WaitTimeout(waiter), self)
        self._request_dispatch()
        event = yield from self.sim.gwait()
        return 0 if event is None else event

    # ------------------------------------------------------------------
    # Blocking async operations (for coroutine schedulables in LiteLayer2)
    # ------------------------------------------------------------------

    async def put(self, timeout: TimeType = float('inf')) -> NumericType:
        return await self.put_n(timeout=timeout, amount=1)

    async def put_n(self, timeout: TimeType = float('inf'), amount: NumericType = 1, **policy_params: Any) -> NumericType:
        retval = self.put_n_nowait(amount)
        if retval > 0:
            return retval
        waiter = _Waiter(self.sim._parent_process, amount)
        self._enqueue_putter(waiter)
        if timeout != float('inf'):
            self.sim.schedule_event(timeout, _WaitTimeout(waiter), self)
        self._request_dispatch()
        event = await self.sim.wait()
        return 0 if event is None else event

    async def get(self, timeout: TimeType = float('inf'), **policy_params: Any) -> NumericType:
        return await self.get_n(timeout=timeout, amount=1, **policy_params)

    async def get_n(self, timeout: TimeType = float('inf'), amount: NumericType = 1, **policy_params: Any) -> NumericType:
        retval = self.get_n_nowait(amount, **policy_params)
        if retval > 0:
            return retval
        waiter = _Waiter(self.sim._parent_process, amount)
        self._enqueue_getter(waiter, **policy_params)
        if timeout != float('inf'):
            self.sim.schedule_event(timeout, _WaitTimeout(waiter), self)
        self._request_dispatch()
        event = await self.sim.wait()
        return 0 if event is None else event


class LitePriorityResource(LiteResource):
    '''LiteResource variant with priority-ordered getter wakeups.

    Lower numeric priority value is served first. Same priority preserves FIFO.
    '''
    Preempted = DSResourcePreempted

    def __init__(self, *args: Any, preemptive: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.preemptive = preemptive
        self._getters: List[_PriorityWaiter] = []
        self._prio_seq = 0
        self._priority = DSPriorityResource()
        self._preemption = DSPriorityPreemption(self._priority)
        # Resource-specific exception subtype allows clear nested catches:
        # except r1.Preempted / except r0.Preempted.
        self.Preempted = type(f'Preempted_{id(self):x}', (DSResourcePreempted,), {'__module__': __name__})

    class _HoldContext:
        def __init__(self, resource: "LitePriorityResource") -> None:
            self.resource = resource
            self.owner = None
            self._held_before: NumericType = 0

        def __enter__(self) -> "LitePriorityResource._HoldContext":
            self.owner = self.resource.sim.pid
            self._held_before = self.resource._held_amount(self.owner)
            return self

        def __exit__(self, exc_type, exc_val, exc_tb) -> None:
            if self.owner is None:
                return
            held_now = self.resource._held_amount(self.owner)
            acquired_in_scope = held_now - self._held_before
            if acquired_in_scope > 0:
                self.resource.put_n_nowait(acquired_in_scope)

    # ------------------------------------------------------------------
    # Holder / preemption bookkeeping
    # ------------------------------------------------------------------

    def _on_reclaimed(self, released: NumericType) -> None:
        if self._getters:
            self._request_dispatch()

    def _held_amount(self, owner: Any) -> NumericType:
        return self._priority.held_amount(owner)

    def _remove_from_bucket(self, owner: Any, priority: int) -> None:
        self._priority.remove_from_bucket(owner, priority)

    def _set_holder_amount(self, owner: Any, amount: NumericType) -> None:
        self._priority.set_holder_amount(owner, amount)

    def _remember_acquire(self, owner: Any, amount: NumericType, priority: int) -> None:
        self._priority.remember_acquire(owner, amount, priority)

    def _reclaim_from_victims(self, need: NumericType, requester: Any, priority: int) -> NumericType:
        def on_take(taken: NumericType) -> None:
            self.amount += taken

        def on_preempted(owner: Any, holder_prio: int, taken: NumericType) -> None:
            self.sim.signal(self.Preempted(self, requester, owner, holder_prio, taken), owner)

        return self._preemption.reclaim_from_victims(
            need=need,
            requester=requester,
            req_priority=priority,
            on_take=on_take,
            on_preempted=on_preempted,
            on_reclaimed=self._on_reclaimed,
        )

    def _consume_reclaimed_release(self, owner: Any, amount: NumericType) -> NumericType:
        return self._priority.consume_reclaimed_release(owner, amount)

    def _make_priority_waiter(self, amount: NumericType, priority: int = 0) -> _PriorityWaiter:
        waiter = _PriorityWaiter(self.sim._parent_process, amount, priority, self._prio_seq)
        self._prio_seq += 1
        return waiter

    def _enqueue_getter(self, waiter: _Waiter, priority: int = 0, **policy_params: Any) -> None:
        # Waiters are sorted by (priority asc, sequence asc).
        pwaiter = waiter if isinstance(waiter, _PriorityWaiter) else _PriorityWaiter(waiter.subscriber, waiter.amount, priority, self._prio_seq)
        if pwaiter is not waiter:
            self._prio_seq += 1
        idx = len(self._getters)
        key = (pwaiter.priority, pwaiter.seq)
        for i, current in enumerate(self._getters):
            if key < (current.priority, current.seq):
                idx = i
                break
        self._getters.insert(idx, pwaiter)

    def _peek_getter(self) -> Optional[_Waiter]:
        return self._getters[0] if self._getters else None

    def _pop_getter(self) -> Optional[_Waiter]:
        if not self._getters:
            return None
        return self._getters.pop(0)

    def _remove_getter(self, waiter: _Waiter) -> bool:
        try:
            self._getters.remove(waiter)
            return True
        except ValueError:
            return False

    # ------------------------------------------------------------------
    # Nowait operations
    # ------------------------------------------------------------------

    def get_nowait(self, priority: int = 0, **policy_params: Any) -> NumericType:
        return self.get_n_nowait(1, priority=priority, **policy_params)

    def get_n_nowait(self, amount: NumericType = 1, priority: int = 0, **policy_params: Any) -> NumericType:
        retval = super().get_n_nowait(amount, **policy_params)
        if retval > 0:
            self._remember_acquire(self.sim.pid, retval, priority)
        return retval

    def put_n_nowait(self, amount: NumericType = 1) -> NumericType:
        owner = self.sim.pid
        accepted = 0
        remaining = amount

        # First release currently-held amount for this owner.
        held = self._held_amount(owner)
        to_release = held if held <= remaining else remaining
        if to_release > 0:
            released = super().put_n_nowait(to_release)
            if released > 0:
                accepted += released
                remaining -= released
                self._set_holder_amount(owner, held - released)

        if remaining <= 0:
            return accepted

        # Then absorb stale release attempts for already-preempted allocations.
        before = remaining
        remaining = self._consume_reclaimed_release(owner, remaining)
        accepted += before - remaining
        if remaining <= 0:
            return accepted

        # Finally allow explicit external top-up behavior of Resource.
        accepted += super().put_n_nowait(remaining)
        return accepted

    # ------------------------------------------------------------------
    # Blocking generator operations
    # ------------------------------------------------------------------

    def gget_n(self, timeout: TimeType = float('inf'), amount: NumericType = 1, **policy_params: Any) -> Generator[EventType, None, NumericType]:
        priority = policy_params.get('priority', 0)
        preempt = policy_params.get('preempt', self.preemptive)
        owner = self.sim.pid
        if preempt and self.amount < amount:
            self._reclaim_from_victims(amount - self.amount, owner, priority)
        retval = self.get_n_nowait(amount, priority=priority)
        if retval > 0:
            return retval
        waiter = self._make_priority_waiter(amount, priority=priority)
        self._enqueue_getter(waiter, priority=priority)
        if timeout != float('inf'):
            self.sim.schedule_event(timeout, _WaitTimeout(waiter), self)
        self._request_dispatch()
        event = yield from self.sim.gwait()
        got = 0 if event is None else event
        if got > 0:
            self._remember_acquire(owner, got, priority)
        return got

    # ------------------------------------------------------------------
    # Blocking async operations
    # ------------------------------------------------------------------

    async def get_n(self, timeout: TimeType = float('inf'), amount: NumericType = 1, **policy_params: Any) -> NumericType:
        priority = policy_params.get('priority', 0)
        preempt = policy_params.get('preempt', self.preemptive)
        owner = self.sim.pid
        if preempt and self.amount < amount:
            self._reclaim_from_victims(amount - self.amount, owner, priority)
        retval = self.get_n_nowait(amount, priority=priority)
        if retval > 0:
            return retval
        waiter = self._make_priority_waiter(amount, priority=priority)
        self._enqueue_getter(waiter, priority=priority)
        if timeout != float('inf'):
            self.sim.schedule_event(timeout, _WaitTimeout(waiter), self)
        self._request_dispatch()
        event = await self.sim.wait()
        got = 0 if event is None else event
        if got > 0:
            self._remember_acquire(owner, got, priority)
        return got

    # ------------------------------------------------------------------
    # Context helpers
    # ------------------------------------------------------------------

    def autorelease(self) -> "_HoldContext":
        '''Context manager that auto-releases acquisitions done in this scope.

        Typical usage:
            with resource.autorelease():
                got = yield from resource.gget(priority=1, preempt=True)
                if got:
                    yield from sim.gwait(5)
            # released automatically here if still held
        '''
        return self._HoldContext(self)


# In the following, self is in fact of type DSSimulation, but PyLance makes troubles with variable types
class SimLiteResourceMixin:
    def resource(self: Any, *args: Any, **kwargs: Any) -> LiteResource:
        sim: 'DSSimulation' = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in resource() method should be set to the same simulation instance.')
        return LiteResource(*args, **kwargs, sim=sim)

    def priority_resource(self: Any, *args: Any, **kwargs: Any) -> LitePriorityResource:
        sim: 'DSSimulation' = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in priority_resource() method should be set to the same simulation instance.')
        return LitePriorityResource(*args, **kwargs, sim=sim)
