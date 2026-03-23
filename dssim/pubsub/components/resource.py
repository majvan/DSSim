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
from typing import Any, Generator, TYPE_CHECKING, Optional
from dssim.base import NumericType, TimeType, EventType, DSComponentSingleton
from dssim.base_components import _ResourceBookkeeper, DSBasePriorityResource, DSPriorityPreemption
from dssim.pubsub.cond import DSFilter
from dssim.pubsub.components.base import DSStatefulComponent
from dssim.pubsub.components.resource_probes import ResourceProbeMixin
from dssim.pubsub.pubsub import DSPub, NotifierPriority, NotifierRoundRobin
from dssim.pubsub.base import ICondition, CallableConditionMixin


if TYPE_CHECKING:
    from dssim.simulation import DSSimulation


class DSResourcePreempted(Exception):
    '''Raised when a resource holder is preempted by a higher-priority requester.'''

    def __init__(self, resource: "DSPriorityResource", by: Any, owner: Any, priority: int, amount: NumericType) -> None:
        super().__init__(f'{owner} was preempted on {resource} by {by} (priority={priority}, amount={amount}).')
        self.resource = resource
        self.by = by
        self.owner = owner
        self.priority = priority
        self.amount = amount


class DSResource(ResourceProbeMixin, DSStatefulComponent):
    '''DSResource models a pool of virtual resource amount.

    * ``get`` consumes amount from the pool.
    * ``put`` adds amount to the pool.

    Unlike DSLiteResource, wakeups are pubsub-driven via ``tx_nempty``/``tx_nfull``.
    '''

    class _GetCond(ICondition, CallableConditionMixin):
        '''Condition helper that tries immediate resource acquisition on check().'''

        def __init__(self, resource: "DSResource", amount: NumericType = 1, owner: Any = None, **policy_params: Any) -> None:
            self.resource = resource
            self.amount = amount
            self.owner = resource.sim.pid if owner is None else owner
            self.policy_params = policy_params
            self.value: NumericType = 0

        def check(self, event: EventType) -> tuple[bool, NumericType]:
            got = self.resource._try_take_n_nowait(self.amount, owner=self.owner, **self.policy_params)
            if got > 0:
                self.value = got
                return True, got
            return False, 0

        def cond_value(self) -> NumericType:
            return self.value

        def get_eps(self):
            # Waiting on policy_for_get should wake on "resource became non-empty".
            return {self.resource.tx_nempty}

        def __str__(self) -> str:
            return f'{self.resource}.policy_for_get(amount={self.amount}, policy={self.policy_params})'

    def __init__(
        self,
        amount: NumericType = 0,
        capacity: NumericType = float('inf'),
        *args: Any,
        nempty_ep: Optional[DSPub] = None,
        nfull_ep: Optional[DSPub] = None,
        ops_ep: Optional[DSPub] = None,
        **kwargs: Any,
    ) -> None:
        ''' Init DSResource component.
        Capacity is max. capacity the resource can handle.
        Amount is initial amount of the resources.
        '''
        super().__init__(*args, **kwargs)
        self._resource = _ResourceBookkeeper(amount=amount, capacity=capacity, owner=self)
        self.tx_nempty = nempty_ep if nempty_ep is not None else self.sim.publisher(name=self.name + '.tx_nempty')
        self.tx_nfull = nfull_ep if nfull_ep is not None else self.sim.publisher(name=self.name + '.tx_nfull')
        self.tx_ops = ops_ep if ops_ep is not None else self.sim.publisher(name=self.name + '.tx_ops')

    # ------------------------------------------------------------------
    # Internal notification hooks
    # ------------------------------------------------------------------

    def _try_take_n_nowait(self, amount: NumericType = 1, owner: Any = None, **policy_params: Any) -> NumericType:
        return self.get_n_nowait(amount)

    def _fire_ops(
        self,
        op: str,
        requested: NumericType,
        moved: NumericType,
        success: bool,
        blocked: bool = False,
        timeout: bool = False,
        wait_time: float = 0.0,
        api: str = '',
    ) -> None:
        if self.tx_ops.has_subscribers():
            self.sim.signal(
                {
                    'kind': 'resource_op',
                    'op': op,
                    'api': api or op,
                    'requested': float(requested),
                    'moved': float(moved),
                    'success': success,
                    'blocked': blocked,
                    'timeout': timeout,
                    'wait_time': wait_time,
                    'time': float(self.sim.time),
                    'amount': float(self.amount),
                    'capacity': float(self.capacity),
                },
                self.tx_ops,
            )

    # ------------------------------------------------------------------
    # Nowait operations
    # ------------------------------------------------------------------

    def policy_for_get(self, amount: NumericType = 1, **policy_params: Any) -> dict[str, Any]:
        '''Return DSFilter policy dict for acquire-on-check behavior.

        Typical usage:
            f = sim.filter(resource.policy_for_get(amount=1, priority=prio, preempt=True))
            got = yield from f.check_and_gwait(10)
        '''
        cond_obj = self._GetCond(self, amount, owner=self.sim.pid, **policy_params)
        return {
            'cond': cond_obj,
            'sigtype': DSFilter.SignalType.LATCH,
            'eps': {self.tx_nempty: {'tier': self.tx_nempty.Phase.CONSUME, 'params': dict(policy_params)}},
            'one_shot': True,
        }

    def put_nowait(self) -> NumericType:
        ''' Put 1 unit into the resource pool immediately. '''
        return self.put_n_nowait(1)

    def put_n_nowait(self, amount: NumericType) -> NumericType:
        ''' Put amount units into the resource pool immediately. '''
        requested = amount
        retval = self._resource.put_n_nowait(amount)
        if retval > 0:
            self.tx_nempty.has_subscribers() and self.sim.signal(self.tx_nempty, self.tx_nempty)
            self.tx_changed.has_subscribers() and self.sim.signal(self.tx_changed, self.tx_changed)
            self.tx_ops.has_subscribers() and self._fire_ops('put', requested=requested, moved=retval, success=True, api='put_n_nowait')
        else:
            self.tx_ops.has_subscribers() and self._fire_ops('put', requested=requested, moved=0, success=False, api='put_n_nowait')
        return retval

    def get_nowait(self, **policy_params: Any) -> NumericType:
        ''' Get 1 unit from the resource pool immediately. '''
        return self.get_n_nowait(1, **policy_params)

    def get_n_nowait(self, amount: NumericType = 1, **policy_params: Any) -> NumericType:
        ''' Get amount units from the resource pool immediately. '''
        requested = amount
        retval = self._resource.get_n_nowait(amount)
        if retval > 0:
            self.tx_nfull.has_subscribers() and self.sim.signal(self.tx_nfull, self.tx_nfull)
            self.tx_changed.has_subscribers() and self.sim.signal(self.tx_changed, self.tx_changed)
            self.tx_ops.has_subscribers() and self._fire_ops('get', requested=requested, moved=retval, success=True, api='get_n_nowait')
        else:
            self.tx_ops.has_subscribers() and self._fire_ops('get', requested=requested, moved=0, success=False, api='get_n_nowait')
        return retval

    # ------------------------------------------------------------------
    # Blocking generator operations
    # ------------------------------------------------------------------

    def gput(self, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, None, NumericType]:
        ''' Put 1 unit into the resource pool (generator version), waiting if at capacity. '''
        return (yield from self.gput_n(timeout, 1, **policy_params))

    def gput_n(self, timeout: TimeType = float('inf'), amount: NumericType = 1, **policy_params: Any) -> Generator[EventType, None, NumericType]:
        ''' Put amount units into the resource pool (generator version), waiting if at capacity. '''
        t_start = float(self.sim.time)
        if self.amount + amount <= self.capacity:
            retval = self._resource.put_n_nowait(amount)
            if retval > 0:
                self.tx_nempty.has_subscribers() and self.sim.signal(self.tx_nempty, self.tx_nempty)
                self.tx_changed.has_subscribers() and self.sim.signal(self.tx_changed, self.tx_changed)
                self.tx_ops.has_subscribers() and self._fire_ops(
                    'put', requested=amount, moved=retval, success=True, blocked=False, wait_time=0.0, api='gput_n'
                )
            else:
                self.tx_ops.has_subscribers() and self._fire_ops(
                    'put', requested=amount, moved=0, success=False, blocked=False, wait_time=0.0, api='gput_n'
                )
            return retval
        with self.sim.consume(self.tx_nfull, **policy_params):
            obj = yield from self.sim.gwait(timeout, cond=lambda e:self.amount + amount <= self.capacity)
        waited = float(self.sim.time) - t_start
        if obj is None:
            retval: NumericType = 0
            self.tx_ops.has_subscribers() and self._fire_ops(
                'put', requested=amount, moved=0, success=False, blocked=True, timeout=True, wait_time=waited, api='gput_n'
            )
        else:
            retval = self._resource.put_n_nowait(amount)
            if retval > 0:
                self.tx_nempty.has_subscribers() and self.sim.signal(self.tx_nempty, self.tx_nempty)
                self.tx_changed.has_subscribers() and self.sim.signal(self.tx_changed, self.tx_changed)
                self.tx_ops.has_subscribers() and self._fire_ops(
                    'put', requested=amount, moved=retval, success=True, blocked=True, wait_time=waited, api='gput_n'
                )
            else:
                self.tx_ops.has_subscribers() and self._fire_ops(
                    'put', requested=amount, moved=0, success=False, blocked=True, wait_time=waited, api='gput_n'
                )
        return retval

    def gget(self, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, None, NumericType]:
        ''' Get 1 unit from the resource pool (generator version), waiting if not available. '''
        return (yield from self.gget_n(timeout, 1, **policy_params))

    def gget_n(self, timeout: TimeType = float('inf'), amount: NumericType = 1, **policy_params: Any) -> Generator[EventType, None, NumericType]:
        ''' Get amount units from the resource pool (generator version), waiting if not available. '''
        t_start = float(self.sim.time)
        if self.amount >= amount:
            retval = self._resource.get_n_nowait(amount)
            if retval > 0:
                self.tx_nfull.has_subscribers() and self.sim.signal(self.tx_nfull, self.tx_nfull)
                self.tx_changed.has_subscribers() and self.sim.signal(self.tx_changed, self.tx_changed)
                self.tx_ops.has_subscribers() and self._fire_ops(
                    'get', requested=amount, moved=retval, success=True, blocked=False, wait_time=0.0, api='gget_n'
                )
            else:
                self.tx_ops.has_subscribers() and self._fire_ops(
                    'get', requested=amount, moved=0, success=False, blocked=False, wait_time=0.0, api='gget_n'
                )
            return retval
        with self.sim.consume(self.tx_nempty, **policy_params):
            obj = yield from self.sim.gwait(timeout, cond=lambda e:self.amount >= amount)
        waited = float(self.sim.time) - t_start
        if obj is None:
            retval: NumericType = 0
            self.tx_ops.has_subscribers() and self._fire_ops(
                'get', requested=amount, moved=0, success=False, blocked=True, timeout=True, wait_time=waited, api='gget_n'
            )
        else:
            retval = self._resource.get_n_nowait(amount)
            if retval > 0:
                self.tx_nfull.has_subscribers() and self.sim.signal(self.tx_nfull, self.tx_nfull)
                self.tx_changed.has_subscribers() and self.sim.signal(self.tx_changed, self.tx_changed)
                self.tx_ops.has_subscribers() and self._fire_ops(
                    'get', requested=amount, moved=retval, success=True, blocked=True, wait_time=waited, api='gget_n'
                )
            else:
                self.tx_ops.has_subscribers() and self._fire_ops(
                    'get', requested=amount, moved=0, success=False, blocked=True, wait_time=waited, api='gget_n'
                )
        return retval

    # ------------------------------------------------------------------
    # Blocking async operations
    # ------------------------------------------------------------------

    async def put(self, timeout: TimeType = float('inf'), **policy_params: Any) -> NumericType:
        ''' Put 1 unit into the resource pool, waiting if at capacity. '''
        return await self.put_n(timeout, 1, **policy_params)

    async def put_n(self, timeout: TimeType = float('inf'), amount: NumericType = 1, **policy_params: Any) -> NumericType:
        ''' Put amount units into the resource pool, waiting if at capacity. '''
        t_start = float(self.sim.time)
        if self.amount + amount <= self.capacity:
            retval = self._resource.put_n_nowait(amount)
            if retval > 0:
                self.tx_nempty.has_subscribers() and self.sim.signal(self.tx_nempty, self.tx_nempty)
                self.tx_changed.has_subscribers() and self.sim.signal(self.tx_changed, self.tx_changed)
                self.tx_ops.has_subscribers() and self._fire_ops(
                    'put', requested=amount, moved=retval, success=True, blocked=False, wait_time=0.0, api='put_n'
                )
            else:
                self.tx_ops.has_subscribers() and self._fire_ops(
                    'put', requested=amount, moved=0, success=False, blocked=False, wait_time=0.0, api='put_n'
                )
            return retval
        with self.sim.consume(self.tx_nfull, **policy_params):
            obj = await self.sim.wait(timeout, cond=lambda e:self.amount + amount <= self.capacity)
        waited = float(self.sim.time) - t_start
        if obj is None:
            retval: NumericType = 0
            self.tx_ops.has_subscribers() and self._fire_ops(
                'put', requested=amount, moved=0, success=False, blocked=True, timeout=True, wait_time=waited, api='put_n'
            )
        else:
            retval = self._resource.put_n_nowait(amount)
            if retval > 0:
                self.tx_nempty.has_subscribers() and self.sim.signal(self.tx_nempty, self.tx_nempty)
                self.tx_changed.has_subscribers() and self.sim.signal(self.tx_changed, self.tx_changed)
                self.tx_ops.has_subscribers() and self._fire_ops(
                    'put', requested=amount, moved=retval, success=True, blocked=True, wait_time=waited, api='put_n'
                )
            else:
                self.tx_ops.has_subscribers() and self._fire_ops(
                    'put', requested=amount, moved=0, success=False, blocked=True, wait_time=waited, api='put_n'
                )
        return retval

    async def get(self, timeout: TimeType = float('inf'), **policy_params: Any) -> NumericType:
        ''' Get 1 unit from the resource pool, waiting if not available. '''
        return await self.get_n(timeout, 1, **policy_params)

    async def get_n(self, timeout: TimeType = float('inf'), amount: NumericType = 1, **policy_params: Any) -> NumericType:
        ''' Get amount units from the resource pool, waiting if not available. '''
        t_start = float(self.sim.time)
        if self.amount >= amount:
            retval = self._resource.get_n_nowait(amount)
            if retval > 0:
                self.tx_nfull.has_subscribers() and self.sim.signal(self.tx_nfull, self.tx_nfull)
                self.tx_changed.has_subscribers() and self.sim.signal(self.tx_changed, self.tx_changed)
                self.tx_ops.has_subscribers() and self._fire_ops(
                    'get', requested=amount, moved=retval, success=True, blocked=False, wait_time=0.0, api='get_n'
                )
            else:
                self.tx_ops.has_subscribers() and self._fire_ops(
                    'get', requested=amount, moved=0, success=False, blocked=False, wait_time=0.0, api='get_n'
                )
            return retval
        with self.sim.consume(self.tx_nempty, **policy_params):
            obj = await self.sim.wait(timeout, cond=lambda e:self.amount >= amount)
        waited = float(self.sim.time) - t_start
        if obj is None:
            retval: NumericType = 0
            self.tx_ops.has_subscribers() and self._fire_ops(
                'get', requested=amount, moved=0, success=False, blocked=True, timeout=True, wait_time=waited, api='get_n'
            )
        else:
            retval = self._resource.get_n_nowait(amount)
            if retval > 0:
                self.tx_nfull.has_subscribers() and self.sim.signal(self.tx_nfull, self.tx_nfull)
                self.tx_changed.has_subscribers() and self.sim.signal(self.tx_changed, self.tx_changed)
                self.tx_ops.has_subscribers() and self._fire_ops(
                    'get', requested=amount, moved=retval, success=True, blocked=True, wait_time=waited, api='get_n'
                )
            else:
                self.tx_ops.has_subscribers() and self._fire_ops(
                    'get', requested=amount, moved=0, success=False, blocked=True, wait_time=waited, api='get_n'
                )
        return retval


