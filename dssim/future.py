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
This file implements future class (see the paradigm in async programming).
'''
from typing import Any, Set, Optional, Generator, TYPE_CHECKING
from contextlib import contextmanager
from dssim.base import TimeType, EventType
from dssim.base import SignalMixin, DSAbortException
from dssim.pubsub import ConsumerMetadata, DSConsumer, DSProducer, TrackEvent


if TYPE_CHECKING:
    from dssim.simulation import DSSimulation


class DSFuture(DSConsumer, SignalMixin):
    ''' Typical future which can be used in the simulations.
    A future can be 'signaled', i.e. finished.
    '''
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # We store the latest value or excpetion. Useful to check the status after finish.
        self.value: Any = None
        self.exc: Optional[Exception] = None
        self._finish_tx = DSProducer(name=self.name+'.future', sim=self.sim)
    
    def create_metadata(self, **kwargs) -> ConsumerMetadata:
        self.meta = ConsumerMetadata()
        self.meta.cond.push(self)  # sending to self => signaling the end of future
        return self.meta

    def get_future_eps(self) -> Set[DSProducer]:
        return {self._finish_tx,}

    def finished(self) -> bool:
        return (self.value, self.exc) != (None, None)

    def abort(self, exc: Optional[Exception] = None) -> None:
        ''' Aborts an awaitable with an exception. '''
        if exc is None:
            exc = DSAbortException(self)
        try:
            self.sim.try_send(self, exc)
        except StopIteration as e:
            self.finish(e)
        except Exception as e:
            self.fail(e)

    def gwait(self, timeout: TimeType = float('inf')) -> Generator[EventType, EventType, EventType]:
        retval = None
        if not self.finished():
            with self.sim.observe_pre(self):
                retval = yield from self.sim.gwait(timeout, cond=self)
        if self.exc is not None:
            raise self.exc
        return retval

    async def wait(self, timeout: TimeType = float('inf')) -> EventType:
        retval = None
        if not self.finished():
            with self.sim.observe_pre(self):
                retval = await self.sim.wait(timeout, cond=self)
        if self.exc is not None:
            raise self.exc
        return retval

    def __await__(self) -> Generator[EventType, EventType, EventType]:
        retval = yield from self.gwait()
        return retval

    def finish(self, value: EventType) -> EventType:
        self.value = value
        self.sim.cleanup(self)
        self._finish_tx.signal(self)
        return value
    
    def fail(self, exc: Exception) -> Exception:
        self.exc = exc
        self.sim.cleanup(self)
        self._finish_tx.signal(self)
        return exc

    @TrackEvent
    def send(self, event: EventType) -> EventType:
        self.finish(event)
        return event


# In the following, self is in fact of type DSSimulation, but PyLance makes troubles with variable types
class SimFutureMixin:
    def future(self: Any, *args: Any, **kwargs: Any) -> DSFuture:
        sim: DSSimulation = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in process() method should be set to the same simulation instance.')
        return DSFuture(*args, **kwargs, sim=sim)
