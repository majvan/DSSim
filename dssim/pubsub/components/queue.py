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
The file implements the DSQueue simulation component.
'''
from typing import Any, List, Iterator, Optional, Generator, TYPE_CHECKING, Callable, Dict
from dssim.base import NumericType, TimeType, EventType, EventRetType, SignalMixin
from dssim.pubsub.base import CondType, DSAbortException, AlwaysTrue, ICondition, CallableConditionMixin, TestObject
from dssim.pubsub.cond import DSFilter
from dssim.pubsub.components.base import DSStatefulComponent
from dssim.pubsub.components.queue_probes import QueueProbeMixin
from dssim.pubsub.pubsub import DSPub
from dssim.base_components import DSBaseOrder, DSLifoOrder, DSKeyOrder


if TYPE_CHECKING:
    from dssim.simulation import DSSimulation


class DSQueue(QueueProbeMixin, DSStatefulComponent, SignalMixin):
    '''A queue component backed by three DSBaseOrder instances:

    - buffer:  items currently in transit (policy controlled by *policy*)
    - putters: processes blocked waiting to put (full buffer)
    - getters: processes blocked waiting to get (empty buffer)

    Exposes ``buffer``, ``putters`` and ``getters`` properties for
    observability / statistics.

    The *policy* parameter accepts a DSBaseOrder instance that acts as the buffer.
    Pass ``None`` (default) for FIFO, ``DSLifoOrder()`` for LIFO, or any
    ``DSKeyOrder(key=...)`` for priority ordering.
    '''

    def __init__(self, capacity: NumericType = float('inf'), policy: DSBaseOrder = None,
                 nempty_ep: Optional[DSPub] = None, nfull_ep: Optional[DSPub] = None,
                 ops_ep: Optional[DSPub] = None,
                 *args: Any, **policy_params: Any) -> None:
        super().__init__(*args, **policy_params)
        self.capacity = capacity
        self._buffer = policy if policy is not None else DSBaseOrder()
        # Three targeted producers reduce spurious wakeups:
        #   getters with simple cond → subscribe to tx_nempty
        #   putters with simple cond → subscribe to tx_nfull
        #   getters/putters with complex cond → subscribe to tx_changed
        # nempty_ep / nfull_ep allow injecting a custom notifier (e.g. NotifierPriority)
        # so that priority-ordered waiting works on the hot tx_nempty / tx_nfull paths.
        # self.tx_changed already defined by DSStatefulComponent (accepts change_ep=)
        self.tx_nempty = nempty_ep if nempty_ep is not None else self.sim.publisher(name=self.name + '.tx_nempty')
        self.tx_nfull  = nfull_ep  if nfull_ep  is not None else self.sim.publisher(name=self.name + '.tx_nfull')
        # tx_ops emits operation-level events (attempt/success/failure), intended
        # for dedicated operational probes.
        self.tx_ops    = ops_ep    if ops_ep    is not None else self.sim.publisher(name=self.name + '.tx_ops')
        self.LAMBDA1 = lambda _: len(self._buffer) >= 1

    # ---- send (SignalMixin interface) ---------------------------------------

    def send(self, event: EventType) -> bool:
        return self.put_nowait(event) is not None

    def _fire_ops(self, op: str, requested: int, moved: int,
                  success: bool, blocked: bool = False, timeout: bool = False,
                  wait_time: float = 0.0, api: str = '',
                  items_in: Optional[list[EventType]] = None,
                  items_out: Optional[list[EventType]] = None) -> None:
        if self.tx_ops.has_subscribers():
            self.sim.signal(
                {
                    'kind': 'queue_op',
                    'op': op,
                    'api': api or op,
                    'requested': requested,
                    'moved': moved,
                    'success': success,
                    'blocked': blocked,
                    'timeout': timeout,
                    'wait_time': wait_time,
                    'time': float(self.sim.time),
                    'items_in': tuple(items_in) if items_in else (),
                    'items_out': tuple(items_out) if items_out else (),
                    'queue_len': len(self._buffer),
                },
                self.tx_ops,
            )

    class _GetCond(ICondition, CallableConditionMixin):
        '''Condition helper that tries immediate dequeue on check().'''

        def __init__(self, queue: "DSQueue", amount: int = 1, cond: CondType = AlwaysTrue) -> None:
            self.queue = queue
            self.amount = amount
            self.cond = cond
            self.value: Optional[EventType] = None

        def check(self, event: EventType) -> tuple[bool, Optional[EventType]]:
            if self.amount == 1:
                got = self.queue.get_nowait(cond=self.cond)
            else:
                got = self.queue.get_n_nowait(amount=self.amount, cond=self.cond)
            if got is not None:
                self.value = got
                return True, got
            return False, None

        def cond_value(self) -> Optional[EventType]:
            return self.value

        def get_eps(self):
            return {self.queue._get_tx_endpoint(self.cond)}

        def __str__(self) -> str:
            return f'{self.queue}.policy_for_get(amount={self.amount}, cond={self.cond})'

        def gwait(self, timeout: TimeType = float('inf'), val: EventRetType = True, **policy_params: Any) -> Generator[EventType, EventType, EventType]:
            with self.queue.sim.consume(*self.get_eps(), **policy_params):
                return (yield from self.queue.sim.gwait(timeout=timeout, cond=self, val=val))

        async def wait(self, timeout: TimeType = float('inf'), val: EventRetType = True, **policy_params: Any) -> EventType:
            with self.queue.sim.consume(*self.get_eps(), **policy_params):
                return await self.queue.sim.wait(timeout=timeout, cond=self, val=val)

        def check_and_gwait(self, timeout: TimeType = float('inf'), val: EventRetType = True, **policy_params: Any) -> Generator[EventType, EventType, EventType]:
            signaled, event = self.check(TestObject)
            if signaled:
                return event
            with self.queue.sim.consume(*self.get_eps(), **policy_params):
                return (yield from self.queue.sim.gwait(timeout=timeout, cond=self, val=val))

        async def check_and_wait(self, timeout: TimeType = float('inf'), val: EventRetType = True, **policy_params: Any) -> EventType:
            signaled, event = self.check(TestObject)
            if signaled:
                return event
            with self.queue.sim.consume(*self.get_eps(), **policy_params):
                return await self.queue.sim.wait(timeout=timeout, cond=self, val=val)

    class _PutCond(ICondition, CallableConditionMixin):
        '''Condition helper that tries immediate enqueue on check().'''

        def __init__(self, queue: "DSQueue", obj: tuple[EventType, ...]) -> None:
            self.queue = queue
            self.obj = obj
            self.value: Optional[tuple] = None

        def check(self, event: EventType) -> tuple[bool, Optional[tuple]]:
            put = self.queue.put_nowait(*self.obj)
            if put is not None:
                self.value = put
                return True, put
            return False, None

        def cond_value(self) -> Optional[tuple]:
            return self.value

        def get_eps(self):
            return {self.queue.tx_nfull}

        def __str__(self) -> str:
            return f'{self.queue}.policy_for_put(obj={self.obj})'

        def gwait(self, timeout: TimeType = float('inf'), val: EventRetType = True, **policy_params: Any) -> Generator[EventType, EventType, EventType]:
            with self.queue.sim.consume(*self.get_eps(), **policy_params):
                return (yield from self.queue.sim.gwait(timeout=timeout, cond=self, val=val))

        async def wait(self, timeout: TimeType = float('inf'), val: EventRetType = True, **policy_params: Any) -> EventType:
            with self.queue.sim.consume(*self.get_eps(), **policy_params):
                return await self.queue.sim.wait(timeout=timeout, cond=self, val=val)

        def check_and_gwait(self, timeout: TimeType = float('inf'), val: EventRetType = True, **policy_params: Any) -> Generator[EventType, EventType, EventType]:
            signaled, event = self.check(TestObject)
            if signaled:
                return event
            with self.queue.sim.consume(*self.get_eps(), **policy_params):
                return (yield from self.queue.sim.gwait(timeout=timeout, cond=self, val=val))

        async def check_and_wait(self, timeout: TimeType = float('inf'), val: EventRetType = True, **policy_params: Any) -> EventType:
            signaled, event = self.check(TestObject)
            if signaled:
                return event
            with self.queue.sim.consume(*self.get_eps(), **policy_params):
                return await self.queue.sim.wait(timeout=timeout, cond=self, val=val)

    class _ChangeCond(ICondition, CallableConditionMixin):
        '''Condition helper that watches queue state changes without consuming.'''

        def __init__(self, queue: "DSQueue", cond: Callable[["DSQueue"], bool]) -> None:
            self.queue = queue
            self.cond = cond
            self.value: Optional[EventType] = None

        def check(self, event: EventType) -> tuple[bool, Optional[EventType]]:
            if self.cond(self.queue):
                self.value = event
                return True, event
            return False, None

        def cond_value(self) -> Optional[EventType]:
            return self.value

        def get_eps(self):
            return {self.queue.tx_changed}

        def __str__(self) -> str:
            return f'{self.queue}.policy_for_observe(cond={self.cond})'

        def gwait(self, timeout: TimeType = float('inf'), val: EventRetType = True, **policy_params: Any) -> Generator[EventType, EventType, EventType]:
            with self.queue.sim.observe_pre(*self.get_eps(), **policy_params):
                return (yield from self.queue.sim.gwait(timeout=timeout, cond=self, val=val))

        async def wait(self, timeout: TimeType = float('inf'), val: EventRetType = True, **policy_params: Any) -> EventType:
            with self.queue.sim.observe_pre(*self.get_eps(), **policy_params):
                return await self.queue.sim.wait(timeout=timeout, cond=self, val=val)

        def check_and_gwait(self, timeout: TimeType = float('inf'), val: EventRetType = True, **policy_params: Any) -> Generator[EventType, EventType, EventType]:
            signaled, event = self.check(TestObject)
            if signaled:
                return event
            with self.queue.sim.observe_pre(*self.get_eps(), **policy_params):
                return (yield from self.queue.sim.gwait(timeout=timeout, cond=self, val=val))

        async def check_and_wait(self, timeout: TimeType = float('inf'), val: EventRetType = True, **policy_params: Any) -> EventType:
            signaled, event = self.check(TestObject)
            if signaled:
                return event
            with self.queue.sim.observe_pre(*self.get_eps(), **policy_params):
                return await self.queue.sim.wait(timeout=timeout, cond=self, val=val)

    # ---- put side ----------------------------------------------------------

    def policy_for_get(self, amount: int = 1, cond: CondType = AlwaysTrue) -> Dict[str, Any]:
        '''Return DSFilter policy dict for dequeue-on-check behavior.'''
        if amount < 1:
            raise ValueError('policy_for_get amount must be >= 1.')
        cond_obj = self._GetCond(self, amount=amount, cond=cond)
        tx = self._get_tx_endpoint(cond)
        return {
            'cond': cond_obj,
            'sigtype': DSFilter.SignalType.LATCH,
            'eps': {tx: tx.Phase.CONSUME},
            'one_shot': True,
        }

    def policy_for_put(self, *obj: EventType) -> Dict[str, Any]:
        '''Return DSFilter policy dict for enqueue-on-check behavior.'''
        if len(obj) == 0:
            raise ValueError('policy_for_put requires at least one object.')
        cond_obj = self._PutCond(self, obj=obj)
        return {
            'cond': cond_obj,
            'sigtype': DSFilter.SignalType.LATCH,
            'eps': {self.tx_nfull: self.tx_nfull.Phase.CONSUME},
            'one_shot': True,
        }

    def policy_for_observe(self, cond: Callable[["DSQueue"], bool] = lambda _q: True) -> Dict[str, Any]:
        '''Return DSFilter policy dict for tx_changed queue-state checks.'''
        cond_obj = self._ChangeCond(self, cond=cond)
        return {
            'cond': cond_obj,
            'sigtype': DSFilter.SignalType.LATCH,
            'eps': {self.tx_changed: self.tx_changed.Phase.PRE},
            'one_shot': True,
        }

    def put_nowait(self, *obj: EventType) -> Optional[tuple]:
        '''Put item(s) into buffer immediately. Returns the obj tuple on success, None if full.'''
        requested = len(obj)
        if len(self._buffer) + len(obj) <= self.capacity:
            for item in obj:
                self._buffer.enqueue(item)
            self.tx_nempty.has_subscribers() and self.sim.signal(self.tx_nempty, self.tx_nempty)
            self.tx_changed.has_subscribers() and self.sim.signal(self.tx_changed, self.tx_changed)
            self.tx_ops.has_subscribers() and self._fire_ops(
                'put', requested=requested, moved=requested, success=True,
                api='put_nowait', items_in=list(obj),
            )
            return obj
        self.tx_ops.has_subscribers() and self._fire_ops('put', requested=requested, moved=0, success=False, api='put_nowait')
        return None

    async def put(self, timeout: TimeType = float('inf'), *obj: EventType, **policy_params: Any) -> EventType:
        '''Put item(s) into buffer, waiting up to *timeout* if the buffer is full.'''
        requested = len(obj)
        t_start = float(self.sim.time)
        if len(self._buffer) + len(obj) <= self.capacity:
            for item in obj:
                self._buffer.enqueue(item)
            self.tx_nempty.has_subscribers() and self.sim.signal(self.tx_nempty, self.tx_nempty)
            self.tx_changed.has_subscribers() and self.sim.signal(self.tx_changed, self.tx_changed)
            self.tx_ops.has_subscribers() and self._fire_ops(
                'put', requested=requested, moved=requested, success=True, blocked=False,
                wait_time=0.0, api='put', items_in=list(obj),
            )
            return True
        with self.sim.consume(self.tx_nfull, **policy_params):
            retval = await self.sim.wait(
                timeout,
                cond=lambda e: len(self._buffer) + len(obj) <= self.capacity,
            )
        waited = float(self.sim.time) - t_start
        if retval is not None:
            for item in obj:
                self._buffer.enqueue(item)
            self.tx_nempty.has_subscribers() and self.sim.signal(self.tx_nempty, self.tx_nempty)
            self.tx_changed.has_subscribers() and self.sim.signal(self.tx_changed, self.tx_changed)
            self.tx_ops.has_subscribers() and self._fire_ops(
                'put', requested=requested, moved=requested, success=True, blocked=True,
                wait_time=waited, api='put', items_in=list(obj),
            )
        else:
            self.tx_ops.has_subscribers() and self._fire_ops(
                'put', requested=requested, moved=0, success=False, blocked=True, timeout=True,
                wait_time=waited, api='put',
            )
        return retval

    def gput(self, timeout: TimeType = float('inf'), *obj: EventType, **policy_params: Any) -> Generator[EventType, EventType, EventType]:
        '''Put item(s) into buffer (generator version), waiting up to *timeout* if full.'''
        requested = len(obj)
        t_start = float(self.sim.time)
        if len(self._buffer) + len(obj) <= self.capacity:
            for item in obj:
                self._buffer.enqueue(item)
            self.tx_nempty.has_subscribers() and self.sim.signal(self.tx_nempty, self.tx_nempty)
            self.tx_changed.has_subscribers() and self.sim.signal(self.tx_changed, self.tx_changed)
            self.tx_ops.has_subscribers() and self._fire_ops(
                'put', requested=requested, moved=requested, success=True, blocked=False,
                wait_time=0.0, api='gput', items_in=list(obj),
            )
            return True
        with self.sim.consume(self.tx_nfull, **policy_params):
            retval = yield from self.sim.gwait(
                timeout,
                cond=lambda e: len(self._buffer) + len(obj) <= self.capacity,
            )
        waited = float(self.sim.time) - t_start
        if retval is not None:
            for item in obj:
                self._buffer.enqueue(item)
            self.tx_nempty.has_subscribers() and self.sim.signal(self.tx_nempty, self.tx_nempty)
            self.tx_changed.has_subscribers() and self.sim.signal(self.tx_changed, self.tx_changed)
            self.tx_ops.has_subscribers() and self._fire_ops(
                'put', requested=requested, moved=requested, success=True, blocked=True,
                wait_time=waited, api='gput', items_in=list(obj),
            )
        else:
            self.tx_ops.has_subscribers() and self._fire_ops(
                'put', requested=requested, moved=0, success=False, blocked=True, timeout=True,
                wait_time=waited, api='gput',
            )
        return retval

    # ---- get side ----------------------------------------------------------

    def get_n_nowait(self, amount: int = 1, cond: CondType = AlwaysTrue) -> Optional[List[EventType]]:
        '''Get item(s) from buffer immediately.

        Returns a list of *amount* items when available and *cond* passes for
        the head item, or None otherwise.
        '''
        if len(self._buffer) >= amount and cond(self._buffer.peek()):
            retval = [self._buffer.dequeue() for _ in range(amount)]
            self.tx_nfull.has_subscribers() and self.sim.signal(self.tx_nfull, self.tx_nfull)
            self.tx_changed.has_subscribers() and self.sim.signal(self.tx_changed, self.tx_changed)
            self.tx_ops.has_subscribers() and self._fire_ops(
                'get', requested=amount, moved=len(retval), success=True,
                api='get_n_nowait', items_out=retval,
            )
            return retval
        self.tx_ops.has_subscribers() and self._fire_ops('get', requested=amount, moved=0, success=False, api='get_n_nowait')
        return None

    def get_nowait(self, cond: CondType = AlwaysTrue) -> Optional[List[EventType]]:
        '''A version of get_n_nowait which does not return a list, but rather one element.'''
        if len(self._buffer) >= 1 and cond(self._buffer.peek()):
            retval = self._buffer.dequeue()
            self.tx_nfull.has_subscribers() and self.sim.signal(self.tx_nfull, self.tx_nfull)
            self.tx_changed.has_subscribers() and self.sim.signal(self.tx_changed, self.tx_changed)
            self.tx_ops.has_subscribers() and self._fire_ops(
                'get', requested=1, moved=1, success=True,
                api='get_nowait', items_out=[retval],
            )
            return retval
        self.tx_ops.has_subscribers() and self._fire_ops('get', requested=1, moved=0, success=False, api='get_nowait')
        return None

    async def get_n(self, timeout: TimeType = float('inf'), amount: int =1, cond: CondType = AlwaysTrue, **policy_params: Any) -> Optional[List[EventType]]:
        '''Get item(s) from buffer, waiting up to *timeout* if not available.'''
        tx = self._get_tx_endpoint(cond)
        t_start = float(self.sim.time)
        if cond is AlwaysTrue:
            check = lambda _: len(self._buffer) >= amount
        else:
            check = lambda _: len(self._buffer) >= amount and cond(self._buffer.peek())
        if check(None):
            retval = [self._buffer.dequeue() for _ in range(amount)]
            self.tx_nfull.has_subscribers() and self.sim.signal(self.tx_nfull, self.tx_nfull)
            self.tx_changed.has_subscribers() and self.sim.signal(self.tx_changed, self.tx_changed)
            self.tx_ops.has_subscribers() and self._fire_ops(
                'get', requested=amount, moved=len(retval), success=True, blocked=False,
                wait_time=0.0, api='get_n', items_out=retval,
            )
            return retval
        with self.sim.consume(tx, **policy_params):
            element = await self.sim.wait(timeout, cond=check)
        waited = float(self.sim.time) - t_start
        if element is None:
            self.tx_ops.has_subscribers() and self._fire_ops(
                'get', requested=amount, moved=0, success=False, blocked=True, timeout=True,
                wait_time=waited, api='get_n',
            )
            return None
        retval = [self._buffer.dequeue() for _ in range(amount)]
        self.tx_nfull.has_subscribers() and self.sim.signal(self.tx_nfull, self.tx_nfull)
        self.tx_changed.has_subscribers() and self.sim.signal(self.tx_changed, self.tx_changed)
        self.tx_ops.has_subscribers() and self._fire_ops(
            'get', requested=amount, moved=len(retval), success=True, blocked=True,
            wait_time=waited, api='get_n', items_out=retval,
        )
        return retval

    async def get(self, timeout: TimeType = float('inf'), cond: CondType = AlwaysTrue, **policy_params: Any) -> Optional[List[EventType]]:
        '''A version of get_n which does not return a list, but rather one element.'''
        tx = self._get_tx_endpoint(cond)
        t_start = float(self.sim.time)
        if cond is AlwaysTrue:
            check = self.LAMBDA1
        else:
            check = lambda _: len(self._buffer) >= 1 and cond(self._buffer.peek())
        if check(None):
            retval = self._buffer.dequeue()
            self.tx_nfull.has_subscribers() and self.sim.signal(self.tx_nfull, self.tx_nfull)
            self.tx_changed.has_subscribers() and self.sim.signal(self.tx_changed, self.tx_changed)
            self.tx_ops.has_subscribers() and self._fire_ops(
                'get', requested=1, moved=1, success=True, blocked=False,
                wait_time=0.0, api='get', items_out=[retval],
            )
            return retval
        with self.sim.consume(tx, **policy_params):
            element = await self.sim.wait(timeout, cond=check)
        waited = float(self.sim.time) - t_start
        if element is None:
            self.tx_ops.has_subscribers() and self._fire_ops(
                'get', requested=1, moved=0, success=False, blocked=True, timeout=True,
                wait_time=waited, api='get',
            )
            return None
        retval = self._buffer.dequeue()
        self.tx_nfull.has_subscribers() and self.sim.signal(self.tx_nfull, self.tx_nfull)
        self.tx_changed.has_subscribers() and self.sim.signal(self.tx_changed, self.tx_changed)
        self.tx_ops.has_subscribers() and self._fire_ops(
            'get', requested=1, moved=1, success=True, blocked=True,
            wait_time=waited, api='get', items_out=[retval],
        )
        return retval

    def gget_n(self, timeout: TimeType = float('inf'), amount: int = 1, cond: CondType = AlwaysTrue, **policy_params: Any) -> Generator[EventType, Optional[List[EventType]], Optional[List[EventType]]]:
        '''Get item(s) from buffer (generator version), waiting up to *timeout* if not available.'''
        tx = self._get_tx_endpoint(cond)
        t_start = float(self.sim.time)
        if cond is AlwaysTrue:
            check = lambda _: len(self._buffer) >= amount
        else:
            check = lambda _: len(self._buffer) >= amount and cond(self._buffer.peek())
        if check(None):
            retval = [self._buffer.dequeue() for _ in range(amount)]
            self.tx_nfull.has_subscribers() and self.sim.signal(self.tx_nfull, self.tx_nfull)
            self.tx_changed.has_subscribers() and self.sim.signal(self.tx_changed, self.tx_changed)
            self.tx_ops.has_subscribers() and self._fire_ops(
                'get', requested=amount, moved=len(retval), success=True, blocked=False,
                wait_time=0.0, api='gget_n', items_out=retval,
            )
            return retval
        with self.sim.consume(tx, **policy_params):
            element = yield from self.sim.gwait(timeout, cond=check)
        waited = float(self.sim.time) - t_start
        if element is None:
            self.tx_ops.has_subscribers() and self._fire_ops(
                'get', requested=amount, moved=0, success=False, blocked=True, timeout=True,
                wait_time=waited, api='gget_n',
            )
            return None
        retval = [self._buffer.dequeue() for _ in range(amount)]
        self.tx_nfull.has_subscribers() and self.sim.signal(self.tx_nfull, self.tx_nfull)
        self.tx_changed.has_subscribers() and self.sim.signal(self.tx_changed, self.tx_changed)
        self.tx_ops.has_subscribers() and self._fire_ops(
            'get', requested=amount, moved=len(retval), success=True, blocked=True,
            wait_time=waited, api='gget_n', items_out=retval,
        )
        return retval

    def gget(self, timeout: TimeType = float('inf'), cond: CondType = AlwaysTrue, **policy_params: Any) -> Generator[EventType, Optional[EventType], Optional[EventType]]:
        '''A version of gget_n which does not return a list, but rather one element.'''
        tx = self._get_tx_endpoint(cond)
        t_start = float(self.sim.time)
        if cond is AlwaysTrue:
            check = self.LAMBDA1
        else:
            check = lambda _: len(self._buffer) >= 1 and cond(self._buffer.peek())
        if check(None):
            retval = self._buffer.dequeue()
            self.tx_nfull.has_subscribers() and self.sim.signal(self.tx_nfull, self.tx_nfull)
            self.tx_changed.has_subscribers() and self.sim.signal(self.tx_changed, self.tx_changed)
            self.tx_ops.has_subscribers() and self._fire_ops(
                'get', requested=1, moved=1, success=True, blocked=False,
                wait_time=0.0, api='gget', items_out=[retval],
            )
            return retval
        with self.sim.consume(tx, **policy_params):
            element = yield from self.sim.gwait(timeout, cond=check)
        waited = float(self.sim.time) - t_start
        if element is None:
            self.tx_ops.has_subscribers() and self._fire_ops(
                'get', requested=1, moved=0, success=False, blocked=True, timeout=True,
                wait_time=waited, api='gget',
            )
            return None
        retval = self._buffer.dequeue()
        self.tx_nfull.has_subscribers() and self.sim.signal(self.tx_nfull, self.tx_nfull)
        self.tx_changed.has_subscribers() and self.sim.signal(self.tx_changed, self.tx_changed)
        self.tx_ops.has_subscribers() and self._fire_ops(
            'get', requested=1, moved=1, success=True, blocked=True,
            wait_time=waited, api='gget', items_out=[retval],
        )
        return retval

    # ---- direct buffer manipulation ----------------------------------------

    def pop(self, index: int = 0, default: Optional[EventType] = None) -> Optional[EventType]:
        '''Remove and return item at *index* (default: head). Returns *default* if out of range.'''
        if len(self._buffer) > index:
            try:
                retval = self._buffer.pop_at(index)
                self.tx_nfull.has_subscribers() and self.sim.signal(self.tx_nfull, self.tx_nfull)
                self.tx_changed.has_subscribers() and self.sim.signal(self.tx_changed, self.tx_changed)
                self.tx_ops.has_subscribers() and self._fire_ops('pop', requested=1, moved=1, success=True, api='pop', items_out=[retval])
            except IndexError:
                retval = default
                self.tx_ops.has_subscribers() and self._fire_ops('pop', requested=1, moved=0, success=False, api='pop')
        else:
            retval = default
            self.tx_ops.has_subscribers() and self._fire_ops('pop', requested=1, moved=0, success=False, api='pop')
        return retval

    def remove(self, cond: CondType) -> None:
        '''Remove item(s) from buffer matching *cond*.

        *cond* may be a callable predicate or an exact item to match (== equality).
        '''
        removed_items: list[EventType] = []
        if len(self._buffer) > 0:
            if callable(cond):
                removed_items = [e for e in self._buffer if cond(e)]
            else:
                removed_items = [e for e in self._buffer if cond == e]
            if removed_items:
                for item in removed_items:
                    try:
                        self._buffer.remove(item)
                    except ValueError:
                        pass
                self.tx_nfull.has_subscribers() and self.sim.signal(self.tx_nfull, self.tx_nfull)
                self.tx_changed.has_subscribers() and self.sim.signal(self.tx_changed, self.tx_changed)
        removed = len(removed_items)
        self.tx_ops.has_subscribers() and self._fire_ops(
            'remove', requested=1, moved=removed, success=(removed > 0),
            api='remove', items_out=removed_items,
        )

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
        if cond(None):
            return None
        with self.sim.consume(tx, **policy_params):
            retval = yield from self.sim.gwait(timeout, cond=cond)
        return retval

    async def check_and_wait(self, timeout: TimeType = float('inf'), cond: CondType = AlwaysTrue, **policy_params: Any) -> EventType:
        tx = self._get_tx_endpoint(cond)
        if cond(None):
            return None
        with self.sim.consume(tx, **policy_params):
            retval = await self.sim.wait(timeout, cond=cond)
        return retval

    # ---- sequence protocol -------------------------------------------------

    def __len__(self) -> int:
        return len(self._buffer)

    def __getitem__(self, index: int) -> EventType:
        return self._buffer[index]

    def __setitem__(self, index: int, data: EventType) -> None:
        old_item = self._buffer[index]
        self._buffer[index] = data
        self.tx_nempty.has_subscribers() and self.sim.signal(self.tx_nempty, self.tx_nempty)
        self.tx_changed.has_subscribers() and self.sim.signal(self.tx_changed, self.tx_changed)
        self.tx_ops.has_subscribers() and self._fire_ops(
            'setitem', requested=1, moved=1, success=True,
            api='setitem', items_in=[data], items_out=[old_item],
        )

    def __iter__(self) -> Iterator[EventType]:
        return iter(self._buffer)

    def __contains__(self, item: Any) -> bool:
        return item in self._buffer


# In the following, self is in fact of type DSAgent, but PyLance makes troubles with variable types
class QueueMixin:
    async def enter(self: Any, queue: DSQueue, timeout: TimeType = float('inf'), **policy_params: Any) -> EventType:
        try:
            retval = await queue.put(timeout, self, **policy_params)
        except DSAbortException as exc:
            self.scheduled_process.abort()
        return retval

    def genter(self: Any, queue: DSQueue, timeout: TimeType = float('inf'), **policy_params) -> Generator[EventType, EventType, EventType]:
        try:
            retval = yield from queue.gput(timeout, self, **policy_params)
        except DSAbortException as exc:
            self.scheduled_process.abort()
        return retval

    def enter_nowait(self: Any, queue: DSQueue) -> Optional[EventType]:
        retval = queue.put_nowait(self)
        return retval

    def leave(self: Any, queue: DSQueue) -> None:
        queue.remove(self)

    async def pop(self: Any, queue: DSQueue, timeout: TimeType = float('inf'), **policy_params: Any) -> Optional[EventType]:
        try:
            retval = await queue.get(timeout, **policy_params)
        except DSAbortException as exc:
            self.scheduled_process.abort()
        return retval

    def gpop(self: Any, queue: DSQueue, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, EventType, EventType]:
        try:
            retval = yield from queue.gget(timeout, **policy_params)
        except DSAbortException as exc:
            self.scheduled_process.abort()
        return retval

    def pop_nowait(self: Any, queue: DSQueue) -> EventType:
        return queue.get_nowait()


# In the following, self is in fact of type DSSimulation, but PyLance makes troubles with variable types
class SimQueueMixin:
    def queue(self: Any, *args: Any, **kwargs: Any) -> DSQueue:
        sim: 'DSSimulation' = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in queue() method should be set to the same simulation instance.')
        return DSQueue(*args, **kwargs, sim=sim)
