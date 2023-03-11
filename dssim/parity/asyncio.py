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
from dssim.simulation import DSSimulation, DSAbsTime, DSSchedulable, DSProcess, DSCallback, DSAbortException
from dssim.cond import DSFilterAggregated, DSFilter

class CancelledError(DSAbortException):
    pass


class TimeoutError(Exception):
    pass


class DSAsyncSimulation(DSSimulation):
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


class DSAsyncProcess(DSProcess):
    ''' Following is a mixin for asyncio Task'''
    def done(self):
        return self.finished()
    
    def cancelled(self):
        return self.finished() and isinstance(self.exc, CancelledError)

    def result(self):
        return self.value
    
    def exception(self):
        return self.exc

    def set_name(self, value):
        self.name = value

    def get_name(self):
        return self.name
    
    def cancel(self, msg=None):
        self.abort(CancelledError())

    def add_done_callback(self, callback, * , context=None):
        if isinstance(callback, function):
            self.finish_tx.add_subscriber(DSCallback(callback))
        elif isinstance(callback, DSCallback):
            self.finish_tx.add_subscriber(callback)
        else:
            raise ValueError(f'Callback {callback} shall be a DSCallback or a function')

    def remove_done_callback(self, callback):
        if isinstance(callback, function):
            callback = DSCallback(callback)
        self.finish_tx.remove_subscriber(callback)

    def get_coro(self):
        return self.scheduled_generator

    def __await__(self):
        with self.sim.observe_pre(self.finish_tx):
            retval = yield from self.sim.check_and_gwait(cond=lambda e:self.finished())
        if self.exc is not None:
            raise self.exc
        return self.value


class TaskGroup:
    def __init__(self):
        self.tasks = []
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        retval = await gather(*self.tasks)
        return retval
    
    def create_task(self, coro):
        task = create_task(coro)
        self.tasks.append(task)
        return task

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
    return [retval[f] for f in filters]  # values have to be sorted by input order

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
    return DSAsyncProcess(coro, sim=loop).schedule(0)
