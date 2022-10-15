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
from dssim.simulation import DSSchedulable, DSComponent
from dssim.pubsub import DSProducer, DSProcessConsumer, DSConsumer
from dssim.components.limiter import Limiter
from random import uniform


class CarGenerator(DSProducer):
    def __init__(self, label, throughput=0, gen_rate=1, name='cargenerator'):
        super().__init__(name=name)
        self._label = label
        self._limiter = Limiter(throughput, name=self.name + '.limiter', sim=self.sim)
        self.tx = self._limiter.tx
        self.sim.schedule(0, self.car_generator(gen_rate))

    def car_generator(self, rate):
        avg_time = 1 / rate if rate else float('inf')
        while True:
            time = uniform(0, 2 * avg_time)
            yield from self.sim.wait(time)
            self.sim.signal(self._limiter.rx, label=self._label, num=1)

    def set_throughput(self, throughput):
        self._limiter.set_throughput(throughput)

    @DSSchedulable
    def set_throughput_late(self, throughput):
        ''' See below a comment why this is defined. '''
        self._limiter.set_throughput(throughput)

class CarRecorder(DSConsumer):
    def __init__(self, name):
        super().__init__(None, name=name)
        self.recorded = []

    def send(self, **data):
        data['time'] = self.sim.time
        self.recorded.append(data)

class Crossroad(DSComponent):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.car_generators = {'N': CarGenerator('N', 0, 0.27, name=self.name + '.cargenN', sim=self.sim),
                               'S': CarGenerator('S', 0, 0.21, name=self.name + '.cargenS', sim=self.sim),
                               'W': CarGenerator('W', 0, 0.15, name=self.name + '.cargenW', sim=self.sim),
                               'E': CarGenerator('E', 0, 0.10, name=self.name + '.cargenE', sim=self.sim),
                               }
        self.recorders = {'N': CarRecorder(name=self.name + '.recorderN', sim=self.sim),
                          'S': CarRecorder(name=self.name + '.recorderS', sim=self.sim),
                          'W': CarRecorder(name=self.name + '.recorderW', sim=self.sim),
                          'E': CarRecorder(name=self.name + '.recorderE', sim=self.sim),
                          }
        sm = self.state_machine()
        self.sim.schedule(0, sm)
        consumer = DSProcessConsumer(sm)
        for k, cg in self.car_generators.items():
            cg.tx.add_consumer(self.recorders[k])
        for cg in self.car_generators.values():
            cg.tx.add_consumer(consumer)
        self.stats = {'EW': 0, 'NS': 0}

    def wait_for_cars(self, time, car_timeout, directions):
        end_time = self.sim.time + time
        cars = 0
        while self.sim.time < end_time:
            if car_timeout:
                max_time = min(car_timeout, end_time - self.sim.time)
            else:
                max_time = end_time - self.sim.time
            rv = yield from self.sim.wait(max_time, lambda e: e['label'] in directions)
            if rv:
                cars += 1
            elif car_timeout:
                # break the cycle if no car came in last time
                break
        return cars

    @DSSchedulable
    def state_machine(self):
        while True:
            print('Setting yellow on East and West road @', self.sim.time)
            yield from self.sim.wait(1)
            print('Setting green on East and West road @', self.sim.time)
            ''' This would normally work with

            self.car_generators['E'].set_throughput(...)
            self.car_generators['W'].set_throughput(...)

            However, if the latest wait_for_cars was triggered by Limiter state machine,
            then we cannot run set_throughput, because that would try to push the Limiter
            state machine.
            Solution: schedule to set throughput via simulation process.
            '''
            self.sim.schedule(0, self.car_generators['E'].set_throughput_late(0.7))
            self.sim.schedule(0, self.car_generators['W'].set_throughput_late(0.7))
            cars = yield from self.wait_for_cars(30, 5, 'EW')
            print('Setting yellow on East and West road @', self.sim.time)
            self.sim.schedule(0, self.car_generators['E'].set_throughput_late(0.3))
            self.sim.schedule(0, self.car_generators['W'].set_throughput_late(0.3))
            cars += yield from self.wait_for_cars(4, 0, 'EW')
            self.stats['EW'] += cars
            print('Setting red on East and West road @', self.sim.time)
            self.sim.schedule(0, self.car_generators['E'].set_throughput_late(0))
            self.sim.schedule(0, self.car_generators['W'].set_throughput_late(0))
            print('Previous # of cars passed', cars)
            yield from self.sim.wait(1)
            print('Setting yellow on North and South road @', self.sim.time)
            yield from self.sim.wait(1)
            print('Setting green on North and South road @', self.sim.time)
            self.sim.schedule(0, self.car_generators['N'].set_throughput_late(0.7))
            self.sim.schedule(0, self.car_generators['S'].set_throughput_late(0.7))
            cars = yield from self.wait_for_cars(30, 6, 'NS')
            print('Setting yellow on North and South road @', self.sim.time)
            self.sim.schedule(0, self.car_generators['N'].set_throughput_late(0.3))
            self.sim.schedule(0, self.car_generators['S'].set_throughput_late(0.3))
            cars += yield from self.wait_for_cars(4, 0, 'NS')
            self.stats['NS'] += cars
            print('Setting red on North and South road @', self.sim.time)
            print('Previous # of cars passed', cars)
            self.sim.schedule(0, self.car_generators['N'].set_throughput_late(0))
            self.sim.schedule(0, self.car_generators['S'].set_throughput_late(0))
            yield from self.sim.wait(1)


if __name__ == '__main__':
    cr0 = Crossroad(name='cr0')
    sim.run(60 * 10)
    print('EW cars', cr0.stats['EW'])
    print('NS cars', cr0.stats['NS'])
    print('E cars', [c['time'] for c in cr0.recorders['E'].recorded])
    print('W cars', [c['time'] for c in cr0.recorders['W'].recorded])
    print('N cars', [c['time'] for c in cr0.recorders['N'].recorded])
    print('S cars', [c['time'] for c in cr0.recorders['S'].recorded])
