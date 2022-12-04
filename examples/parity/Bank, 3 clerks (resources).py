# Copyright 2021 NXP Semiconductors
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
            yield from self.wait(random.uniform(5, 15))


class Customer(sim.Component):
    def process(self):
        yield from self.get(clerks)  # Get for me one clerk (=resource). If not available, wait
        print(f"{env.now()} Customer in process with clerk")
        yield from self.wait(30)
        yield from self.put(clerks)  # Put the clerk back to the resources, but wait while the resource is full (it is not, the capacity is infinity).


env = sim.Environment() 
CustomerGenerator()
clerks = sim.Resource(amount=3, name="clerks")
env.run(50000)

# clerks.print_statistics()
# clerks.print_info()
