# Copyright 2022- majvan (majvan@gmail.com)
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
The file provides process-centric API to easy the design of process-oriented
application.
'''
from abc import abstractmethod
from typing import Any, Optional, Generator, Type, Callable
import inspect
from dssim.base import EventType, TimeType, DSComponent, NumericType
from dssim.pubsub.base import CondType, DSAbortException, AlwaysTrue
from dssim.pubsub.process import DSProcess
from dssim.simulation import DSSchedulable
from dssim.pubsub.components.container import DSContainer
from dssim.pubsub.components.resource import DSResource


class AgentContainerMixin:
    async def enter(self: Any, container: DSContainer, timeout: TimeType = float('inf'), **policy_params: Any) -> EventType:
        try:
            retval = await container.put(timeout, self, **policy_params)
        except DSAbortException:
            self._scheduled_process.abort()
            raise
        return retval

    def genter(self: Any, container: DSContainer, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, EventType, EventType]:
        try:
            retval = yield from container.gput(timeout, self, **policy_params)
        except DSAbortException:
            self._scheduled_process.abort()
            raise
        return retval

    def enter_nowait(self: Any, container: DSContainer) -> Optional[EventType]:
        return container.put_nowait(self)

    def leave(self: Any, container: DSContainer) -> None:
        container.remove(self)

    async def pop(self: Any, container: DSContainer, timeout: TimeType = float('inf'), **policy_params: Any) -> Optional[EventType]:
        try:
            retval = await container.get(timeout, **policy_params)
        except DSAbortException:
            self._scheduled_process.abort()
            raise
        return retval

    def gpop(self: Any, container: DSContainer, timeout: TimeType = float('inf'), **policy_params: Any) -> Generator[EventType, EventType, EventType]:
        try:
            retval = yield from container.gget(timeout, **policy_params)
        except DSAbortException:
            self._scheduled_process.abort()
            raise
        return retval

    def pop_nowait(self: Any, container: DSContainer) -> Optional[EventType]:
        return container.get_nowait()


class AgentResourceMixin:
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


class DSAgent(DSComponent, AgentContainerMixin, AgentResourceMixin):
    _dscomponent_instances: int = 0

    def __init__(self, *args: Any, name: Optional[str] = None, **kwargs: Any) -> None:
        if name is None:
            name = type(self).__name__ + '.' + str(self._dscomponent_instances)
        super().__init__(name=name, *args, **kwargs)
        kwargs.pop('name', None), kwargs.pop('sim', None)  # remove the two arguments
        process: DSProcess
        if inspect.isgeneratorfunction(self.process) or inspect.iscoroutinefunction(self.process):
            process = _ComponentProcess(self, self.process(*args, **kwargs), name=self.name+'.process', sim=self.sim)
        elif inspect.ismethod(self.process):
            process = _ComponentProcess(self, DSSchedulable(self.process)(*args, **kwargs), name=self.name+'.process', sim=self.sim)
        else:
            raise ValueError(f'The attribute {self.__class__}.process is not method, generator, neither coroutine.')
        self._scheduled_process: _ComponentProcess = process.schedule(0)
        self._instance_nr = self.__class__._dscomponent_instances + 1
        self.__class__._dscomponent_instances = self.instance_nr

    @property
    def instance_nr(self) -> int: return self._instance_nr
    
    @abstractmethod
    def process(self, *args: Any, **kwargs: Any) -> Any:
        pass

    def signal(self, event: EventType) -> None:
        self._scheduled_process.signal(event)

    def hold(self, timeout: TimeType = float('inf'), val: EventType = True) -> Generator[EventType, EventType, EventType]:
        '''Pause this agent for a duration (maps to gsleep).'''
        try:
            retval = yield from self.sim.gsleep(timeout=timeout, val=val)
        except DSAbortException:
            self._scheduled_process.abort()
            raise
        return retval

    def passivate(self, timeout: TimeType = float('inf'), val: EventType = True) -> Generator[EventType, EventType, EventType]:
        '''Wait until this agent receives any event (or timeout).'''
        try:
            retval = yield from self.sim.gwait(timeout=timeout, cond=AlwaysTrue, val=val)
        except DSAbortException:
            self._scheduled_process.abort()
            raise
        return retval

    def activate(self, event: EventType = True) -> None:
        '''Activate this agent by sending an event to itself.'''
        self.signal(event)

    async def wait(self, timeout: TimeType = float('inf'), cond: CondType = AlwaysTrue) -> EventType:
        try:
            retval = await self.sim.wait(timeout, cond=cond)
        except DSAbortException as exc:
            self._scheduled_process.abort()
        return retval

    def gwait(self, timeout: TimeType = float('inf'), cond: CondType = AlwaysTrue) -> Generator[EventType, EventType, EventType]:
        try:
            retval = yield from self.sim.gwait(timeout, cond=cond)
        except DSAbortException as exc:
            self._scheduled_process.abort()
        return retval


class _ComponentProcess(DSProcess):
    def __init__(self, process_component: DSAgent, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._component = process_component

    @property
    def component(self) -> DSAgent:
        return self._component


class PCGenerator(DSAgent):
    def __init__(self, cls: Type[DSComponent], wait_method: Callable[[DSComponent], float] = lambda last: 1, *args: Any, name: Optional[str] = None, **kwargs: Any) -> None:
        self.cls = cls
        self.wait_method = wait_method
        if name is None:
            name = f'PCGenerator({cls.__name__ }).' + str(self._dscomponent_instances)
        super().__init__(*args, name=name, **kwargs)

    async def process(self) -> None:
        while True:
            obj = self.cls()  # create new instance of the class
            await self.sim.sleep(self.wait_method(obj))


# Backward-compatibility alias; DSAgent is the preferred name.
DSProcessComponent = DSAgent
      
