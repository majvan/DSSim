# Copyright 2022- majvan (majvan@gmail.com)
# Copyright 2022 NXP Semiconductors
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
import dssim.parity.salabim as sim
import random


class CustomerGenerator(sim.Component):
    def process(self):
        while True:
            Customer()
            yield from self.gwait(random.uniform(5, 15))


class Customer(sim.Component):
    def process(self):
        yield from self.gget(clerks)  # Get for me one clerk (=resource). If not available, wait
        print(f"{env.now()} Customer in process with clerk")
        yield from self.gwait(30)
        yield from self.gput(clerks)  # Put the clerk back to the resources, but wait while the resource is full (it is not, the capacity is infinity).


env = sim.Environment() 
CustomerGenerator()
clerks = sim.Resource(amount=3, name="clerks")
time, events = env.run(50000)

# clerks.print_statistics()
# clerks.print_info()
assert 49950 < time <= 50000, f"Time {time} is out of expected range."
assert 20000 < events < 50000 / 30 * 3 * 6 + 30, f"Number of events {events} is out of expected range."
