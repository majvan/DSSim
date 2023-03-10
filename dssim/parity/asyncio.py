# Copyright 2020- majvan (majvan@gmail.com)
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
import inspect
from dssim.simulation import DSSimulation, DSAbsTime, DSProcess, DSCallback
from dssim.cond import DSFilterAggregated, DSFilter

class EventLoopAsyncioMixin:
    ''' Following is a mixin for asyncio event loop'''
    def run_forever(self):
        retval = self.run()
        return retval

    def run_until_complete(self, future):
        if inspect.iscoroutine(future):
            future = DSAsyncProcess(future, sim=self)  # create a DSProcess, Task
            future.schedule(0)
        # The loop is required because we wait for event 'process' which is produced by the process finish().
        # However, other components may use the process as an event for inter-process communication
        while not future.finished():
            retval = self.run(future=future)
        return future.result()

    def stop(self):
        return

    def is_running(self):
        return False
    
    def is_closed(self):
        return False
    
    def close(self):
        return False
    
    def call_later(self, delay, callback, *args, context=None):
        cb = DSSchedulable(DSCallback(callback(*args)))
        self.schedule(delay, cb)
    
    def call_at(self, time, callback, *args, context=None):
        cb = DSSchedulable(DSCallback(callback(*args)))
        self.schedule(DSAbsTime(time), cb)

class DSAsyncSimulation(DSSimulation, EventLoopAsyncioMixin):
    pass


class TaskAsyncioMixin:
    ''' Following is a mixin for asyncio task'''
    def result(self):
        return self.value

class DSAsyncProcess(DSProcess, TaskAsyncioMixin):
    pass


def set_current_loop(simulation):
    DSAsyncSimulation.sim_singleton = simulation

def get_current_loop():
    if DSSimulation.sim_singleton is None:
        set_current_loop(DSAsyncSimulation())
    return DSSimulation.sim_singleton

async def gather(*coros_or_futures, return_exceptions=False):
    loop = get_current_loop()
    filters = [DSFilter(c, sim=loop) for c in coros_or_futures]
    f = DSFilterAggregated(all, filters)
    retval = await loop.wait(cond=f)
    return list(retval.values())

async def sleep(time):
    loop = get_current_loop()
    retval = await loop.wait(time)
    return retval

def run(coro_or_future):
    loop = get_current_loop()
    retval = loop.run_until_complete(coro_or_future)
    return retval

def create_task(coro):
    loop = get_current_loop()
    return DSAsyncProcess(coro, sim=loop)
