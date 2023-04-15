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
from dssim import DSSimulation, Queue, DSProcessComponent
from random import randint

class CustomerGenerator(DSProcessComponent):
    def process(self):
        while True:
            Customer()
            yield from self.sim.gwait(7) # randint(5, 15))

class Customer(DSProcessComponent):
    def process(self):
        ret = self.enter_nowait(waitingline)
        if ret is None:
            print(f'{sim.time} {self} balked')
            self.sim.number_balked += 1
            #self.sim.print_trace("", "", "balked")
            return
        print(f'{sim.time} {self} waiting in line')
        ret = yield from self.gwait(50)  # wait maximum 50 for signal from clerk
        if ret is None:
            print(f'{sim.time} {self} reneged')
            self.leave(waitingline)
            self.sim.number_reneged += 1
            #self.sim.print_trace("", "", "reneged")
        else:
            print(f'{sim.time} {self} being serviced')
            yield from self.gwait()  # wait for service to be completed


class Clerk(DSProcessComponent):
    def process(self):
        while True:
            customer = yield from self.gpop(waitingline)  # take somebody from waiting line
            customer.signal('start clerk processing')  # get the customer out of it's hold(50)
            print(f'{sim.time} {self} starting processing {customer}')
            yield from self.gwait(30)  # process with customer 30
            print(f'{sim.time} {self} finished processing {customer}')

            customer.signal('stop clerk processing')  # get the customer out of it's hold(50)

if __name__ == '__main__':
    sim = DSSimulation()
    waitingline = Queue(capacity=5, name='waitingline')
    CustomerGenerator(name='CustomerGenerator')
    sim.number_balked = 0
    sim.number_reneged = 0
    clerks = [Clerk() for i in range(3)]

    #waitingline.length.monitor(False)
    sim.run(up_to=1500)  # first do a prerun of 1500 time units without collecting data
    #waitingline.length.monitor(True)
    #sim.run(up_to=3000)  # now do the actual data collection for 1500 time units
    #waitingline.length.print_histogram(30, 0, 1)
    print()
    #waitingline.length_of_stay.print_histogram(30, 0, 10)
    print("number reneged", sim.number_reneged)
    print("number balked", sim.number_balked)
    assert (sim.number_reneged, sim.number_balked) == (13, 48)
