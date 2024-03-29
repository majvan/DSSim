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
Simple controllable bottleneck components
'''
from typing import Any, List
from dssim.base import EventType, DSComponent
from dssim.pubsub import DSCallback, DSProducer
from dssim.process import DSProcess


class IntegralLimiter(DSComponent):
    ''' Limiter which passes events with max. limited throughput.
    The limiter informs with constant frequency how many events were sent since last report.
    '''
    def __init__(self, throughput: float, report_frequency: float = 1, accumulated_report: bool = True, **kwargs: Any) -> None:
        ''' Initialize the limiter with max. throughput of events equal to frequency '''
        super().__init__(**kwargs)
        self.buffer: List[EventType] = []
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
        self.tx = self.sim.producer(name=self.name + '.tx')

    def _on_event(self, event: EventType) -> None:
        ''' Feed consumer handler '''
        self.buffer.append(event)

    async def _push(self) -> None:
        ''' Push another event after events accumlated over time '''
        while True:
            await self.sim.wait(self.report_period)
            self.accumulated_rate += self.report_period * self.throughput
            limited_num = int(self.accumulated_rate)
            self.accumulated_rate -= limited_num
            if not self.accumulated_report:
                events = self.buffer[:limited_num]
            self.buffer = self.buffer[limited_num:]
            if not self.accumulated_report:
                for event in events:
                    self.tx.schedule_event(0, event)
            else:
                self.tx.schedule_kw_event(0, num=limited_num)

class Limiter(DSComponent):
    ''' Limiter which passes events with max. limited throughput.
    The limiter informs with variable frequency (depending on throughput) about constant
    number of event passed.
    '''
    def __init__(self, throughput: float, **kwargs: Any) -> None:
        ''' Throughput limitation for incoming events '''
        super().__init__(**kwargs)
        self.buffer: List[EventType] = []
        self.report_period = self._compute_period(throughput)
        self._update_period = self.report_period
        self.pusher = self.sim.process(
            self._push(),
            name=self.name + '.rx_push',
        ).schedule(0)
        self.rx = self.sim.callback(self._on_event, name=self.name + '.rx')
        self.tx = self.sim.producer(name=self.name + '.tx')

    def _compute_period(self, throughput: float) -> float:
        ''' Compute when is the next time to report '''
        return 1 / throughput if throughput else float('inf')

    def set_throughput(self, throughput: float) -> None:
        ''' Set throughput on runtime '''
        self._update_period = self._compute_period(throughput)
        if self.report_period == self._update_period:
            return
        self.pusher.signal(True)

    def _on_event(self, event: EventType) -> None:
        ''' Feed consumer handler '''
        if self.buffer:
            self.buffer.append(event)
        else:
            self.buffer.append(event)
            self.pusher.signal(True)

    async def _push(self) -> None:
        ''' Push another event after computed throughtput time '''
        previous_time = float('-inf')
        while True:
            # State 1: waiting for first event
            while len(self.buffer) <= 0:
                await self.sim.wait(cond=lambda e: True)
                self.report_period = self._update_period
            # State 2: waiting while having something in the buffer
            next_time = self.sim.time
            while len(self.buffer) > 0:
                if self.sim.time >= next_time:
                    event = self.buffer.pop(0)
                    self.tx.schedule_event(0, event)
                    previous_time = self.sim.time
                    next_time = previous_time + self.report_period
                wait_next = next_time - self.sim.time
                await self.sim.wait(wait_next, cond=lambda e: True)
                self.report_period = self._update_period
                next_time = previous_time + self.report_period