class DSUnitResource(DSResource):
    '''Unit-only DSResource specialization.

    This variant enforces amount=1 operations and uses round-robin notifiers
    for nempty/nfull endpoints so each signal wakes one waiter path.
    '''

    def __init__(
        self,
        amount: NumericType = 0,
        capacity: NumericType = float('inf'),
        *args: Any,
        nempty_ep: Optional[DSPub] = None,
        nfull_ep: Optional[DSPub] = None,
        **kwargs: Any,
    ) -> None:
        sim = kwargs.get('sim', DSComponentSingleton.sim_singleton)
        if sim is None:
            raise ValueError('DSUnitResource requires a simulation instance (sim=...).')
        if nempty_ep is None:
            nempty_ep = sim.publisher(notifier=NotifierRoundRobin)
        if nfull_ep is None:
            nfull_ep = sim.publisher(notifier=NotifierRoundRobin)
        super().__init__(
            amount=amount,
            capacity=capacity,
            nempty_ep=nempty_ep,
            nfull_ep=nfull_ep,
            *args,
            **kwargs,
        )

    @staticmethod
    def _assert_unit_amount(amount: NumericType) -> None:
        if amount != 1:
            raise ValueError('DSUnitResource supports only amount=1 operations.')

    def _can_put_unit(self, _event: EventType) -> bool:
        return self.amount < self.capacity

    def _can_get_unit(self, _event: EventType) -> bool:
        return self.amount > 0

    def put_n_nowait(self, amount: NumericType) -> NumericType:
        self._assert_unit_amount(amount)
        return DSResource.put_n_nowait(self, 1)

    def get_n_nowait(self, amount: NumericType = 1, **policy_params: Any) -> NumericType:
        self._assert_unit_amount(amount)
        return DSResource.get_n_nowait(self, 1, **policy_params)

    def gput(self, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, None, NumericType]:
        return (yield from DSResource.gput_n(self, timeout=timeout, amount=1, **policy_params))

    def gput_n(self, timeout: TimeType = float('inf'), amount: NumericType = 1, **policy_params: Any) -> Generator[EventType, None, NumericType]:
        self._assert_unit_amount(amount)
        return (yield from self.gput(timeout, **policy_params))

    def gget(self, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, None, NumericType]:
        return (yield from DSResource.gget_n(self, timeout=timeout, amount=1, **policy_params))

    def gget_n(self, timeout: TimeType = float('inf'), amount: NumericType = 1, **policy_params: Any) -> Generator[EventType, None, NumericType]:
        self._assert_unit_amount(amount)
        return (yield from self.gget(timeout, **policy_params))

    async def put(self, timeout: TimeType = float('inf'), **policy_params: Any) -> NumericType:
        return await DSResource.put_n(self, timeout=timeout, amount=1, **policy_params)

    async def put_n(self, timeout: TimeType = float('inf'), amount: NumericType = 1, **policy_params: Any) -> NumericType:
        self._assert_unit_amount(amount)
        return await self.put(timeout, **policy_params)

    async def get(self, timeout: TimeType = float('inf'), **policy_params: Any) -> NumericType:
        return await DSResource.get_n(self, timeout=timeout, amount=1, **policy_params)

    async def get_n(self, timeout: TimeType = float('inf'), amount: NumericType = 1, **policy_params: Any) -> NumericType:
        self._assert_unit_amount(amount)
        return await self.get(timeout, **policy_params)


