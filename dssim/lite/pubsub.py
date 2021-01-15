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
Minimal pubsub primitives for LiteLayer2.
'''
from __future__ import annotations

from typing import Any, Callable, List, TYPE_CHECKING

from dssim.base import DSComponent, EventRetType, EventType, ISubscriber

if TYPE_CHECKING:
    from dssim.simulation import DSSimulation


class DSLiteSub(DSComponent, ISubscriber):
    '''Base subscriber for LiteLayer2 pubsub primitives.'''

    supports_direct_send: bool = True

    def send(self, event: EventType) -> EventRetType:
        raise NotImplementedError('DSLiteSub is a base class; use DSLiteCallback or a subclass.')


class DSLiteCallback(DSLiteSub):
    '''Minimal callback subscriber for LiteLayer2.'''

    def __init__(self, forward_method: Callable[[EventType], EventRetType], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.forward_method = forward_method

    def send(self, event: EventType) -> EventRetType:
        return self.forward_method(event)


class DSLitePub(DSComponent, ISubscriber):
    '''Minimal fan-out publisher endpoint for LiteLayer2.'''

    supports_direct_send: bool = True

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._subs: List[ISubscriber] = []

    def add_subscriber(self, subscriber: ISubscriber) -> None:
        self._subs.append(subscriber)

    def remove_subscriber(self, subscriber: ISubscriber) -> None:
        try:
            self._subs.remove(subscriber)
        except ValueError:
            return

    def has_subscribers(self) -> bool:
        return len(self._subs) > 0

    def send(self, event: EventType) -> None:
        if not self.has_subscribers():
            return
        # Snapshot keeps iteration stable if subscribers mutate the list.
        for sub in list(self._subs):
            if getattr(sub, 'supports_direct_send', False):
                sub.send(event)
            else:
                self.sim.send_object(sub, event)


class SimLitePubsubMixin:
    '''Factory mixin for LiteLayer2 pubsub primitives.'''

    def publisher(self: Any, *args: Any, **kwargs: Any) -> DSLitePub:
        sim: 'DSSimulation' = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in publisher() method should be set to the same simulation instance.')
        return DSLitePub(*args, **kwargs, sim=sim)

    def callback(self: Any, *args: Any, **kwargs: Any) -> DSLiteCallback:
        sim: 'DSSimulation' = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in callback() method should be set to the same simulation instance.')
        return DSLiteCallback(*args, **kwargs, sim=sim)
