# Copyright 2023- majvan (majvan@gmail.com)
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
from dssim import DSComponent, DSSimulation, DSProcess
from dssim import NotifierDict, NotifierRoundRobin, NotifierPriority, DSProducer

class SingleProducerMultipleConsumers(DSComponent):
    def __init__(self, notifier_method, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.p = self.sim.producer(name=f'{self.name}.generator', notifier=notifier_method)
        self.sim.schedule(1, self.producer())
        for order in range(6):
            self.sim.process(self.consumer(order), name=self.name+f'.consumer{order}').schedule(0)
        self.log = []

    def producer(self):
        while True:
            self.p.signal('hello from producer')
            yield from self.sim.gwait(1)

    async def consumer(self, order):
        with sim.consume(self.p, priority=order % 3):
            while True:
                data = await self.sim.wait(cond=lambda e:True, val=(order == 2))
                self.log.append((self.sim.time, order))
                print(f'{self.sim.time} Consumer {order} notified with {data}')


'''
This is the setup of the 6 consumers:
consumer0: prio: 0, consumes event: False
consumer1: prio: 1, consumes event: False
consumer2: prio: 2, consumes event: True
consumer3: prio: 0, consumes event: False
consumer4: prio: 1, consumes event: False
consumer5: prio: 2, consumes event: False
'''
sim = DSSimulation(name='dssim0')
# In NotifierDict, prio value is not omited. The event is always notifed from the first consumer.
system = SingleProducerMultipleConsumers(NotifierDict, name='SPMC', sim=sim)
sim.run(4)
assert system.log == [(1, 0), (1, 1), (1, 2), (2, 0), (2, 1), (2, 2), (3, 0), (3, 1), (3, 2)]
print('---')

sim = DSSimulation(name='dssim1')
# In NotifierRoundRobin, prio value is not omited. The event is always notifed from the most un-notified consumer.
system = SingleProducerMultipleConsumers(NotifierRoundRobin, name='SPMC', sim=sim)
sim.run(4)
assert system.log == [(1, 0), (1, 1), (1, 2), (2, 3), (2, 4), (2, 5), (2, 0), (2, 1), (2, 2), (3, 3), (3, 4), (3, 5), (3, 0), (3, 1), (3, 2)]
print('---')

sim = DSSimulation(name='dssim2')
# In NotifierPriority, prio value is taken into account. The event is always notifed from the most priority consumer to the lease priority consumer.
system = SingleProducerMultipleConsumers(NotifierPriority, name='SPMC', sim=sim)
sim.run(4)
assert system.log == [(1, 0), (1, 3), (1, 1), (1, 4), (1, 2), (2, 0), (2, 3), (2, 1), (2, 4), (2, 2), (3, 0), (3, 3), (3, 1), (3, 4), (3, 2)]
