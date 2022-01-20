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
from dssim import DSSimulation, DSProcessComponent, Queue
import random


class CustomerGenerator(DSProcessComponent):
    def process(self):
        while True:
            Customer()
            yield from self.gwait(random.uniform(5, 15))


class Customer(DSProcessComponent):
    def process(self):
        self.enter_nowait(waitingline)
        event = yield from self.gwait()  # wait any event to be activated
        print(f"{self.sim.time} Customer ends with signal {event}")


class Clerk(DSProcessComponent):
    def process(self):
        while True:
            customer = yield from self.gpop(waitingline)
            print(f"{self.sim.time} Processing customer")
            yield from self.gwait(30)
            customer.signal("processed")


sim = DSSimulation()

CustomerGenerator()
clerks = Clerk()
waitingline = Queue(name="waitingline")

sim.run(50)
print()
# waitingline.print_statistics()

