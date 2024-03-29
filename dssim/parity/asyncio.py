# Copyright 2023- majvan (majvan@gmail.com)
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
The light asyncio api implementation for dssim.
'''
import inspect
from dssim import DSSimulation, DSAbsTime, DSAbortException
from dssim import DSSchedulable, DSFuture, DSProcess, DSCallback
# other imports
from dssim.process import DSTimeoutContext
from dssim.cond import DSCircuit, DSFilter
from contextlib import asynccontextmanager


class CancelledError(DSAbortException):
    def __init__(self, msg=None):
        super().__init__(None, msg=msg)


class InvalidStateError(Exception):
    pass


class Timeout(DSTimeoutContext):
    def expired(self):
        return self.interrupted()


class DSAsyncSimulation(DSSimulation):
    ''' Following is a mixin for asyncio event loop'''
    def run_forever(self):
        retval = self.run()
        return retval

    def run_until_complete(self, future):
        if inspect.iscoroutine(future):
            future = Task(future, sim=self)  # create a DSProcess, Task
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
        cb = DSSchedulable(DSCallback(callback(*args), sim=self))
        self.schedule(delay, cb)
    
    def call_at(self, time, callback, *args, context=None):
        cb = DSSchedulable(DSCallback(callback(*args), sim=self))
        self.schedule(DSAbsTime(time), cb)

    def create_task(self, coro):
        return Task(coro, sim=self).schedule(0)

    def create_future(self):
        return Future(sim=self)


class FutureAsyncMixin:
    ''' Extends a class with a asyncio's Future interface '''
    def result(self):
        if not self.finished():
            raise InvalidStateError()
        if self.exc is None:
            return self.value
        else:
            raise self.exc

    def done(self):
        return self.finished()

    def cancelled(self):
        return isinstance(self.exc, CancelledError)

    def add_done_callback(self, callback, * , context=None):
        if isinstance(callback, DSCallback):
            self._finish_tx.add_subscriber(callback, phase='pre')
        elif callable(callback):
            self._finish_tx.add_subscriber(DSCallback(callback, sim=self.sim), phase='pre')
        else:
            raise ValueError(f'Callback {callback} shall be a DSCallback or a callable')

    def remove_done_callback(self, callback):
        if isinstance(callback, function):
            callback = DSCallback(callback, sim=self)
        self._finish_tx.remove_subscriber(callback)

    def cancel(self, msg=None):
        if self.finished():
            return False
        self.abort(CancelledError(msg))
        return True
    
    def exception(self):
        if not self.finished():
            raise InvalidStateError()
        elif isinstance(self.exc, CancelledError):
            raise self.exc
        else:
            return self.exc
        
    def get_loop(self):
        return self.sim  


class Future(DSFuture, FutureAsyncMixin):
    def set_result(self, result):
        if self.finished():
            raise InvalidStateError()
        self.finish(result)

    def set_exception(self, exc):
        if self.finished():
            raise InvalidStateError()
        self.fail(exc)

    def __await__(self):
        yield from super().__await__()
        return self.value


class Task(DSProcess, FutureAsyncMixin):
    ''' Following is an implementation of asyncio Task'''

    def get_coro(self):
        return self.scheduled_generator

    def set_name(self, value):
        self.name = value

    def get_name(self):
        return self.name


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

def get_running_loop():
    return DSSimulation.sim_singleton

def get_event_loop():
    return get_current_loop()


async def gather(*coros_or_futures, return_exceptions=False):
    loop = get_running_loop()
    filters = [DSFilter(c, sim=loop) for c in coros_or_futures]
    f = DSCircuit(all, filters, sim=loop)
    retval = await f
    return [retval[f] for f in filters]  # values have to be sorted by input order

async def sleep(delay, result=None):
    loop = get_running_loop()
    retval = await loop.wait(delay)
    return retval

async def wait_for(aw, timeout):
    async with _timeout(timeout) as cm:
        retval = await aw
    if cm.interrupted():
        raise TimeoutError()
    return retval

ALL_COMPLETED = 1
async def wait(aws, *, timeout=None, return_when=ALL_COMPLETED):
    loop = get_running_loop()
    filters = [DSFilter(c, sim=loop) for c in aws if inspect.iscoroutine(c)]
    if return_when == ALL_COMPLETED:
        f = DSCircuit(all, filters)
    else:
        f = DSCircuit(any, filters)
    retval = await f
    return [retval[f] for f in filters]  # values have to be sorted by input order


@asynccontextmanager
async def timeout(delay):
    loop = get_running_loop()
    exc = TimeoutError()
    cm = Timeout(delay, sim=loop, exc=exc)
    try:
        yield cm
    except TimeoutError as e:
        if cm.exc is not e:
            raise
        cm.set_interrupted()
    finally:
        cm.cleanup()
_timeout = timeout

@asynccontextmanager
async def timeout_at(when):
    async with timeout(DSAbsTime(when)) as cm:
        yield cm

def run(coro_or_future):
    loop = get_current_loop()
    retval = loop.run_until_complete(coro_or_future)
    return retval

def create_task(coro):
    loop = get_running_loop()
    return loop.create_task(coro)

def current_task():
    loop = get_running_loop()
    return loop.pid

def isfuture(obj):
    return isinstance(obj, DSFuture)

def ensure_future(obj, *, loop=None):
    async def wait_for_obj(obj):
        retval = await obj
        return retval
    
    if isinstance(obj, DSFuture):
        return obj
    loop = loop or get_running_loop()
    if inspect.iscoroutine(obj):
        return loop.create_task(obj)
    if inspect.isawaitable(obj):
        return loop.create_task(wait_for_obj(obj))
    raise TypeError(f'Parameter {obj}: an awaitable expected.')
