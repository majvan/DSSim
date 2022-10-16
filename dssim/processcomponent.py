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
        if not inspect.isgeneratorfunction(self.process):
            process = DSProcess(DSSchedulable(self.process)(*args, **kwargs), name=self.name+'.process', sim=self.sim)
        else:
            process = DSProcess(self.process(*args, **kwargs), name=self.name+'.process', sim=self.sim)
        retval = process.schedule(0)
        self.scheduled_process = retval
        self.__class__._dscomponent_instances += 1

    def signal(self, event_object):
        self.scheduled_process.signal(object=event_object)
        #self.sim.schedule_event(0, {'object': event_object}, self.scheduled_process)

    def wait(self, timeout=float('inf')):
        try:
            retval = yield from self.sim.wait(timeout, cond=lambda e: True)
            if retval is not None:
                retval = retval['object']
        except DSAbortException as exc:
            self.scheduled_process.abort()
        return retval

    def enter(self, queue, timeout=float('inf')):
        try:
            retval = yield from queue.put(timeout, object=self)
            if retval is not None:
                retval = retval['object']
        except DSAbortException as exc:
            self.scheduled_process.abort()
        return retval

    def enter_nowait(self, queue):
        retval = queue.put_nowait({'object': self})
        return retval

    def leave(self, queue,timeout=float('inf')):
        queue.remove({'object': self})

    def pop(self, queue, timeout=float('inf')):
        try:
            retval = yield from queue.get(timeout)
            assert len(retval) == 1
            if retval is not None:
                retval = retval[0]['object']
        except DSAbortException as exc:
            self.scheduled_process.abort()
        return retval

    def pop_nowait(self, queue):
        retval = queue.get_nowait()
        if retval is not None:
            retval = retval[0]['object']
        return retval

    def get(self, resource, amount=1, timeout=float('inf')):
        retval = yield from resource.get(timeout, amount)
        return retval
            
    def put(self, resource, *amount, timeout=float('inf')):
        retval = yield from resource.put(timeout, *amount)
        return retval
