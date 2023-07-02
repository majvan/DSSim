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
    def process(self):
        entered = self.enter_nowait(waiting_line)
        if entered is None:
            stat['balked'] += 1
            # env.print_trace("", "", "balked")
            # print(env.now(), stat['balked'], self.name)            
            return
        event = yield from waiting_line.gwait(50, cond=lambda e: self not in waiting_line)
        if event is None:  # did we get the event?
            self.leave(waiting_line)
            stat['reneged'] += 1
            # env.print_trace("", "", "reneged")


class Clerk(sim.Component):
    def process(self):
        while True:
            customer_list = yield from waiting_line.gget()  # get from the queue if available
            # customer = customer_list[0]
            yield from self.gwait(30)


env = sim.Environment()
CustomerGenerator()
stat = {'balked': 0, 'reneged': 0}
clerks = [Clerk() for _ in range(3)]
waiting_line = sim.Queue(5, name="waiting_line")
time, events = env.run(300000)
# waiting_line.length.print_histogram(30, 0, 1)
# waiting_line.length_of_stay.print_histogram(30, 0, 10)
print("number reneged", stat['reneged'])
print("number balked", stat['balked'])
assert stat['reneged'] == 6665, f"Unexpected number of reneged."
assert stat['balked'] == 23330, f"Unexpected number of balked."
assert time == 299995, f"Time {time} is out of expected range."
assert events == 289995, f"Number of events {events} is out of expected range."
