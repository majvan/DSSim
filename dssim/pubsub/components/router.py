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
One-of-N routers over channel families (queues or resources), built on the
two-phase (guard + commit) circuit evaluation: every operation commits into
exactly one channel, with blocking back-pressure when none can serve.
'''
from typing import Any, Dict, Generator, Optional, Union

from dssim.base import TimeType, EventType, EventRetType, DSComponent
from dssim.pubsub.base import CondType, AlwaysTrue, ITwoPhaseCondition
from dssim.pubsub.cond import DSFilter, DSCircuit
from dssim.pubsub.components.queue import DSQueue
from dssim.pubsub.components.resource import DSResource


ChannelType = Union[DSQueue, DSResource]

# Placeholder bound into put-router policies before the first load(); never committed.
_ROUTER_UNBOUND = object()


class _DSRouterBase(DSComponent):
    '''Facade over a static one-of-N two-phase circuit of channel policies.

    Builds the OR circuit once at construction; each operation rebinds/waits/
    re-arms it, so callers get a single call per item instead of the
    load-every-branch / wait / reset dance. The circuit stays exposed as
    ``self.circuit`` for composition (e.g. ``router.circuit | escape_filter``),
    though composed trees must then be driven manually again.

    Channels must be homogeneous (all queues, or all plain resources) and must
    provide TWO-PHASE policy conditions - a classical one-pass condition (e.g.
    a priority/preemptive resource) would commit on every evaluated branch,
    which is exactly what routing must never do, so it is rejected here.
    '''

    def __init__(self, *channels: ChannelType, selector: str = 'ordered', **kwargs: Any) -> None:
        if len(channels) == 0:
            raise ValueError('At least one channel is required.')
        kinds = {type(ch) for ch in channels}
        if not (all(isinstance(ch, DSQueue) for ch in channels)
                or all(isinstance(ch, DSResource) for ch in channels)):
            raise ValueError(f'Router channels must be all queues or all resources, got {kinds}.')
        kwargs.setdefault('sim', channels[0].sim)
        super().__init__(**kwargs)
        self.channels = list(channels)
        self._is_resource = isinstance(channels[0], DSResource)
        self.filters = [DSFilter(self._make_policy(ch), sim=self.sim) for ch in self.channels]
        for f, ch in zip(self.filters, self.channels):
            if not isinstance(f.cond, ITwoPhaseCondition):
                raise ValueError(
                    f'{ch} provides a one-pass condition; routing over it would commit '
                    'on every branch. Only two-phase channels can be routed.')
        route: Any = self.filters[0]
        for f in self.filters[1:]:
            route = route | f
        if isinstance(route, DSCircuit):
            route.set_selector(selector)
        self.circuit = route
        self._by_filter = dict(zip(self.filters, self.channels))

    def _make_policy(self, channel: ChannelType) -> Dict[str, Any]:
        raise NotImplementedError

    def _finish(self, payload: EventType) -> tuple[Optional[ChannelType], EventType]:
        '''Re-arm the circuit and resolve (winning channel, committed value).'''
        self.circuit.reset()
        if isinstance(payload, dict):
            if len(payload) == 0:  # circuit timeout returns an empty payload map
                return None, None
            winner = next(iter(payload))
            return self._by_filter.get(winner), payload[winner]
        if payload is None:  # single-channel route timeout
            return None, None
        return self.channels[0], payload


class DSPutRouter(_DSRouterBase):
    '''Static router placing each put into exactly one of N channels.

    With selector 'ordered' (default) the channels form an overflow chain - fill
    the first, spill to the next. With 'round_robin' operations spread fairly,
    skipping full channels. When every channel is full the caller blocks with
    back-pressure until room frees somewhere::

        router = DSPutRouter(q0, q1, q2, selector='round_robin')
        target = await router.put(timeout, item)     # DSQueue or None on timeout

        router = DSPutRouter(pool_a, pool_b)         # resources: amounts, not items
        target = await router.put(timeout, 3)        # deposit 3 units into one pool

    ``router.target`` keeps the last accepting channel.
    '''

    def __init__(self, *channels: ChannelType, selector: str = 'ordered', **kwargs: Any) -> None:
        super().__init__(*channels, selector=selector, **kwargs)
        self.target: Optional[ChannelType] = None

    def _make_policy(self, channel: ChannelType) -> Dict[str, Any]:
        if isinstance(channel, DSResource):
            return channel.policy_for_put(1)
        return channel.policy_for_put(_ROUTER_UNBOUND)

    def _load(self, obj: tuple) -> None:
        if self._is_resource:
            if len(obj) > 1:
                raise ValueError('A resource put takes a single amount.')
            amount = obj[0] if obj else 1
            for f in self.filters:
                f.cond.load(amount)
            return
        if len(obj) == 0:
            raise ValueError('put requires at least one object.')
        for f in self.filters:
            f.cond.load(*obj)

    def gput(self, timeout: TimeType = float('inf'), *obj: EventType) -> Generator[EventType, EventType, Optional[ChannelType]]:
        '''Put item(s) - or, for resources, an amount - into one channel, waiting
        up to *timeout* when all are full. Returns the accepting channel, or None
        on timeout.'''
        self._load(obj)
        payload = yield from self.circuit.check_and_gwait(timeout)
        self.target, _ = self._finish(payload)
        return self.target

    async def put(self, timeout: TimeType = float('inf'), *obj: EventType) -> Optional[ChannelType]:
        '''Async variant of gput.'''
        self._load(obj)
        payload = await self.circuit.check_and_wait(timeout)
        self.target, _ = self._finish(payload)
        return self.target


class DSGetRouter(_DSRouterBase):
    '''Static router taking each get from exactly one of N channels.

    With selector 'ordered' (default) earlier channels have priority; with
    'round_robin' the scan starts after the channel served last. Blocks until
    some channel can serve::

        router = DSGetRouter(q0, q1, q2)
        item = await router.get(timeout)     # queue item, or None on timeout

        router = DSGetRouter(pool_a, pool_b, amount=2)
        got = await router.get(timeout)      # 2 units taken from one pool

    ``router.source`` keeps the channel the last operation was served from.
    '''

    def __init__(self, *channels: ChannelType, amount: Any = 1, cond: CondType = AlwaysTrue,
                 selector: str = 'ordered', **kwargs: Any) -> None:
        self._amount = amount
        self._cond = cond
        if cond is not AlwaysTrue and any(isinstance(ch, DSResource) for ch in channels):
            raise ValueError('cond applies to queue items; resources have no items to test.')
        super().__init__(*channels, selector=selector, **kwargs)
        self.source: Optional[ChannelType] = None

    def _make_policy(self, channel: ChannelType) -> Dict[str, Any]:
        if isinstance(channel, DSResource):
            return channel.policy_for_get(amount=self._amount)
        return channel.policy_for_get(amount=self._amount, cond=self._cond)

    def gget(self, timeout: TimeType = float('inf')) -> Generator[EventType, EventType, EventType]:
        '''Get from the first channel which can serve, waiting up to *timeout*.
        Returns the item(s)/amount, or None on timeout; the channel is kept in
        ``self.source``.'''
        payload = yield from self.circuit.check_and_gwait(timeout)
        self.source, value = self._finish(payload)
        return value

    async def get(self, timeout: TimeType = float('inf')) -> EventType:
        '''Async variant of gget.'''
        payload = await self.circuit.check_and_wait(timeout)
        self.source, value = self._finish(payload)
        return value
