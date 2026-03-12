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
Lite process wrapper for LiteLayer2.

DSLiteProcess is a minimal schedulable wrapper around a generator/coroutine.
It intentionally avoids DSProcess/pubsub condition stack machinery.
'''
from __future__ import annotations

import inspect
from typing import Any, Optional, Union, Generator, Coroutine, TYPE_CHECKING

from dssim.base import DSComponent, EventType, TimeType, ISubscriber, IFuture
from dssim.pubsub.base import DSAbortException

if TYPE_CHECKING:
    from dssim.simulation import DSSimulation


class DSLiteProcess(DSComponent, ISubscriber, IFuture):
    '''A lightweight process object for LiteLayer2.

    The wrapped generator/coroutine is scheduled as an ISubscriber and receives
    events via ``send(event)``.
    '''

    def __init__(self, schedulable: Union[Generator, Coroutine], *args: Any, **kwargs: Any) -> None:
        self._schedulable = schedulable
        self._scheduled = False
        self._started = False
        self._finished = False
        self.value: EventType = None
        self.exc: Optional[Exception] = None
        if inspect.iscoroutine(schedulable):
            if inspect.getcoroutinestate(schedulable) != inspect.CORO_CREATED:
                raise ValueError('The DSLiteProcess can be used only on non-started generators / coroutines')
        elif inspect.isgenerator(schedulable):
            if inspect.getgeneratorstate(schedulable) != inspect.GEN_CREATED:
                raise ValueError('The DSLiteProcess can be used only on non-started generators / coroutines')
        else:
            raise ValueError(f'The assigned code {schedulable} is not a generator, neither a coroutine.')
        super().__init__(*args, **kwargs)

    def send(self, event: EventType) -> EventType:
        self._started = True
        self.value = self._schedulable.send(event)
        return self.value

    def schedule(self, time: TimeType = 0) -> "DSLiteProcess":
        if not self._scheduled:
            self._scheduled = True
            self.sim.schedule_event(time, None, self)
        return self

    def signal(self, event: EventType) -> None:
        self.sim.signal(event, self)

    def started(self) -> bool:
        return self._started

    def finished(self) -> bool:
        return self._finished

    def finish(self, value: EventType) -> EventType:
        self._finished = True
        self.value = value
        self.sim.cleanup(self)
        return value

    def fail(self, exc: Exception) -> Exception:
        self._finished = True
        self.exc = exc
        self.sim.cleanup(self)
        return exc

    def abort(self, exc: Optional[Exception] = None) -> None:
        if exc is None:
            exc = DSAbortException(self)
        if not self.started():
            self.fail(exc)
            return
        self.signal(exc)


class SimLiteProcessMixin:
    '''Lite schedule/process helpers.

    Wraps generators/coroutines in DSLiteProcess so Lite schedulables have a
    process object with lifecycle methods.
    '''

    def schedule(self: "DSSimulation", time: TimeType, schedulable: Any) -> Any:
        if inspect.iscoroutine(schedulable) or inspect.isgenerator(schedulable):
            process = DSLiteProcess(schedulable, sim=self)
            process.schedule(time)
            return process
        if isinstance(schedulable, DSLiteProcess):
            schedulable.schedule(time)
            return schedulable
        return super().schedule(time, schedulable)

    def process(self: Any, *args: Any, **kwargs: Any) -> DSLiteProcess:
        sim: "DSSimulation" = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in process() method should be set to the same simulation instance.')
        return DSLiteProcess(*args, **kwargs, sim=sim)
