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
from dssim.simulation import DSComponent, DSSchedulable, sim
from dssim.pubsub import DSSingleProducer, DSConsumer
from dssim.components.limiter import Limiter
from random import uniform


class MCU(DSComponent):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._producer = DSSingleProducer(name=self.name + '.(internal) generator')
        limiter = Limiter(0.5, name=self.name + '.(internal) limiter0')
        self._producer.add_consumer(limiter.rx)
        consumer = DSConsumer(self, MCU._on_output, name=self.name+'.(internal) output')
        limiter.tx.add_consumer(consumer)

    def boot(self):
        ''' This function has to be called after producers are registered '''
        self.sim.schedule(0, self.generator(average_rate=0.8))

    @DSSchedulable
    def generator(self, average_rate):
        n = 0
        average_sleep = 1 / average_rate
        while True:
            delay = uniform(0, 2 * average_sleep)
            yield from self.sim.wait(delay)
            n += 1
            print('Event', n, 'produced @', self.sim.time)
            self._producer.signal(n=n)  # some event

    def _on_output(self, n, **others):
        print('Event', n, 'came @', self.sim.time)

if __name__ == '__main__':
    mcu0 = MCU(name='mcu master')
    mcu0.boot()
    sim.run(300)
