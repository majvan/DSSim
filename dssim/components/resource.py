# Copyright 2021- majvan (majvan@gmail.com)
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
A resource is an object representing a pool of abstract resources with amount filled in.
Compared to queue, resource works with non-integer amounts but it does not contain object
in the pool, just an abstract pool level information (e.g. amount of water in a tank).
'''
from typing import Any, Generator, TYPE_CHECKING, Optional, Dict, List
from dssim.base import NumericType, TimeType, EventType, DSComponentSingleton
from dssim.components.base import DSStatefulComponent
from dssim.pubsub import DSProducer, NotifierPriority


if TYPE_CHECKING:
    from dssim.simulation import DSSimulation


class Resource(DSStatefulComponent):
    '''Resource models a pool of virtual resource amount.

    * ``get`` consumes amount from the pool.
    * ``put`` adds amount to the pool.

    Unlike TinyResource, wakeups are pubsub-driven via ``tx_nempty``/``tx_nfull``.
    '''
    def __init__(
        self,
        amount: NumericType = 0,
        capacity: NumericType = float('inf'),
        *args: Any,
        nempty_ep: Optional[DSProducer] = None,
        nfull_ep: Optional[DSProducer] = None,
        **kwargs: Any,
    ) -> None:
        ''' Init Resource component.
        Capacity is max. capacity the resource can handle.
        Amount is initial amount of the resources.
        '''
        super().__init__(*args, **kwargs)
        if amount > capacity:
            raise ValueError('Initial amount of the resource is greater than capacity.')
        self.amount = amount
        self.capacity = capacity
        self.tx_nempty = nempty_ep if nempty_ep is not None else self.sim.producer(name=self.name + '.tx_nempty')
        self.tx_nfull = nfull_ep if nfull_ep is not None else self.sim.producer(name=self.name + '.tx_nfull')

    # ------------------------------------------------------------------
    # Internal notification hooks
    # ------------------------------------------------------------------

    def _fire_nempty(self) -> None:
        if self.tx_nempty.has_subscribers():
            self.sim.signal(self.tx_nempty, self.tx_nempty)

    def _fire_nfull(self) -> None:
        if self.tx_nfull.has_subscribers():
            self.sim.signal(self.tx_nfull, self.tx_nfull)

    def _fire_changed(self) -> None:
        if self.tx_changed.has_subscribers():
            self.sim.signal(self.tx_changed, self.tx_changed)

    # ------------------------------------------------------------------
    # Nowait operations
    # ------------------------------------------------------------------

    def put_nowait(self) -> NumericType:
        ''' Put 1 unit into the resource pool immediately. '''
        return self.put_n_nowait(1)

    def put_n_nowait(self, amount: NumericType) -> NumericType:
        ''' Put amount units into the resource pool immediately. '''
        if self.amount + amount > self.capacity:
            retval: NumericType = 0
        else:
            self.amount += amount
            self._fire_nempty()
            self._fire_changed()
            retval = amount
        return retval

    def get_nowait(self) -> NumericType:
        ''' Get 1 unit from the resource pool immediately. '''
        return self.get_n_nowait(1)

    def get_n_nowait(self, amount: NumericType = 1) -> NumericType:
        ''' Get amount units from the resource pool immediately. '''
        if amount > self.amount:
            retval: NumericType = 0
        else:
            self.amount -= amount
            self._fire_nfull()
            self._fire_changed()
            retval = amount
        return retval

    # ------------------------------------------------------------------
    # Blocking generator operations
    # ------------------------------------------------------------------

    def gput(self, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, None, NumericType]:
        ''' Put 1 unit into the resource pool (generator version), waiting if at capacity. '''
        return (yield from self.gput_n(timeout, 1, **policy_params))

    def gput_n(self, timeout: TimeType = float('inf'), amount: NumericType = 1, **policy_params: Any) -> Generator[EventType, None, NumericType]:
        ''' Put amount units into the resource pool (generator version), waiting if at capacity. '''
        with self.sim.consume(self.tx_nfull, **policy_params):
            obj = yield from self.sim.check_and_gwait(timeout, cond=lambda e:self.amount + amount <= self.capacity)
        if obj is None:
            retval: NumericType = 0
        else:
            self.amount += amount
            self._fire_nempty()
            self._fire_changed()
            retval = amount
        return retval

    def gget(self, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, None, NumericType]:
        ''' Get 1 unit from the resource pool (generator version), waiting if not available. '''
        return (yield from self.gget_n(timeout, 1, **policy_params))

    def gget_n(self, timeout: TimeType = float('inf'), amount: NumericType = 1, **policy_params: Any) -> Generator[EventType, None, NumericType]:
        ''' Get amount units from the resource pool (generator version), waiting if not available. '''
        with self.sim.consume(self.tx_nempty, **policy_params):
            obj = yield from self.sim.check_and_gwait(timeout, cond=lambda e:self.amount >= amount)
        if obj is None:
            retval: NumericType = 0
        else:
            self.amount -= amount
            self._fire_nfull()
            self._fire_changed()
            retval = amount
        return retval

    # ------------------------------------------------------------------
    # Blocking async operations
    # ------------------------------------------------------------------

    async def put(self, timeout: TimeType = float('inf'), **policy_params: Any) -> NumericType:
        ''' Put 1 unit into the resource pool, waiting if at capacity. '''
        return await self.put_n(timeout, 1, **policy_params)

    async def put_n(self, timeout: TimeType = float('inf'), amount: NumericType = 1, **policy_params: Any) -> NumericType:
        ''' Put amount units into the resource pool, waiting if at capacity. '''
        with self.sim.consume(self.tx_nfull, **policy_params):
            obj = await self.sim.check_and_wait(timeout, cond=lambda e:self.amount + amount <= self.capacity)
        if obj is None:
            retval: NumericType = 0
        else:
            self.amount += amount
            self._fire_nempty()
            self._fire_changed()
            retval = amount
        return retval

    async def get(self, timeout: TimeType = float('inf'), **policy_params: Any) -> NumericType:
        ''' Get 1 unit from the resource pool, waiting if not available. '''
        return await self.get_n(timeout, 1, **policy_params)

    async def get_n(self, timeout: TimeType = float('inf'), amount: NumericType = 1, **policy_params: Any) -> NumericType:
        ''' Get amount units from the resource pool, waiting if not available. '''
        with self.sim.consume(self.tx_nempty, **policy_params):
            obj = await self.sim.check_and_wait(timeout, cond=lambda e:self.amount >= amount)
        if obj is None:
            retval: NumericType = 0
        else:
            self.amount -= amount
            self._fire_nfull()
            self._fire_changed()
            retval = amount
        return retval


class PriorityResource(Resource):
    '''Resource variant with priority-ordered waiter wakeups.

    Lower numeric priority value is served first. Same priority keeps notifier
    policy order. With ``preempt=True``, higher priority requesters may reclaim
    units from lower-priority holders.
    '''

    def __init__(
        self,
        amount: NumericType = 0,
        capacity: NumericType = float('inf'),
        preemptive: bool = False,
        nempty_ep: Optional[DSProducer] = None,
        nfull_ep: Optional[DSProducer] = None,
        change_ep: Optional[DSProducer] = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        sim = kwargs.get('sim', DSComponentSingleton.sim_singleton)
        if sim is None:
            raise ValueError('PriorityResource requires a simulation instance (sim=...).')
        if change_ep is None:
            change_ep = sim.producer(notifier=NotifierPriority)
        if nempty_ep is None:
            nempty_ep = sim.producer(notifier=NotifierPriority)
        if nfull_ep is None:
            nfull_ep = sim.producer(notifier=NotifierPriority)
        super().__init__(
            amount=amount,
            capacity=capacity,
            change_ep=change_ep,
            nempty_ep=nempty_ep,
            nfull_ep=nfull_ep,
            *args,
            **kwargs,
        )
        self.preemptive = preemptive
        # Dual-index holder state:
        # - by owner: fast release/update for current process
        # - by priority buckets: efficient preemption candidate ordering
        self._holders_by_owner: Dict[Any, Dict[str, Any]] = {}
        self._holders_by_priority: Dict[int, List[Any]] = {}
        self._reclaimed: Dict[Any, NumericType] = {}

    class Preempted(Exception):
        def __init__(self, resource: "PriorityResource", by: Any, owner: Any, priority: int, amount: NumericType) -> None:
            super().__init__(f'{owner} was preempted on {resource} by {by} (priority={priority}, amount={amount}).')
            self.resource = resource
            self.by = by
            self.owner = owner
            self.priority = priority
            self.amount = amount

    class _HoldContext:
        def __init__(self, resource: "PriorityResource") -> None:
            self.resource = resource
            self.owner = None
            self._held_before: NumericType = 0

        def __enter__(self) -> "PriorityResource._HoldContext":
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

    def _held_amount(self, owner: Any) -> NumericType:
        state = self._holders_by_owner.get(owner)
        if state is None:
            return 0
        return state['amount']

    def _remove_from_bucket(self, owner: Any, priority: int) -> None:
        bucket = self._holders_by_priority.get(priority)
        if bucket is None:
            return
        try:
            bucket.remove(owner)
        except ValueError:
            return
        if not bucket:
            self._holders_by_priority.pop(priority, None)

    def _set_holder_amount(self, owner: Any, amount: NumericType) -> None:
        state = self._holders_by_owner.get(owner)
        if state is None:
            return
        if amount <= 0:
            self._remove_from_bucket(owner, state['priority'])
            self._holders_by_owner.pop(owner, None)
            return
        state['amount'] = amount

    def _remember_acquire(self, owner: Any, amount: NumericType, priority: int) -> None:
        state = self._holders_by_owner.get(owner)
        if state is None:
            self._holders_by_owner[owner] = {'amount': amount, 'priority': priority}
            bucket = self._holders_by_priority.setdefault(priority, [])
            bucket.append(owner)
            return

        state['amount'] += amount
        old_priority = state['priority']
        new_priority = min(old_priority, priority)
        if new_priority != old_priority:
            self._remove_from_bucket(owner, old_priority)
            state['priority'] = new_priority
            self._holders_by_priority.setdefault(new_priority, []).append(owner)
            return

        # Same-priority re-acquire: refresh recency (newest at end).
        bucket = self._holders_by_priority.setdefault(new_priority, [])
        try:
            bucket.remove(owner)
        except ValueError:
            pass
        bucket.append(owner)

    def _reclaim_from_victims(self, need: NumericType, requester: Any, priority: int) -> NumericType:
        if need <= 0:
            return 0
        released = 0
        # preempt weakest holders first:
        # larger numeric priority first, and for equal priority newest first.
        candidates = []
        for holder_prio in sorted(self._holders_by_priority.keys(), reverse=True):
            if holder_prio <= priority:
                continue
            bucket = self._holders_by_priority[holder_prio]
            for owner in reversed(bucket):
                candidates.append((holder_prio, owner))

        for holder_prio, owner in candidates:
            if need <= 0:
                break
            if owner is requester:
                continue
            state = self._holders_by_owner.get(owner)
            if state is None:
                continue
            if state['priority'] <= priority:
                continue
            held = state['amount']
            if held <= 0:
                continue
            taken = held if held <= need else need
            self._set_holder_amount(owner, held - taken)
            self._reclaimed[owner] = self._reclaimed.get(owner, 0) + taken
            self.amount += taken
            released += taken
            need -= taken
            self.sim.signal(self.Preempted(self, requester, owner, holder_prio, taken), owner)
        if released > 0:
            self._fire_nempty()
            self._fire_changed()
        return released

    def _consume_reclaimed_release(self, owner: Any, amount: NumericType) -> NumericType:
        reclaimed = self._reclaimed.get(owner, 0)
        if reclaimed <= 0:
            return amount
        consumed = reclaimed if reclaimed <= amount else amount
        left = reclaimed - consumed
        if left > 0:
            self._reclaimed[owner] = left
        else:
            self._reclaimed.pop(owner, None)
        return amount - consumed

    # ------------------------------------------------------------------
    # Nowait operations
    # ------------------------------------------------------------------

    def get_nowait(self, priority: int = 0) -> NumericType:
        return self.get_n_nowait(1, priority=priority)

    def get_n_nowait(self, amount: NumericType = 1, priority: int = 0) -> NumericType:
        retval = super().get_n_nowait(amount)
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
        retval = yield from super().gget_n(timeout=timeout, amount=amount, **policy_params)
        if retval > 0:
            self._remember_acquire(owner, retval, priority)
        return retval

    # ------------------------------------------------------------------
    # Blocking async operations
    # ------------------------------------------------------------------

    async def get_n(self, timeout: TimeType = float('inf'), amount: NumericType = 1, **policy_params: Any) -> NumericType:
        priority = policy_params.get('priority', 0)
        preempt = policy_params.get('preempt', self.preemptive)
        owner = self.sim.pid
        if preempt and self.amount < amount:
            self._reclaim_from_victims(amount - self.amount, owner, priority)
        retval = await super().get_n(timeout=timeout, amount=amount, **policy_params)
        if retval > 0:
            self._remember_acquire(owner, retval, priority)
        return retval

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


DSResourcePreempted = PriorityResource.Preempted


class Mutex(Resource):
    class _OpenContext:
        def __init__(self, mutex: "Mutex", timeout: TimeType, **policy_params: Any) -> None:
            self.mutex = mutex
            self.timeout = timeout
            self.policy_params = policy_params
            self.owner = None
            self.event: Optional[NumericType] = None

        async def __aenter__(self) -> NumericType:
            self.owner = self.mutex.sim.pid
            self.event = await self.mutex.lock(self.timeout, **self.policy_params)
            return self.event

        async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
            if self.event and self.mutex.last_owner == self.owner:
                self.mutex.release()

        def __enter__(self) -> "Mutex._OpenContext":
            # Sync context cannot await lock itself; caller may call await cm.lock().
            self.owner = self.mutex.sim.pid
            return self

        def __exit__(self, exc_type, exc_val, exc_tb) -> None:
            if self.mutex.last_owner == self.owner:
                self.mutex.release()

        async def lock(self) -> NumericType:
            self.event = await self.mutex.lock(self.timeout, **self.policy_params)
            return self.event

    def __init__(self, *args, **kwargs):
        super().__init__(1, 1, *args, **kwargs)
        self.last_owner = None

    async def lock(self, timeout=float('inf'), **policy_params: Any):
        retval = await self.get(timeout, **policy_params)
        if retval:
            # store the info that the mutext is owned by us
            self.last_owner = self.sim.pid
        return retval
    
    def open(self, timeout=float('inf'), **policy_params: Any) -> "_OpenContext":
        return self._OpenContext(self, timeout, **policy_params)

    def locked(self):
        return self.amount == 0

    def release(self):
        if self.amount == 0:
            return self.put_nowait()

    async def __aenter__(self):
        raise ValueError(f'You try to use context manager "async with {self}" but you need to use open() function for that.')

    def __enter__(self):
        # Unfortunately, it is not possible to yield here. So the caller has to yield from lock() after with
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # release the mutex only if we own the acquired mutex
        if self.last_owner == self.sim.pid:
            self.release()

    def __exit__(self, exc_type, exc_val, exc_tb):
        # release the mutex only if we own the acquired mutex
        if self.last_owner == self.sim.pid:
            self.release()


# In the following, self is in fact of type DSProcessComponent, but PyLance makes troubles with variable types
class ResourceMixin:
    async def get(self: Any, resource: Resource, timeout: TimeType = float('inf'), **policy_params: Any) -> NumericType:
        return await resource.get(timeout, **policy_params)

    def gget(self: Any, resource: Resource, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, None, NumericType]:
        return (yield from resource.gget(timeout, **policy_params))

    async def get_n(self: Any, resource: Resource, amount: NumericType = 1, timeout: TimeType = float('inf'), **policy_params: Any) -> NumericType:
        return await resource.get_n(timeout, amount, **policy_params)

    def gget_n(self: Any, resource: Resource, amount: NumericType = 1, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, None, NumericType]:
        return (yield from resource.gget_n(timeout, amount, **policy_params))

    async def put(self: Any, resource: Resource, timeout: TimeType = float('inf'), **policy_params: Any) -> NumericType:
        return await resource.put(timeout, **policy_params)

    def gput(self: Any, resource: Resource, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, None, NumericType]:
        return (yield from resource.gput(timeout, **policy_params))

    async def put_n(self: Any, resource: Resource, amount: NumericType = 1, timeout: TimeType = float('inf'), **policy_params: Any) -> NumericType:
        return await resource.put_n(timeout, amount, **policy_params)

    def gput_n(self: Any, resource: Resource, amount: NumericType = 1, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, None, NumericType]:
        return (yield from resource.gput_n(timeout, amount, **policy_params))

    def put_nowait(self: Any, resource: Resource) -> NumericType:
        return resource.put_nowait()

    def put_n_nowait(self: Any, resource: Resource, amount: NumericType = 1) -> NumericType:
        return resource.put_n_nowait(amount)



# In the following, self is in fact of type DSSimulation, but PyLance makes troubles with variable types
class SimResourceMixin:
    def resource(self: Any, *args: Any, **kwargs: Any) -> Resource:
        sim: DSSimulation = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in resource() method should be set to the same simulation instance.')
        return Resource(*args, **kwargs, sim=sim)

    def priority_resource(self: Any, *args: Any, **kwargs: Any) -> PriorityResource:
        sim: DSSimulation = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in priority_resource() method should be set to the same simulation instance.')
        return PriorityResource(*args, **kwargs, sim=sim)
