# Copyright 2022- majvan (majvan@gmail.com)
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
from dssim import DSSimulation, Queue, DSProcessComponent, PCGenerator
from dssim.pubsub import DSProducer, NotifierPriority
from random import randint

class Customer(DSProcessComponent):
    def process(self):
        ret = self.enter_nowait(waiting_line)
        if ret is None:
            print(f'{sim.time} {self} balked')
            stat['balked'] += 1
            return
        print(f'{sim.time} {self} waiting in line')
        ret = yield from self.gwait(50)  # wait maximum 50 for signal from clerk
        if ret is None:
            print(f'{sim.time} {self} reneged')
            self.leave(waiting_line)
            stat['reneged'] += 1
        else:
            print(f'{sim.time} {self} being serviced')
            yield from self.gwait()  # wait for service to be completed


class Clerk(DSProcessComponent):
    async def process(self):
        self.processed_customers = []
        while True:
            # The priority parameter chooses the clerk who should take from waiting_line first if more clerks are waiting
            customer = await self.pop(waiting_line, priority = -self.instance_nr % 3)  # take somebody from waiting line
            customer.signal(self)  # notify customer that we are going to process him
            print(f'{sim.time} {self} starting processing {customer}')
            await self.wait(30)  # process with customer 30
            self.processed_customers.append(customer)
            print(f'{sim.time} {self} finished processing {customer}')
            customer.signal('stop')

if __name__ == '__main__':
    sim = DSSimulation()
    # In the following we force the notifying endpoint with a special policy
    waiting_line = Queue(capacity=5, change_ep=DSProducer(notifier=NotifierPriority), name='waiting_line')
    PCGenerator(Customer, lambda last: 7, name='CustomerGenerator')
    stat = {'balked': 0, 'reneged': 0}
    clerks = [Clerk() for i in range(3)]
    sim.run(up_to=1500)
    print("number reneged", stat['reneged'])
    print("number balked", stat['balked'])
    assert stat == {'balked': 48, 'reneged': 13}
    # Assert that the policy worked and the highest priority had the last clerk
    assert clerks[0].processed_customers[0].name == 'Customer.2'
    assert clerks[1].processed_customers[0].name == 'Customer.1'
    assert clerks[2].processed_customers[0].name == 'Customer.0'
