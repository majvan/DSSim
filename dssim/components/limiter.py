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
from dssim.simulation import DSComponent, DSCallback, DSProcess
from dssim.pubsub import DSProducer


class IntegralLimiter(DSComponent):
    ''' Limiter which passes events with max. limited throughput.
    The limiter informs with constant frequency how many events were sent since last report.
    '''
    def __init__(self, throughput, report_frequency=1, accumulated_report=True, **kwargs):
        ''' Initialize the limiter with max. throughput of events equal to frequency '''
        super().__init__(**kwargs)
        self.buffer = []
        self.throughput = throughput
        self.report_period = 1 / report_frequency
        self.accumulated_rate = 0
        self.accumulated_report = accumulated_report
        self.sim.start(self.push())
        self.rx = DSCallback(
            self._on_event,
            name=self.name + '.rx',
            sim=self.sim,
        )
        self.tx = DSProducer(name=self.name + '.tx', sim=self.sim)

    def _on_event(self, event):
        ''' Feed consumer handler '''
        self.buffer.append(event)

    def push(self):
        ''' Push another event after events accumlated over time '''
        while True:
            yield from self.sim.wait(self.report_period)
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
    def __init__(self, throughput, **kwargs):
        ''' Throughput limitation for incoming events '''
        super().__init__(**kwargs)
        self.buffer = []
        self.report_period = self._compute_period(throughput)
        self._update_period = self.report_period
        self.pusher = DSProcess(
            self._push(),
            name=self.name + '.rx_push',
            sim=self.sim,
        )
        self.pusher.schedule(0)
        self.rx = DSCallback(self._on_event, name=self.name + '.rx', sim=self.sim)
        self.tx = DSProducer(name=self.name + '.tx', sim=self.sim)

    def _compute_period(self, throughput):
        ''' Compute when is the next time to report '''
        return 1 / throughput if throughput else float('inf')

    def set_throughput(self, throughput):
        ''' Set throughput on runtime '''
        self._update_period = self._compute_period(throughput)
        if self.report_period == self._update_period:
            return
        self.pusher.signal(True)

    def _on_event(self, event):
        ''' Feed consumer handler '''
        if self.buffer:
            self.buffer.append(event)
        else:
            self.buffer.append(event)
            self.pusher.signal(True)

    def _push(self):
        ''' Push another event after computed throughtput time '''
        previous_time = float('-inf')
        while True:
            # State 1: waiting for first event
            while len(self.buffer) <= 0:
                yield from self.sim.wait(cond=lambda e: True)
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
                yield from self.sim.wait(wait_next, cond=lambda e: True)
                self.report_period = self._update_period
                next_time = previous_time + self.report_period
