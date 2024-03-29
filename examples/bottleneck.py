# Copyright 2020- majvan (majvan@gmail.com)
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
from dssim import DSComponent, DSCallback, DSSimulation, DSProducer, Limiter
from random import uniform


class MCU(DSComponent):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        limiter = Limiter(1, name=self.name + '.(internal) limiter0', sim=self.sim)
        self._producer = self.sim.producer(name=self.name + '.(internal) event producer')
        self._producer.add_subscriber(limiter.rx)
        consumer = self.sim.callback(self._on_output, name=self.name+'.(internal) output')
        limiter.tx.add_subscriber(consumer)
        self.stat = {'generated': 0, 'received': 0}

    def boot(self):
        ''' This function has to be called after producers are registered '''
        self.sim.process(self.generator(average_rate=1.2), name=self.name+'.(internal) generator process').schedule(0)

    async def generator(self, average_rate):
        n = 0
        average_sleep = 1 / average_rate
        while True:
            delay = uniform(0, 2 * average_sleep)
            await self.sim.wait(delay)
            n += 1
            print('Event', n, 'produced @', self.sim.time)
            self._producer.signal(n)  # feed the producer with some event
            self.stat['generated'] += 1

    def _on_output(self, n):
        print('Event', n, 'came @', self.sim.time)
        self.stat['received'] += 1

if __name__ == '__main__':
    sim = DSSimulation()
    mcu0 = MCU(name='mcu master', sim=sim)
    mcu0.boot()
    sim.run(300)
    ratio = mcu0.stat['generated'] / mcu0.stat['received']
    assert 1.12 <= ratio <= 1.29, f'Ratio {ratio} is out of range'  # high probability to pass
    assert 296 <= mcu0.stat['received'] <= 300  # high probability to pass

