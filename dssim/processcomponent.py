# Copyright 2022 NXP Semiconductors
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
from dssim.base import CondType, EventType, TimeType, DSAbortException, DSComponent
from dssim.pubsub import DSProducer
from dssim.process import DSProcess, DSSchedulable
from dssim.components.base import DSWaitableComponent, MethBind
from dssim.components.container import ContainerMixin
from dssim.components.resource import ResourceMixin


class DSProcessComponent(DSWaitableComponent, ContainerMixin, ResourceMixin):
    _dscomponent_instances: int = 0

    def __init__(self, *args: Any, name: Optional[str] = None, **kwargs: Any) -> None:
        if name is None:
            name = type(self).__name__ + '.' + str(self._dscomponent_instances)
        super().__init__(name=name, *args, **kwargs)
        kwargs.pop('name', None), kwargs.pop('sim', None)  # remove the two arguments
        process: DSProcess
        if inspect.isgeneratorfunction(self.process) or inspect.iscoroutinefunction(self.process):
            process = _ComponentProcess(self, self.process(*args, **kwargs), name=self.name+'.process')
        elif inspect.ismethod(self.process):
            process = _ComponentProcess(self, DSSchedulable(self.process)(*args, **kwargs), name=self.name+'.process')
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

    async def wait(self, timeout: TimeType = float('inf'), cond: CondType = lambda e: True, **policy_params: Any) -> EventType:
        try:
            retval = await self.sim.wait(timeout, cond=cond, **policy_params)
        except DSAbortException as exc:
            self._scheduled_process.abort()
        return retval

    def gwait(self, timeout: TimeType = float('inf'), cond: CondType = lambda e: True, **policy_params: Any) -> Generator[EventType, EventType, EventType]:
        try:
            retval = yield from self.sim.gwait(timeout, cond=cond, **policy_params)
        except DSAbortException as exc:
            self._scheduled_process.abort()
        return retval

    def _set_probed_methods(self):
        if not self._blocking_stat:
            cls = self.__class__
            MethBind.bind(self, 'wait', MethBind.probed(MethBind.method_for(self, cls.wait), self.wait_ep))
            MethBind.bind(self, 'gwait', MethBind.probed(MethBind.method_for(self, cls.gwait), self.wait_ep))
            super()._set_probed_methods()
    
    def _set_unprobed_methods(self):
        if self._blocking_stat:
            cls = self.__class__
            MethBind.bind(self, 'wait', MethBind.method_for(self, cls.wait))
            MethBind.bind(self, 'gwait', MethBind.method_for(self, cls.gwait))
            super()._set_unprobed_methods()


class _ComponentProcess(DSProcess):
    def __init__(self, process_component: DSProcessComponent, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._component = process_component

    @property
    def component(self) -> DSProcessComponent:
        return self._component


class PCGenerator(DSProcessComponent):
    def __init__(self, cls: Type[DSComponent], wait_method: Callable[[DSComponent], float] = lambda last: 1, *args: Any, name: Optional[str] = None, **kwargs: Any) -> None:
        self.cls = cls
        self.wait_method = wait_method
        if name is None:
            name = f'PCGenerator({cls.__name__ }).' + str(self._dscomponent_instances)
        super().__init__(*args, name=name, **kwargs)

    async def process(self) -> None:
        while True:
            obj = self.cls()  # create new instance of the class
            await self.sim.wait(self.wait_method(obj))
      
