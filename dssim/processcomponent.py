# Copyright 2022 NXP Semiconductors
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
from dssim.simulation import DSSchedulable, DSComponent, DSProcess, DSAbortException
from dssim.components.queue import Queue
from dssim.components.resource import Resource
import inspect

class DSProcessComponent(DSComponent):
    _dscomponent_instances = 0

    def __init__(self, *args, name=None, **kwargs):
        if name is None:
            name = type(self).__name__ + '.' + str(self._dscomponent_instances)
        super().__init__(self, name=name, *args, **kwargs)
        kwargs.pop('name', None), kwargs.pop('sim', None)  # remove the two arguments
        if inspect.isfunction(self.process):
            process = DSProcess(DSSchedulable(self.process)(*args, **kwargs), name=self.name+'.process', sim=self.sim)
        elif inspect.isgeneratorfunction(self.process) or inspect.iscoroutinefunction(self.process):
            process = DSProcess(self.process(*args, **kwargs), name=self.name+'.process', sim=self.sim)
        else:
            raise ValueError(f'The attribute {self.__class__}.process is is not method, generator, neither coroutine.')
        retval = process.schedule(0)
        self.scheduled_process = retval
        self.__class__._dscomponent_instances += 1

    def signal(self, event):
        self.scheduled_process.signal({'object': event})
        #self.sim.schedule_event(0, {'object': event}, self.scheduled_process)

    async def wait(self, timeout=float('inf')):
        try:
            retval = await self.sim.wait(timeout, cond=lambda e: True)
            if retval is not None:
                retval = retval['object']
        except DSAbortException as exc:
            self.scheduled_process.abort()
        return retval

    async def enter(self, queue, timeout=float('inf')):
        try:
            retval = await queue.put(timeout, self)
            if retval is not None:
                retval = retval['object']
        except DSAbortException as exc:
            self.scheduled_process.abort()
        return retval

    def enter_nowait(self, queue):
        retval = queue.put_nowait(self)
        return retval

    def leave(self, queue,timeout=float('inf')):
        queue.remove(self)

    async def pop(self, queue, timeout=float('inf')):
        try:
            retval = await queue.get(timeout)
            assert len(retval) == 1
            if retval is not None:
                retval = retval[0]
        except DSAbortException as exc:
            self.scheduled_process.abort()
        return retval

    def pop_nowait(self, queue):
        retval = queue.get_nowait()
        if retval is not None:
            retval = retval[0]['object']
        return retval

    async def get(self, resource, amount=1, timeout=float('inf')):
        retval = await resource.get(timeout, amount)
        return retval
            
    async def put(self, resource, *amount, timeout=float('inf')):
        retval = await resource.put(timeout, *amount)
        return retval

    def gget(self, resource, amount=1, timeout=float('inf')):
        retval = yield from resource.get(timeout, amount)
        return retval
            
    def gput(self, resource, *amount, timeout=float('inf')):
        retval = yield from resource.gput(timeout, *amount)
        return retval
