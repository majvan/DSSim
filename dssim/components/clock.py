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
from dssim.pubsub import DSProducer, DSConsumer


class Timer(DSComponent):
    ''' The class exports 'source' Producer which ticks with a period provided at init. '''
    def __init__(self, name, period=1, repeats=None, **kwargs):
        super().__init__(**kwargs)
        self.status = 'STOPPED'
        self.period = period
        self.counter = repeats
        self.source = DSProducer(name=self.name + '.tick source')
        feedback = DSConsumer(self, Timer._on_tick, name=self.name + '.(internal) fb', sim=self.sim)
        self.source.add_consumer(feedback)

    def _schedule_next_time(self):
        ''' Methods schedules new event depending on the counter '''
        if self.counter is None:
            self.source.schedule(self.period)
            return True
        if self.counter > 0:
            self.counter -= 1
            self.source.schedule(self.period)
            return True
        return False

    def _on_tick(self, **others):
        ''' Feedback from the tick event to schedule a new event. '''
        if self.status != 'RUNNING':
            return
        if not self._schedule_next_time():
            self.status = 'STOPPED'

    def delay(self, delay_time):
        ''' Start the timer with a delay. '''
        self.start(delay_time, 1)

    def start(self, period=None, repeats=None):
        ''' Start the timer. '''
        if period:
            self.period = period  # Redefine period
        self.counter = repeats
        if self._schedule_next_time():
            self.status = 'RUNNING'

    def stop(self, time):
        ''' Stop the timer. '''
        # if we already scheduled a tick, delete it
        self.source.undo_all_futures()
        self.status = 'STOPPED'
