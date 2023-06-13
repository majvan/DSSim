# Copyright 2020 NXP Semiconductors
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
Periodic timer with on/off control
'''
from typing import Any, Optional
from enum import Enum
from dssim.base import EventType, DSComponent
from dssim.pubsub import DSProducer
from dssim.process import DSProcess


class Timer(DSComponent):
    class Status(Enum):
        STOPPED = 0
        RUNNING = 1
        PAUSED = 2

    ''' The class exports 'source' Producer which ticks with a period provided at init. '''
    def __init__(self, period: float = 1, repeats: Optional[int] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.period = period
        self.counter: float = repeats or float('inf')
        self.status: Timer.Status = Timer.Status.STOPPED
        self.tx = DSProducer(name=self.name + '.tx', sim=self.sim)
        self.proc = DSProcess(self.process(), name=self.name+'.process', sim=self.sim).schedule(0)

    async def process(self) -> EventType:
        ''' Methods schedules new event depending on the counter '''
        remaining = self.period
        tick_nr = 0
        while True:
            if self.status == Timer.Status.RUNNING:
                last = self.sim.time
                interrupt = await self.sim.wait(remaining, cond=lambda e:True)  # wait with timeout
                remaining = max(last + self.period - self.sim.time, 0)
                if interrupt is None:  # timed out
                    tick_nr = tick_nr + 1
                    self.counter -= 1 
                    self.tx.signal_kw(tick=tick_nr)
                    if self.counter <= 0:
                        self.status = Timer.Status.STOPPED
                    remaining = self.period
            elif self.status == Timer.Status.PAUSED:
                interrupt = await self.sim.wait(cond=lambda e:True)  # wait for any state change
            else:  # self.status == Timer.Status.STOPPED:
                interrupt = await self.sim.wait(cond=lambda e:True)  # wait for any state change
                remaining = self.period

    def start(self, period : Optional[float] = None, repeats: Optional[int] = None) -> "Timer":
        ''' Start the timer. '''
        self.period = period or self.period  # Redefine period
        self.counter = repeats or float('inf')
        self.status = Timer.Status.RUNNING
        self.proc.signal_kw(status=Timer.Status.RUNNING)
        return self

    def stop(self, time) -> "Timer":
        ''' Stop the timer. '''
        self.status = Timer.Status.STOPPED
        self.proc.signal_kw(status=Timer.Status.STOPPED)
        return self

    def pause(self) -> "Timer":
        ''' Pause the timer. '''
        self.status = Timer.Status.PAUSED
        self.proc.signal_kw(status=Timer.Status.PAUSED)
        return self

    def resume(self) -> "Timer":
        ''' Resume the timer. '''
        self.status = Timer.Status.RUNNING
        self.proc.signal_kw(status=self.Status.RUNNING)
        return self
