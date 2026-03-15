# Copyright 2026- majvan (majvan@gmail.com)
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
LiteLayer2 counterpart of examples/pubsub/agent.py.

Note:
- DSLiteQueue does not support prioritized waiter routing.
- This port keeps the same customer/clerk flow without queue-priority assertions.
'''
from dssim import DSSimulation, DSLiteAgent, LiteLayer2, PCLiteGenerator


class Customer(DSLiteAgent):
    def process(self):
        queued = self.enter_nowait(waiting_line)
        if queued is None:
            print(f'{sim.time} {self} balked')
            stat['balked'] += 1
            return
        print(f'{sim.time} {self} waiting in line')
        start = yield from self.gwait(50)
        if start is None:
            print(f'{sim.time} {self} timed out')
            stat['timed_out'] += 1
            return
        print(f'{sim.time} {self} being serviced')
        yield from self.gwait()


class Clerk(DSLiteAgent):
    def process(self):
        self.processed_customers = []
        while True:
            customer = yield from self.gpop(waiting_line)
            customer.signal(self)
            print(f'{sim.time} {self} starting processing {customer}')
            yield from self.gwait(30)
            self.processed_customers.append(customer)
            print(f'{sim.time} {self} finished processing {customer}')
            customer.signal('stop')


if __name__ == '__main__':
    sim = DSSimulation(layer2=LiteLayer2)
    waiting_line = sim.queue(capacity=5, name='waiting_line')
    PCLiteGenerator(Customer, lambda last: 7, name='CustomerGenerator', sim=sim)
    stat = {'balked': 0, 'timed_out': 0}
    clerks = [Clerk(sim=sim) for _ in range(3)]

    sim.run(until=1500)
    print("number timed_out", stat['timed_out'])
    print("number balked", stat['balked'])
    assert len(clerks[0].processed_customers) > 0
    assert len(clerks[1].processed_customers) > 0
    assert len(clerks[2].processed_customers) > 0
