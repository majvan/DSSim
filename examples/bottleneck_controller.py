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
from dssim import DSComponent, DSCallback, DSProcess, DSProducer, DSSimulation, Limiter

class MCU(DSComponent):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.limiter = Limiter(0, name=self.name + '.(internal) limiter0', sim=self.sim)
        self._producer = DSProducer(name=self.name + '.(internal) event producer', sim=self.sim)
        self._producer.add_subscriber(self.limiter.rx)
        consumer = DSCallback(self._on_output, name=self.name + '.(internal) output', sim=self.sim)
        self.limiter.tx.add_subscriber(consumer)
        self.stat = {'generated': 0, 'received': 0}

    def boot(self):
        ''' This function has to be called after producers are registered '''
        DSProcess(self.generator(20), name=self.name + '.(internal) generator process', sim=self.sim).schedule(0)
        DSProcess(self.limit_controller(), name=self.name + '.(internal) control process', sim=self.sim).schedule(0)

    def limit_controller(self):
        self.limiter.set_throughput(10)  # 0 sec
        yield from self.sim.gwait(1)
        self.limiter.set_throughput(0)  # 1 sec
        yield from self.sim.gwait(1)
        self.limiter.set_throughput(10)  # 2 sec
        yield from self.sim.gwait(1)
        self.limiter.set_throughput(0)  # 3 sec
        yield from self.sim.gwait(1)
        self.limiter.set_throughput(20)  # 4 sec
        yield from self.sim.gwait(1)
        self.limiter.set_throughput(0)  # 5 sec
        yield from self.sim.gwait(1)
        self.limiter.set_throughput(30)  # 6 sec
        yield from self.sim.gwait(1)
        self.limiter.set_throughput(0)  # 7 sec

    def generator(self, rate):
        n = 0
        delay = 1 / rate
        while True:
            previous_time = self.sim.time
            yield from self.sim.gwait(delay)
            n += 1
            # print('Event', n, 'produced @', self.sim.time)
            self._producer.signal(n)  # feed the producer with some event
            self.stat['generated'] += 1

    def _on_output(self, n, **others):
        print('Event', n, 'came @', self.sim.time)
        self.stat['received'] += 1

if __name__ == '__main__':
    sim = DSSimulation()
    mcu0 = MCU(name='mcu master', sim=sim)
    mcu0.boot()
    sim.run(10)
    assert mcu0.stat['generated'] == 199
    assert mcu0.stat['received'] == 72
