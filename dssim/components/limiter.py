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
from dssim.simulation import DSComponent
from dssim.pubsub import DSConsumer, DSProducer, DSProcessConsumer


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
        self.rx = DSConsumer(
            self,
            IntegralLimiter._on_event,
            name=self.name + '.rx',
            sim=self.sim,
        )
        self.tx = DSProducer(name=self.name + '.tx', sim=self.sim)

    def _on_event(self, producer, **event):
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
                    self.tx.schedule(0, **event)
            else:
                self.tx.schedule(0, num=limited_num)

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
        self.pusher = DSProcessConsumer(
            self._push(),
            start=True,
            name=self.name + '.rx_push',
            sim=self.sim,
        )
        self.rx = DSConsumer(self, Limiter._on_event, name=self.name + '.rx', sim=self.sim)
        self.tx = DSProducer(name=self.name + '.tx', sim=self.sim)

    def _compute_period(self, throughput):
        ''' Compute when is the next time to report '''
        return 1 / throughput if throughput else float('inf')

    def set_throughput(self, throughput):
        ''' Set throughput on runtime '''
        self._update_period = self._compute_period(throughput)
        if self.report_period == self._update_period:
            return
        self.pusher.notify(period_update=True)

    def _on_event(self, producer=None, **event):
        ''' Feed consumer handler '''
        if self.buffer:
            self.buffer.append(event)
        else:
            self.buffer.append(event)
            self.pusher.notify(**event)

    def _push(self):
        ''' Push another event after computed throughtput time '''
        while True:
            wait_next = self.report_period
            while self.buffer:
                previous_time = self.sim.time
                yield from self.sim.wait(wait_next, cond=lambda e: 'period_update' in e)
                if self._update_period != self.report_period:
                    elapsed = self.sim.time - previous_time
                    required = self._update_period - self.report_period
                    required -= elapsed
                    self.report_period = self._update_period
                    if required > 0:  # there is still some time to wait
                        wait_next = required
                        continue
                event = self.buffer.pop(0)
                self.tx.schedule(0, **event)
                wait_next = self.report_period
            yield from self.sim.wait(cond=lambda e: True)
