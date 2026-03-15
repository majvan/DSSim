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
Lite timer/delay/limiter components for LiteLayer2.

These components avoid full pubsub machinery and use only LiteLayer2 primitives:
  - sim.signal(event, subscriber)
  - sim.wait(...) / sim.gwait(...)
  - sim.process(...)
'''
from __future__ import annotations

from collections import deque
from enum import Enum
from typing import Any, Deque, Optional, TYPE_CHECKING

from dssim.base import DSComponent, EventType
from dssim.lite.pubsub import DSLiteCallback, DSLitePub

if TYPE_CHECKING:
    from dssim.simulation import DSSimulation

class LiteDelay(DSComponent):
    '''Delay component that forwards each event after a fixed delay.'''

    def __init__(self, delay: float, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.set_delay(delay)
        self.rx = DSLiteCallback(self._on_event, name=self.name + '.rx', sim=self.sim)
        self.tx = DSLitePub(name=self.name + '.tx', sim=self.sim)

    def set_delay(self, delay: float) -> None:
        self.delay = 0 if delay is None else delay

    def _on_event(self, event: EventType) -> None:
        self.sim.schedule_event(self.delay, event, self.tx)


class LiteLimiter(DSComponent):
    '''Limiter which passes events with max. limited throughput.'''

    def __init__(self, throughput: float, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.buffer: Deque[EventType] = deque()
        self.report_period = self._compute_period(throughput)
        self._pending_period = self.report_period
        self.pusher = self.sim.process(self._push(), name=self.name + '.rx_push').schedule(0)
        self.rx = DSLiteCallback(self._on_event, name=self.name + '.rx', sim=self.sim)
        self.tx = DSLitePub(name=self.name + '.tx', sim=self.sim)

    @staticmethod
    def _compute_period(throughput: float) -> float:
        return 1 / throughput if throughput else float('inf')

    def _wake_pusher(self) -> None:
        self.pusher.signal(True)

    def set_throughput(self, throughput: float) -> None:
        self._pending_period = self._compute_period(throughput)
        if self.report_period == self._pending_period:
            return
        self._wake_pusher()

    def _on_event(self, event: EventType) -> None:
        was_empty = len(self.buffer) == 0
        self.buffer.append(event)
        if was_empty:
            self._wake_pusher()

    async def _push(self) -> None:
        last_sent_at = float('-inf')
        while True:
            while not self.buffer:
                await self.sim.wait()
                self.report_period = self._pending_period

            next_send_at = self.sim.time
            while self.buffer:
                if self.sim.time >= next_send_at:
                    self.sim.signal(self.buffer.popleft(), self.tx)
                    last_sent_at = self.sim.time
                    next_send_at = last_sent_at + self.report_period
                await self.sim.wait(next_send_at - self.sim.time)
                self.report_period = self._pending_period
                next_send_at = last_sent_at + self.report_period


class LiteTimer(DSComponent):
    '''Periodic clock component with start/stop/pause/resume control.'''

    class Status(Enum):
        STOPPED = 0
        RUNNING = 1
        PAUSED = 2

    def __init__(self, period: float = 1, repeats: Optional[int] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.period = period
        self.counter: float = repeats or float('inf')
        self.status: LiteTimer.Status = LiteTimer.Status.STOPPED
        self._remaining = self.period
        self._tick_nr = 0
        self._restart_cycle = False
        self.tx = DSLitePub(name=self.name + '.tx', sim=self.sim)
        self.proc = self.sim.process(self.process(), name=self.name + '.process').schedule(0)

    def _wake_process(self) -> None:
        self.proc.signal({'status': self.status})

    def _emit_tick(self) -> None:
        self._tick_nr += 1
        self.counter -= 1
        self.sim.signal({'tick': self._tick_nr}, self.tx)
        if self.counter <= 0:
            self.status = LiteTimer.Status.STOPPED
            self._remaining = self.period
        else:
            self._remaining = self.period

    async def process(self) -> EventType:
        while True:
            if self.status is LiteTimer.Status.STOPPED:
                await self.sim.wait()
                self._remaining = self.period
                continue

            if self.status is LiteTimer.Status.PAUSED:
                await self.sim.wait()
                continue

            if self._restart_cycle:
                self._remaining = self.period
                self._restart_cycle = False

            wait_started_at = self.sim.time
            interrupt = await self.sim.wait(self._remaining)

            if interrupt is None:
                self._emit_tick()
                continue

            if self.status is LiteTimer.Status.STOPPED:
                self._remaining = self.period
            else:
                elapsed = self.sim.time - wait_started_at
                self._remaining = max(self._remaining - elapsed, 0)

    def start(self, period: Optional[float] = None, repeats: Optional[int] = None) -> "LiteTimer":
        if period is not None:
            self.period = period
        self.counter = repeats or float('inf')
        self.status = LiteTimer.Status.RUNNING
        self._restart_cycle = True
        self._wake_process()
        return self

    def stop(self, event: Optional[EventType] = None) -> "LiteTimer":
        self.status = LiteTimer.Status.STOPPED
        self._remaining = self.period
        self._restart_cycle = False
        self._wake_process()
        return self

    def pause(self, event: Optional[EventType] = None) -> "LiteTimer":
        self.status = LiteTimer.Status.PAUSED
        self._wake_process()
        return self

    def resume(self, event: Optional[EventType] = None) -> "LiteTimer":
        self.status = LiteTimer.Status.RUNNING
        self._wake_process()
        return self


class SimLiteTimeMixin:
    '''Factory mixin for lite timer/delay/limiter components.'''

    def timer(self: Any, *args: Any, **kwargs: Any) -> LiteTimer:
        sim: 'DSSimulation' = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in timer() method should be set to the same simulation instance.')
        return LiteTimer(*args, **kwargs, sim=sim)

    def delay(self: Any, *args: Any, **kwargs: Any) -> LiteDelay:
        sim: 'DSSimulation' = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in delay() method should be set to the same simulation instance.')
        return LiteDelay(*args, **kwargs, sim=sim)

    def limiter(self: Any, *args: Any, **kwargs: Any) -> LiteLimiter:
        sim: 'DSSimulation' = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in limiter() method should be set to the same simulation instance.')
        return LiteLimiter(*args, **kwargs, sim=sim)