class DSPriorityResource(DSResource):
    '''DSResource variant with priority-ordered waiter wakeups.

    Lower numeric priority value is served first. Same priority keeps notifier
    policy order. With ``preempt=True``, higher priority requesters may reclaim
    units from lower-priority holders.
    '''
    Preempted = DSResourcePreempted

    def __init__(
        self,
        amount: NumericType = 0,
        capacity: NumericType = float('inf'),
        preemptive: bool = False,
        nempty_ep: Optional[DSPub] = None,
        nfull_ep: Optional[DSPub] = None,
        change_ep: Optional[DSPub] = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        sim = kwargs.get('sim', DSComponentSingleton.sim_singleton)
        if sim is None:
            raise ValueError('DSPriorityResource requires a simulation instance (sim=...).')
        if change_ep is None:
            change_ep = sim.publisher(notifier=NotifierPriority)
        if nempty_ep is None:
            nempty_ep = sim.publisher(notifier=NotifierPriority)
        if nfull_ep is None:
            nfull_ep = sim.publisher(notifier=NotifierPriority)
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
        self._priority = DSBasePriorityResource()
        self._preemption = DSPriorityPreemption(self._priority)
        self.preempt_count = 0
        self.preempted_amount: NumericType = 0
        # DSResource-specific exception subtype allows clear nested catches:
        # except r1.Preempted / except r0.Preempted.
        self.Preempted = type(f'Preempted_{id(self):x}', (DSResourcePreempted,), {'__module__': __name__})

    class _HoldContext:
        def __init__(self, resource: "DSPriorityResource") -> None:
            self.resource = resource
            self.owner = None
            self._held_before: NumericType = 0

        def __enter__(self) -> "DSPriorityResource._HoldContext":
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
        self.tx_nempty.has_subscribers() and self.sim.signal(self.tx_nempty, self.tx_nempty)
        self.tx_changed.has_subscribers() and self.sim.signal(self.tx_changed, self.tx_changed)

    def _held_amount(self, owner: Any) -> NumericType:
        return self._priority.held_amount(owner)

    def held_amount(self, owner: Any) -> NumericType:
        '''Public introspection helper: amount currently held by *owner*.'''
        return self._held_amount(owner)

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
            self.preempt_count += 1
            self.preempted_amount += taken
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

    # ------------------------------------------------------------------
    # Nowait operations
    # ------------------------------------------------------------------

    def _try_take_n_nowait(self, amount: NumericType = 1, owner: Any = None, **policy_params: Any) -> NumericType:
        priority = policy_params.get('priority', 0)
        preempt = policy_params.get('preempt', self.preemptive)
        owner = self.sim.pid if owner is None else owner
        if preempt and self.amount < amount:
            self._reclaim_from_victims(amount - self.amount, owner, priority)
        return self._get_n_nowait_for_owner(owner, amount, priority)

    def _get_n_nowait_for_owner(self, owner: Any, amount: NumericType = 1, priority: int = 0) -> NumericType:
        retval = super().get_n_nowait(amount)
        if retval > 0:
            self._remember_acquire(owner, retval, priority)
        return retval

    def get_nowait(self, priority: int = 0) -> NumericType:
        return self.get_n_nowait(1, priority=priority)

    def get_n_nowait(self, amount: NumericType = 1, priority: int = 0) -> NumericType:
        return self._get_n_nowait_for_owner(self.sim.pid, amount, priority)

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

        # Finally allow explicit external top-up behavior of DSResource.
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
                    yield from sim.gsleep(5)
            # released automatically here if still held
        '''
        return self._HoldContext(self)

class DSMutex(DSResource):
    class _OpenContext:
        def __init__(self, mutex: "DSMutex", timeout: TimeType, **policy_params: Any) -> None:
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

        def __enter__(self) -> "DSMutex._OpenContext":
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


# In the following, self is in fact of type DSAgent, but PyLance makes troubles with variable types
class ResourceMixin:
    async def get(self: Any, resource: DSResource, timeout: TimeType = float('inf'), **policy_params: Any) -> NumericType:
        return await resource.get(timeout, **policy_params)

    def gget(self: Any, resource: DSResource, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, None, NumericType]:
        return (yield from resource.gget(timeout, **policy_params))

    async def get_n(self: Any, resource: DSResource, amount: NumericType = 1, timeout: TimeType = float('inf'), **policy_params: Any) -> NumericType:
        return await resource.get_n(timeout, amount, **policy_params)

    def gget_n(self: Any, resource: DSResource, amount: NumericType = 1, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, None, NumericType]:
        return (yield from resource.gget_n(timeout, amount, **policy_params))

    async def put(self: Any, resource: DSResource, timeout: TimeType = float('inf'), **policy_params: Any) -> NumericType:
        return await resource.put(timeout, **policy_params)

    def gput(self: Any, resource: DSResource, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, None, NumericType]:
        return (yield from resource.gput(timeout, **policy_params))

    async def put_n(self: Any, resource: DSResource, amount: NumericType = 1, timeout: TimeType = float('inf'), **policy_params: Any) -> NumericType:
        return await resource.put_n(timeout, amount, **policy_params)

    def gput_n(self: Any, resource: DSResource, amount: NumericType = 1, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, None, NumericType]:
        return (yield from resource.gput_n(timeout, amount, **policy_params))

    def put_nowait(self: Any, resource: DSResource) -> NumericType:
        return resource.put_nowait()

    def put_n_nowait(self: Any, resource: DSResource, amount: NumericType = 1) -> NumericType:
        return resource.put_n_nowait(amount)



# In the following, self is in fact of type DSSimulation, but PyLance makes troubles with variable types
class SimResourceMixin:
    def resource(self: Any, *args: Any, **kwargs: Any) -> DSResource:
        sim: DSSimulation = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in resource() method should be set to the same simulation instance.')
        return DSResource(*args, **kwargs, sim=sim)

    def unit_resource(self: Any, *args: Any, **kwargs: Any) -> DSUnitResource:
        sim: DSSimulation = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in unit_resource() method should be set to the same simulation instance.')
        return DSUnitResource(*args, **kwargs, sim=sim)

    def priority_resource(self: Any, *args: Any, **kwargs: Any) -> DSPriorityResource:
        sim: DSSimulation = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in priority_resource() method should be set to the same simulation instance.')
        return DSPriorityResource(*args, **kwargs, sim=sim)
