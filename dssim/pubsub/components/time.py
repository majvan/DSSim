# Copyright 2021- majvan (majvan@gmail.com)
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
Time-oriented pubsub components:
  - DSDelay
  - DSLimiter / DSIntegralLimiter
  - DSTimer
'''
from collections import deque
from enum import Enum
from typing import Any, Deque, Optional, TYPE_CHECKING

from dssim.base import DSComponent, EventType

if TYPE_CHECKING:
    from dssim.simulation import DSSimulation


class DSDelay(DSComponent):
    '''DSDelay component that forwards each event after a fixed delay.'''

    def __init__(self, delay: float, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.set_delay(delay)
        self.rx = self.sim.callback(self._on_event, name=self.name + '.rx')
        self.tx = self.sim.publisher(name=self.name + '.tx')

    def set_delay(self, delay: float) -> None:
        '''Update forwarding delay (relative simulation time).'''
        self.delay = 0 if delay is None else delay

    def _on_event(self, event: EventType) -> None:
        '''Forward incoming event after the configured delay.'''
        self.sim.schedule_event(self.delay, event, self.tx)


class DSIntegralLimiter(DSComponent):
    '''DSLimiter which passes events with max. limited throughput.
    The limiter informs with constant frequency how many events were sent since last report.
    '''

    def __init__(self, throughput: float, report_frequency: float = 1, accumulated_report: bool = True, **kwargs: Any) -> None:
        '''Initialize limiter with a max throughput and report cadence.'''
        super().__init__(**kwargs)
        self.buffer: Deque[EventType] = deque()
        self.throughput = throughput
        self.report_period = 1 / report_frequency
        self.accumulated_rate: float = 0
        self.accumulated_report = accumulated_report
        self.pusher = self.sim.process(
            self._push(),
            name=self.name + '.rx_push',
        ).schedule(0)
        self.rx = self.sim.callback(
            self._on_event,
            name=self.name + '.rx',
        )
        self.tx = self.sim.publisher(name=self.name + '.tx')

    def _on_event(self, event: EventType) -> None:
        '''Feed subscriber handler.'''
        self.buffer.append(event)

    async def _push(self) -> None:
        '''Push events according to the configured integral throughput.'''
        while True:
            await self.sim.sleep(self.report_period)
            self.accumulated_rate += self.report_period * self.throughput
            allowed = int(self.accumulated_rate)
            self.accumulated_rate -= allowed

            if self.accumulated_report:
                self.sim.signal({'num': allowed}, self.tx)
                continue

            to_send = min(allowed, len(self.buffer))
            for _ in range(to_send):
                self.sim.signal(self.buffer.popleft(), self.tx)


class DSLimiter(DSComponent):
    '''DSLimiter which passes events with max. limited throughput.
    The limiter informs with variable frequency (depending on throughput) about constant
    number of event passed.
    '''

    def __init__(self, throughput: float, **kwargs: Any) -> None:
        '''Initialize throughput limitation for incoming events.'''
        super().__init__(**kwargs)
        self.buffer: Deque[EventType] = deque()
        self.report_period = self._compute_period(throughput)
        self._pending_period = self.report_period
        self.pusher = self.sim.process(
            self._push(),
            name=self.name + '.rx_push',
        ).schedule(0)
        self.rx = self.sim.callback(self._on_event, name=self.name + '.rx')
        self.tx = self.sim.publisher(name=self.name + '.tx')

    def _compute_period(self, throughput: float) -> float:
        '''Compute period between two forwarded events for given throughput.'''
        return 1 / throughput if throughput else float('inf')

    def _wake_pusher(self) -> None:
        '''Wake the pusher process to apply new state immediately.'''
        self.pusher.signal(True)

    def set_throughput(self, throughput: float) -> None:
        '''Update throughput at runtime.'''
        self._pending_period = self._compute_period(throughput)
        if self.report_period == self._pending_period:
            return
        self._wake_pusher()

    def _on_event(self, event: EventType) -> None:
        '''Feed limiter with a new event.'''
        was_empty = len(self.buffer) == 0
        self.buffer.append(event)
        if was_empty:
            # Start release loop on transition empty -> non-empty.
            self._wake_pusher()

    async def _push(self) -> None:
        '''Forward queued events with current limiter cadence.'''
        last_sent_at = float('-inf')
        while True:
            # State 1: idle until the first queued event (or throughput change).
            while not self.buffer:
                await self.sim.wait()
                self.report_period = self._pending_period

            # State 2: queue non-empty. First event in a new burst is immediate.
            next_send_at = self.sim.time
            while self.buffer:
                if self.sim.time >= next_send_at:
                    self.sim.signal(self.buffer.popleft(), self.tx)
                    last_sent_at = self.sim.time
                    next_send_at = last_sent_at + self.report_period

                # Can be +inf when throughput is zero.
                await self.sim.wait(next_send_at - self.sim.time)
                self.report_period = self._pending_period
                next_send_at = last_sent_at + self.report_period


class DSTimer(DSComponent):
    '''Periodic clock component with start/stop/pause/resume control.'''

    class Status(Enum):
        STOPPED = 0
        RUNNING = 1
        PAUSED = 2

    def __init__(self, period: float = 1, repeats: Optional[int] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.period = period
        self.counter: float = self._normalize_repeats(repeats)
        self.status: DSTimer.Status = DSTimer.Status.STOPPED
        self._remaining = self.period
        self._tick_nr = 0
        self._restart_cycle = False
        self.tx = self.sim.publisher(name=self.name + '.tx')
        self.proc = self.sim.process(self.process(), name=self.name + '.process').schedule(0)

    @staticmethod
    def _normalize_repeats(repeats: Optional[int]) -> float:
        # Keep legacy behavior: None/0 -> infinite ticking.
        return repeats or float('inf')

    def _wake_process(self) -> None:
        self.proc.signal_kw(status=self.status)

    def _emit_tick(self) -> None:
        self._tick_nr += 1
        self.counter -= 1
        self.tx.signal_kw(tick=self._tick_nr)
        if self.counter <= 0:
            self.status = DSTimer.Status.STOPPED
            self._remaining = self.period
        else:
            self._remaining = self.period

    async def process(self) -> EventType:
        '''DSTimer state machine.'''
        while True:
            if self.status is DSTimer.Status.STOPPED:
                await self.sim.wait()
                self._remaining = self.period
                continue

            if self.status is DSTimer.Status.PAUSED:
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

            if self.status is DSTimer.Status.STOPPED:
                self._remaining = self.period
            else:
                elapsed = self.sim.time - wait_started_at
                self._remaining = max(self._remaining - elapsed, 0)

    def start(self, period: Optional[float] = None, repeats: Optional[int] = None) -> "DSTimer":
        '''Start or restart timer ticking.'''
        if period is not None:
            self.period = period
        self.counter = self._normalize_repeats(repeats)
        self.status = DSTimer.Status.RUNNING
        self._restart_cycle = True
        self._wake_process()
        return self

    def stop(self, event: Optional[EventType] = None) -> "DSTimer":
        '''Stop timer ticking and reset remaining period.'''
        self.status = DSTimer.Status.STOPPED
        self._remaining = self.period
        self._restart_cycle = False
        self._wake_process()
        return self

    def pause(self, event: Optional[EventType] = None) -> "DSTimer":
        '''Pause timer ticking while preserving remaining period.'''
        self.status = DSTimer.Status.PAUSED
        self._wake_process()
        return self

    def resume(self, event: Optional[EventType] = None) -> "DSTimer":
        '''Resume ticking from paused position.'''
        self.status = DSTimer.Status.RUNNING
        self._wake_process()
        return self


class SimTimeMixin:
    '''Factory mixin for pubsub timer/delay/limiter components.'''

    def timer(self: Any, *args: Any, **kwargs: Any) -> DSTimer:
        sim: 'DSSimulation' = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in timer() method should be set to the same simulation instance.')
        return DSTimer(*args, **kwargs, sim=sim)

    def delay(self: Any, *args: Any, **kwargs: Any) -> DSDelay:
        sim: 'DSSimulation' = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in delay() method should be set to the same simulation instance.')
        return DSDelay(*args, **kwargs, sim=sim)

    def limiter(self: Any, *args: Any, **kwargs: Any) -> DSLimiter:
        sim: 'DSSimulation' = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in limiter() method should be set to the same simulation instance.')
        return DSLimiter(*args, **kwargs, sim=sim)

    def integral_limiter(self: Any, *args: Any, **kwargs: Any) -> DSIntegralLimiter:
        sim: 'DSSimulation' = kwargs.pop('sim', self)
        if sim is not self:
            raise ValueError('The parameter sim in integral_limiter() method should be set to the same simulation instance.')
        return DSIntegralLimiter(*args, **kwargs, sim=sim)
