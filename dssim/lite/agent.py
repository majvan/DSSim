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
Lite process-centric API for LiteLayer2 simulations.

DSLiteAgent mirrors DSAgent lifecycle (component + scheduled process) but uses
LiteLayer2-compatible wait and helper methods.
'''
from __future__ import annotations

from abc import abstractmethod
from typing import Any, Optional, Generator, Type, Callable
import inspect
from functools import wraps

from dssim.base import DSComponent, EventType, EventRetType, TimeType, NumericType
from dssim.pubsub.base import DSAbortException, AlwaysTrue
from dssim.pubsub.process import DSProcess
from dssim.lite.components.litequeue import LiteQueue
from dssim.lite.components.literesource import LiteResource, LitePriorityResource


def _as_schedulable(api_func: Callable[..., Any]) -> Callable[..., Generator[Any, Any, Any]]:
    '''Local lightweight equivalent of DSSchedulable without importing simulation.'''
    def _fcn_in_generator(*args: Any, **kwargs: Any) -> Generator[Any, Any, Any]:
        if False:
            yield None
        return api_func(*args, **kwargs)

    @wraps(api_func)
    def scheduled_func(*args: Any, **kwargs: Any) -> Generator[Any, Any, Any]:
        if inspect.isgeneratorfunction(api_func) or inspect.iscoroutinefunction(api_func):
            return api_func(*args, **kwargs)
        return _fcn_in_generator(*args, **kwargs)

    return scheduled_func


class _LiteQueueMixin:
    '''Queue helper methods for DSLiteAgent.

    LiteQueue provides generator + nowait APIs only, so async enter/pop are not
    exposed here.
    '''

    def enter_nowait(self: Any, queue: LiteQueue, item: Any = None) -> Optional[Any]:
        item = self if item is None else item
        return queue.put_nowait(item)

    def genter(self: Any, queue: LiteQueue, item: Any = None) -> Generator[EventType, EventType, Any]:
        item = self if item is None else item
        try:
            retval = yield from queue.gput(item)
        except DSAbortException:
            self._scheduled_process.abort()
            raise
        return retval

    def pop_nowait(self: Any, queue: LiteQueue) -> Optional[Any]:
        return queue.get_nowait()

    def gpop(self: Any, queue: LiteQueue) -> Generator[EventType, EventType, Any]:
        try:
            retval = yield from queue.gget()
        except DSAbortException:
            self._scheduled_process.abort()
            raise
        return retval


class _LiteResourceMixin:
    '''Resource helper methods for DSLiteAgent.'''

    async def get(self: Any, resource: LiteResource, timeout: TimeType = float('inf'), **policy_params: Any) -> NumericType:
        return await resource.get(timeout=timeout, **policy_params)

    def gget(self: Any, resource: LiteResource, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, EventType, NumericType]:
        return (yield from resource.gget(timeout=timeout, **policy_params))

    async def get_n(self: Any, resource: LiteResource, amount: NumericType = 1, timeout: TimeType = float('inf'), **policy_params: Any) -> NumericType:
        return await resource.get_n(timeout=timeout, amount=amount, **policy_params)

    def gget_n(self: Any, resource: LiteResource, amount: NumericType = 1, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, EventType, NumericType]:
        return (yield from resource.gget_n(timeout=timeout, amount=amount, **policy_params))

    async def put(self: Any, resource: LiteResource, timeout: TimeType = float('inf')) -> NumericType:
        return await resource.put(timeout=timeout)

    def gput(self: Any, resource: LiteResource, timeout: TimeType = float('inf')) -> Generator[EventType, EventType, NumericType]:
        return (yield from resource.gput(timeout=timeout))

    async def put_n(self: Any, resource: LiteResource, amount: NumericType = 1, timeout: TimeType = float('inf'), **policy_params: Any) -> NumericType:
        return await resource.put_n(timeout=timeout, amount=amount, **policy_params)

    def gput_n(self: Any, resource: LiteResource, amount: NumericType = 1, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, EventType, NumericType]:
        return (yield from resource.gput_n(timeout=timeout, amount=amount, **policy_params))

    def put_nowait(self: Any, resource: LiteResource) -> NumericType:
        return resource.put_nowait()

    def put_n_nowait(self: Any, resource: LiteResource, amount: NumericType = 1) -> NumericType:
        return resource.put_n_nowait(amount)

    def get_nowait(self: Any, resource: LiteResource, **policy_params: Any) -> NumericType:
        return resource.get_nowait(**policy_params)

    def get_n_nowait(self: Any, resource: LiteResource, amount: NumericType = 1, **policy_params: Any) -> NumericType:
        return resource.get_n_nowait(amount, **policy_params)


class DSLiteAgent(DSComponent, _LiteQueueMixin, _LiteResourceMixin):
    _dsliteagent_instances: int = 0

    def __init__(self, *args: Any, name: Optional[str] = None, **kwargs: Any) -> None:
        if name is None:
            name = type(self).__name__ + '.' + str(self._dsliteagent_instances)
        super().__init__(name=name, *args, **kwargs)
        kwargs.pop('name', None), kwargs.pop('sim', None)
        process: DSProcess
        if inspect.isgeneratorfunction(self.process) or inspect.iscoroutinefunction(self.process):
            process = _LiteComponentProcess(self, self.process(*args, **kwargs), name=self.name + '.process', sim=self.sim)
        elif inspect.ismethod(self.process):
            process = _LiteComponentProcess(self, _as_schedulable(self.process)(*args, **kwargs), name=self.name + '.process', sim=self.sim)
        else:
            raise ValueError(f'The attribute {self.__class__}.process is not method, generator, neither coroutine.')
        self._scheduled_process: _LiteComponentProcess = process.schedule(0)
        # LiteLayer2 does not inject process-level conditions (SimProcessMixin
        # is not loaded), so keep one always-true condition on the process to
        # allow direct event delivery from Lite components.
        self._scheduled_process.get_cond().push(AlwaysTrue)
        self._instance_nr = self.__class__._dsliteagent_instances + 1
        self.__class__._dsliteagent_instances = self.instance_nr

    @property
    def instance_nr(self) -> int:
        return self._instance_nr

    @property
    def scheduled_process(self) -> DSProcess:
        return self._scheduled_process

    @abstractmethod
    def process(self, *args: Any, **kwargs: Any) -> Any:
        pass

    def signal(self, event: EventType) -> None:
        self._scheduled_process.signal(event)

    async def wait(self, timeout: TimeType = float('inf')) -> EventRetType:
        try:
            return await self.sim.wait(timeout)
        except DSAbortException:
            self._scheduled_process.abort()
            raise

    def gwait(self, timeout: TimeType = float('inf')) -> Generator[EventType, EventType, EventRetType]:
        try:
            retval = yield from self.sim.gwait(timeout)
        except DSAbortException:
            self._scheduled_process.abort()
            raise
        return retval


class _LiteComponentProcess(DSProcess):
    def __init__(self, process_component: DSLiteAgent, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._component = process_component

    @property
    def component(self) -> DSLiteAgent:
        return self._component


class PCLiteGenerator(DSLiteAgent):
    def __init__(self, cls: Type[DSComponent], wait_method: Callable[[DSComponent], float] = lambda last: 1, *args: Any, name: Optional[str] = None, **kwargs: Any) -> None:
        self.cls = cls
        self.wait_method = wait_method
        if name is None:
            name = f'PCLiteGenerator({cls.__name__ }).' + str(self._dsliteagent_instances)
        super().__init__(*args, name=name, **kwargs)

    async def process(self) -> None:
        while True:
            obj = self.cls()
            await self.sim.sleep(self.wait_method(obj))
