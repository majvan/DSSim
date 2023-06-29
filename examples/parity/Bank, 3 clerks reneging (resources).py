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
'''
The example is showing a code parity with example from salabim project
'''
from dssim.parity import salabim as sim
import random


class CustomerGenerator(sim.Component):
    def process(self):
        while True:
            Customer()
            yield from self.gwait(5)  # If needed: random.randint(5, 15)


class Customer(sim.Component):
    waiting = 0  # dssim does not support the info about the length of components waiting for a resource
    def process(self):
        if Customer.waiting >= 5:
            stat['balked'] += 1
            # env.print_trace("", "", "balked")
            # print(env.now(), stat['balked'], self.name)            
            return
        Customer.waiting += 1
        clerk_amount = yield from self.gget(clerks, timeout=50)
        Customer.waiting -= 1
        if clerk_amount == 0:  # did we get the clerk
            stat['reneged'] += 1
            # env.print_trace("", "", "reneged")
        else:
            yield from self.sim.gwait(30)
            self.put_nowait(clerks)


env = sim.Environment()
CustomerGenerator()
stat = {'balked': 0, 'reneged': 0}
clerks = sim.Resource(3, name="clerks")
time, events = env.run(300000)
# waitingline.length.print_histogram(30, 0, 1)
# waitingline.length_of_stay.print_histogram(30, 0, 10)
print("number reneged", stat['reneged'])
print("number balked", stat['balked'])
assert stat['reneged'] == 6665, f"Unexpected number of reneged."
assert stat['balked'] == 23330, f"Unexpected number of balked."
assert time == 299995, f"Time {time} is out of expected range."
assert events == 276651, f"Number of events {events} is out of expected range."
