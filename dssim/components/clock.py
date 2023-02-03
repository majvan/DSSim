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
from dssim.simulation import DSComponent
from dssim.pubsub import DSProducer


class Timer(DSComponent):
    ''' The class exports 'source' Producer which ticks with a period provided at init. '''
    def __init__(self, name, period=1, repeats=None, **kwargs):
        super().__init__(**kwargs)
        self.period = period
        self.counter = repeats
        self.state = 'STOPPED'
        self.tx = DSProducer(name=self.name + '.tx', sim=self.sim)
        self.proc = DSProcess(self.process(), name=self.name+'.process', sim=self.sim).schedule(0)

    async def process(self):
        ''' Methods schedules new event depending on the counter '''
        remaining = self.period
        while True:
            if status == 'RUNNING':
                last = self.sim.time
                interrupt = await self.sim.wait(remaining, lambda e:True)  # wait with timeout
                remaining = max(last + self.period - self.sim.time, 0)
                if interrupt is None:  # timed out
                    tick_nr = tick_nr + 1
                    self.counter -= 1
                    self.tx.signal(tick=tick_nr)
                    if self.counter <= 0:
                        self.status = 'STOPPED'
            elif self.status == 'PAUSED':
                interrupt = await self.sim.wait(lambda e:True)  # wait for any state change
            else:  # self.status == 'STOPPED':
                interrupt = await self.sim.wait(lambda e:True)  # wait for any state change
                remaining = self.period

    def start(self, period=None, repeats=None):
        ''' Start the timer. '''
        self.period = period or self.period  # Redefine period
        self.counter = repeats or float('inf')
        self.status = 'RUNNING'
        self.proc.signal(status='RUNNING')

    def stop(self, time):
        ''' Stop the timer. '''
        self.status = 'STOPPED'
        self.proc.signal(status='STOPPED')

    def pause(self):
        ''' Pause the timer. '''
        self.status = 'PAUSED'
        self.proc.signal(status='PAUSED')

    def resume(self):
        ''' Resume the timer. '''
        self.status = 'RUNNING'
        self.proc.signal(status='RUNNING')
