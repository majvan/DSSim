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
from dssim.base import EventType, TimeType, DSComponent, DSAbortException
from dssim.process import DSProcess
from dssim.process import DSSchedulable
from dssim.components.queue import QueueMixin
from dssim.components.resource import ResourceMixin


class DSProcessComponent(DSComponent, QueueMixin, ResourceMixin):
    _dscomponent_instances: int = 0

    def __init__(self, *args: Any, name: Optional[str] = None, **kwargs: Any) -> None:
        if name is None:
            name = type(self).__name__ + '.' + str(self._dscomponent_instances)
        super().__init__(name=name, *args, **kwargs)
        kwargs.pop('name', None), kwargs.pop('sim', None)  # remove the two arguments
        process: DSProcess
        if inspect.isgeneratorfunction(self.process) or inspect.iscoroutinefunction(self.process):
            process = DSProcess(self.process(*args, **kwargs), name=self.name+'.process', sim=self.sim)
        elif inspect.ismethod(self.process):
            process = DSProcess(DSSchedulable(self.process)(*args, **kwargs), name=self.name+'.process', sim=self.sim)
        else:
            raise ValueError(f'The attribute {self.__class__}.process is not method, generator, neither coroutine.')
        self.scheduled_process: DSProcess = process.schedule(0)
        self.__class__._dscomponent_instances += 1
    
    @abstractmethod
    def process(self, *args: Any, **kwargs: Any) -> Any:
        pass

    def signal(self, event: EventType) -> None:
        self.scheduled_process.signal({'object': event})

    async def wait(self, timeout: TimeType = float('inf')) -> EventType:
        try:
            retval = await self.sim.wait(timeout, cond=lambda e: True)
        except DSAbortException as exc:
            self.scheduled_process.abort()
        return retval

    def gwait(self, timeout: TimeType = float('inf')) -> Generator[EventType, EventType, EventType]:
        try:
            retval = yield from self.sim.gwait(timeout, cond=lambda e: True)
        except DSAbortException as exc:
            self.scheduled_process.abort()
        return retval


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
      
