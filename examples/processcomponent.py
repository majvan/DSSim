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
from random import randint

class Customer(DSProcessComponent):
    def process(self):
        ret = self.enter_nowait(waitingline)
        if ret is None:
            print(f'{sim.time} {self} balked')
            stat['balked'] += 1
            #self.sim.print_trace("", "", "balked")
            return
        print(f'{sim.time} {self} waiting in line')
        ret = yield from self.gwait(50)  # wait maximum 50 for signal from clerk
        if ret is None:
            print(f'{sim.time} {self} reneged')
            self.leave(waitingline)
            stat['reneged'] += 1
            #self.sim.print_trace("", "", "reneged")
        else:
            print(f'{sim.time} {self} being serviced')
            yield from self.gwait()  # wait for service to be completed


class Clerk(DSProcessComponent):
    async def process(self):
        while True:
            customer = await self.pop(waitingline)  # take somebody from waiting line
            customer.signal(self)  # notify customer that we are going to process him
            print(f'{sim.time} {self} starting processing {customer}')
            await self.wait(30)  # process with customer 30
            print(f'{sim.time} {self} finished processing {customer}')
            customer.signal('stop')

if __name__ == '__main__':
    sim = DSSimulation()
    waitingline = Queue(capacity=5, name='waitingline')
    PCGenerator(Customer, lambda last: 7, name='CustomerGenerator')
    stat = {'balked': 0, 'reneged': 0}
    clerks = [Clerk() for i in range(3)]
    sim.run(up_to=1500)  # first do a prerun of 1500 time units without collecting data
    #waitingline.length_of_stay.print_histogram(30, 0, 10)
    print("number reneged", stat['reneged'])
    print("number balked", stat['balked'])
    assert stat == {'balked': 48, 'reneged': 13}
