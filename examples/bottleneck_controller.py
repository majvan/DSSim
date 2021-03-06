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


class MCU(DSComponent):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._producer = DSSingleProducer(name=self.name + '.(internal) generator')
        self.limiter = Limiter(0, name=self.name + '.(internal) limiter0')
        self._producer.add_consumer(self.limiter.rx)
        consumer = DSConsumer(self, MCU._on_output, name=self.name + '.(internal) output')
        self.limiter.tx.add_consumer(consumer)

    def boot(self):
        ''' This function has to be called after producers are registered '''
        self.sim.schedule(0, self.generator(20))
        self.sim.schedule(0, self.limit_controller())

    @DSSchedulable
    def limit_controller(self):
        self.limiter.set_throughput(10)  # 0 sec
        yield from self.sim.wait(1)
        self.limiter.set_throughput(0)  # 1 sec
        yield from self.sim.wait(1)
        self.limiter.set_throughput(10)  # 2 sec
        yield from self.sim.wait(1)
        self.limiter.set_throughput(0)  # 3 sec
        yield from self.sim.wait(1)
        self.limiter.set_throughput(20)  # 4 sec
        yield from self.sim.wait(1)
        self.limiter.set_throughput(0)  # 5 sec
        yield from self.sim.wait(1)
        self.limiter.set_throughput(30)  # 6 sec
        yield from self.sim.wait(1)
        self.limiter.set_throughput(0)  # 7 sec

    @DSSchedulable
    def generator(self, rate):
        n = 0
        delay = 1 / rate
        while True:
            previous_time = self.sim.time
            yield from self.sim.wait(delay)
            n += 1
            # print('Event', n, 'produced @', self.sim.time)
            time = self.sim.time
            self._producer.signal(n=n)  # some event

    def _on_output(self, n, **others):
        print('Event', n, 'came @', self.sim.time)

if __name__ == '__main__':
    mcu0 = MCU(name='mcu master')
    mcu0.boot()
    sim.run(10)
